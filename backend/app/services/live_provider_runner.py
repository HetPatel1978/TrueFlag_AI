"""Bounded Linux provider subprocess. Secret travels over stdin, never command line or audit."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.schemas.investigation_drafts import ProviderReply
from app.schemas.provider_live import ClaudeProviderConfig, ClaudeResponseDiagnostics
from app.services.claude_provider import authorize_claude
from app.services.investigation_provider import (
    ProviderFailure,
    ProviderLimit,
    ProviderTimeout,
    strict_json,
)
from app.services.investigation_provider_runner import IsolatedSimulationRunner
from app.services.luminal_provider import ProviderRateLimited, ProviderRejected, authorize


class ProviderRunner:
    def __init__(self, settings):
        self.settings = settings

    def invoke(self, packet, config, cancelled=None):
        if config.provider == "deterministic_fake":
            return IsolatedSimulationRunner().invoke(packet, config)
        if isinstance(config, ClaudeProviderConfig):
            authorize_claude(self.settings, config)
            auth_names = [
                "anthropic_synthetic_demo_enabled",
                "anthropic_contract_verified",
                "anthropic_bootstrap_enabled",
                "anthropic_bootstrap_input_sha256",
                "anthropic_diagnostic_enabled",
                "anthropic_diagnostic_input_sha256",
                "anthropic_fix_verification_enabled",
                "anthropic_fix_input_sha256",
                "anthropic_verification_diagnostic_enabled",
                "anthropic_verification_input_sha256",
                "anthropic_claim_fix_enabled",
                "anthropic_claim_fix_input_sha256",
                "anthropic_live_validation_enabled",
                "anthropic_live_validation_input_sha256",
                "anthropic_development_validation_enabled",
                "anthropic_development_input_sha256",
                "anthropic_development_approval_id",
                "anthropic_terms_sha256",
                "anthropic_demo_spend_limit_usd",
                "anthropic_demo_call_limit",
                "anthropic_api_key",
                "regulatory_investigation_enabled",
            ]
            if getattr(config, "research_scope", None) == "academic_research_v1":
                auth_names += [
                    "academic_research_enabled",
                    "academic_research_scope_sha256",
                    "anthropic_research_dispatch_enabled",
                    "anthropic_research_approval_id",
                    "anthropic_research_input_sha256",
                    "anthropic_research_request_sha256",
                ]
        else:
            authorize(self.settings, config)
            auth_names = [
                "investigation_external_enabled",
                "investigation_provider_financial_policy",
                "investigation_provider_call_limit",
                "investigation_provider_approval_id",
                "investigation_provider_terms_sha256",
                "investigation_provider_contract_verified",
                "investigation_provider_spend_limit_usd",
                "investigation_provider_input_usd_per_million",
                "investigation_provider_output_usd_per_million",
                "investigation_provider_api_key",
            ]
        if sys.platform not in {"linux", "win32"}:
            raise ProviderRejected("provider_linux_required")
        data = dict(
            packet=packet.model_dump(mode="json"),
            config=config.model_dump(mode="json"),
            authorization={
                name: getattr(self.settings, name).get_secret_value()
                if name.endswith("api_key")
                else getattr(self.settings, name)
                for name in auth_names
            },
        )
        if getattr(config,"research_scope",None)=="academic_research_v1" and self.settings.academic_research_response_file:
            data["research_response_file"]=str(self.settings.academic_research_response_file)
        if cancelled and cancelled.is_set():
            raise ProviderRejected("provider_cancelled")
        # Research jobs allow deadline+30s; a 10s child margin lets the in-child HTTP
        # deadline report its own sanitized outcome instead of being killed simultaneously.
        child_timeout = config.request_deadline_seconds + (
            10 if getattr(config, "research_scope", None) == "academic_research_v1" else 0
        )
        if sys.platform == "win32":
            from app.workers.process_control import (
                ProcessCancelled,
                ProcessOutputLimit,
                ProcessTimeout,
                run_windows,
            )

            try:
                code, raw = run_windows(
                    [sys.executable, "-B", "-m", "app.workers.live_provider_process"],
                    json.dumps(data).encode(),
                    environment={
                        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                    timeout=child_timeout,
                    max_output=65536,
                    memory_bytes=384 * 1024 * 1024,
                    cpu_seconds=12,
                    cancelled=cancelled,
                )
            except ProcessTimeout:
                raise ProviderTimeout("provider_timeout") from None
            except ProcessOutputLimit:
                raise ProviderLimit("provider_response_limit") from None
            except ProcessCancelled:
                raise ProviderRejected("provider_cancelled") from None
            except OSError:
                raise ProviderRejected("provider_unavailable") from None
            if code:
                raise ProviderRejected("provider_unavailable")
        else:
            with tempfile.TemporaryFile() as out:
                process = subprocess.Popen(
                    [sys.executable, "-B", "-m", "app.workers.live_provider_process"],
                    stdin=subprocess.PIPE,
                    stdout=out,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env={
                        "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
                        "PYTHONDONTWRITEBYTECODE": "1",
                    },
                )
                deadline = time.monotonic() + child_timeout
                try:
                    payload = json.dumps(data).encode()
                    while True:
                        if cancelled and cancelled.is_set():
                            raise ProviderRejected("provider_cancelled")
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise ProviderTimeout("provider_timeout")
                        try:
                            process.communicate(payload, timeout=min(0.1, remaining))
                            break
                        except subprocess.TimeoutExpired:
                            payload = None
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                out.seek(0)
                raw = out.read(65537)
                if len(raw) > 65536:
                    raise ProviderLimit("provider_response_limit")
                if process.returncode:
                    raise ProviderRejected("provider_unavailable")
        try:
            value = strict_json(raw.decode(), 65536)
            if value.get("error") == "rate_limited":
                raise ProviderRateLimited(value.get("retry_after", 30))
            if value.get("error") == "provider_rejected" and config.provider == "anthropic":
                code = value.get("http_status")
                if code is not None and (type(code) is not int or not 100 <= code <= 599):
                    raise ProviderRejected("provider_invalid_envelope")
                diagnostics = value.get("diagnostics")
                if diagnostics is not None:
                    diagnostics = ClaudeResponseDiagnostics.model_validate(diagnostics).model_dump(
                        mode="json"
                    )
                raise ProviderRejected(
                    "provider_unavailable", http_status=code, diagnostics=diagnostics
                )
            if "error" in value:
                raise ProviderRejected("provider_unavailable")
            return ProviderReply.model_validate(value)
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderRejected("provider_invalid_envelope") from None
