"""Native Claude Messages transport for the existing, independently verified draft pipeline."""

import time
from decimal import Decimal

import httpx

from app.schemas.investigation_drafts import ProviderReply, ReportedUsage
from app.schemas.provider_live import ClaudeProviderConfig
from app.schemas.regulatory_investigation import GroundedProviderInput
from app.services.claude_contract import (
    http_error_diagnostics,
    output_schema,
    parse_response,
    request_body,
    response_diagnostics,
)
from app.services.ingestion import digest
from app.services.investigation_provider import ProviderFailure, ProviderLimit, ProviderTimeout
from app.services.luminal_provider import ProviderRateLimited, ProviderRejected


def authorize_claude(settings, config):
    """Require operator enablement and separately verified compatibility; default deny."""
    try:
        if getattr(config, "research_scope", None) == "academic_research_v1":
            from app.schemas.research_demo import ResearchClaudeConfig

            if not (
                isinstance(config, ResearchClaudeConfig)
                and getattr(settings, "academic_research_enabled", False)
                and getattr(settings, "anthropic_research_dispatch_enabled", False)
                and config.approval_id == settings.anthropic_research_approval_id
                and config.exact_input_sha256 == settings.anthropic_research_input_sha256
                and config.research_scope_sha256 == settings.academic_research_scope_sha256
                and config.terms_sha256 == settings.anthropic_terms_sha256
                and bool(settings.anthropic_terms_sha256)
                and bool(settings.anthropic_api_key.get_secret_value())
                and config.wire_schema_sha256
                == digest(output_schema(grounded=True, wire_format=config.wire_format))
                and settings.anthropic_research_request_sha256
            ):
                raise ProviderRejected("research_dispatch_not_authorized")
            return
        if (
            isinstance(config, ClaudeProviderConfig)
            and config.financial_scope == "development_no_spend_cap_v1"
        ):
            valid = (
                settings.anthropic_synthetic_demo_enabled
                and getattr(settings, "anthropic_development_validation_enabled", False)
                and not settings.anthropic_contract_verified
                and config.purpose == "development_validation"
                and config.wire_format == "flat_selection_v2"
                and config.max_cost_usd == 0
                and config.max_attempts == 1
                and config.approval_id == getattr(settings, "anthropic_development_approval_id", "")
                and bool(config.approval_id)
                and config.exact_input_sha256
                == getattr(settings, "anthropic_development_input_sha256", "")
                and bool(settings.anthropic_api_key.get_secret_value())
                and config.terms_sha256 == settings.anthropic_terms_sha256
                and bool(settings.anthropic_terms_sha256)
                and config.wire_schema_sha256
                == digest(output_schema(wire_format="flat_selection_v2"))
            )
            if not valid:
                raise ProviderRejected("provider_activation_unavailable")
            return
        valid = (
            isinstance(config, ClaudeProviderConfig)
            and settings.anthropic_synthetic_demo_enabled
            and (
                config.purpose == "investigation"
                and settings.anthropic_contract_verified
                or config.purpose == "compatibility_probe"
                and getattr(settings, "anthropic_bootstrap_enabled", False)
                and not settings.anthropic_contract_verified
                and config.exact_input_sha256
                == getattr(settings, "anthropic_bootstrap_input_sha256", "")
                or config.purpose == "compatibility_diagnostic"
                and getattr(settings, "anthropic_diagnostic_enabled", False)
                and not settings.anthropic_contract_verified
                and config.exact_input_sha256
                == getattr(settings, "anthropic_diagnostic_input_sha256", "")
                or config.purpose == "compatibility_fix_verification"
                and getattr(settings, "anthropic_fix_verification_enabled", False)
                and not settings.anthropic_contract_verified
                and config.exact_input_sha256 == getattr(settings, "anthropic_fix_input_sha256", "")
                or config.purpose == "verification_diagnostic"
                and getattr(settings, "anthropic_verification_diagnostic_enabled", False)
                and not settings.anthropic_contract_verified
                and config.exact_input_sha256
                == getattr(settings, "anthropic_verification_input_sha256", "")
                or config.purpose == "claim_type_fix_verification"
                and getattr(settings, "anthropic_claim_fix_enabled", False)
                and not settings.anthropic_contract_verified
                and config.exact_input_sha256
                == getattr(settings, "anthropic_claim_fix_input_sha256", "")
                or config.purpose == "live_validation"
                and getattr(settings, "anthropic_live_validation_enabled", False)
                and not settings.anthropic_contract_verified
                and config.exact_input_sha256
                == getattr(settings, "anthropic_live_validation_input_sha256", "")
            )
            and bool(settings.anthropic_api_key.get_secret_value())
            and 1 <= settings.anthropic_demo_call_limit <= 100
            and Decimal("0") < Decimal(str(settings.anthropic_demo_spend_limit_usd)) <= 20
            and config.max_cost_usd <= Decimal(str(settings.anthropic_demo_spend_limit_usd))
            and config.approval_id == "synthetic-claude-demo-2026-11-20"
            and (
                config.wire_schema_sha256 == digest(output_schema(wire_format=config.wire_format))
                or settings.regulatory_investigation_enabled
                and config.purpose == "investigation"
                and config.wire_schema_sha256
                == digest(output_schema(grounded=True, wire_format=config.wire_format))
            )
            and bool(settings.anthropic_terms_sha256)
            and config.terms_sha256 == settings.anthropic_terms_sha256
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ProviderRejected("provider_activation_unavailable")


class ClaudeProvider:
    def __init__(self, settings, *, transport=None, cancelled=None, response_recorder=None):
        self.settings, self.transport, self.cancelled = settings, transport, cancelled
        self.response_recorder = response_recorder

    def _cancel(self):
        if self.cancelled is not None and self.cancelled.is_set():
            raise ProviderRejected("provider_cancelled")

    def propose(self, packet, config):
        authorize_claude(self.settings, config)
        grounded = isinstance(packet, GroundedProviderInput)
        research = getattr(config, "research_scope", None) == "academic_research_v1"
        if research and getattr(packet, "regulatory_context", None) != "research_unapproved":
            raise ProviderRejected("research_context_required")
        if (
            grounded
            and not research
            and (
                not self.settings.regulatory_investigation_enabled
                or config.purpose != "investigation"
                or config.wire_schema_sha256
                != digest(output_schema(grounded=True, wire_format=config.wire_format))
            )
        ):
            raise ProviderRejected("regulatory_provider_activation_unavailable")
        if (
            config.purpose != "investigation"
            and digest(packet.model_dump(mode="json")) != config.exact_input_sha256
        ):
            raise ProviderRejected("synthetic_probe_input_mismatch")
        raw = request_body(
            packet,
            max_output_tokens=config.max_output_tokens,
            max_bytes=config.max_request_bytes,
            wire_format=config.wire_format,
        )
        if research:
            import hashlib

            if hashlib.sha256(raw).hexdigest() != self.settings.anthropic_research_request_sha256:
                raise ProviderRejected("research_request_changed")
        self._cancel()
        deadline = time.monotonic() + config.request_deadline_seconds
        try:
            with httpx.Client(
                transport=self.transport,
                trust_env=False,
                follow_redirects=False,
                timeout=httpx.Timeout(config.request_deadline_seconds),
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                with client.stream(
                    "POST",
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.settings.anthropic_api_key.get_secret_value(),
                        "anthropic-version": "2023-06-01",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    content=raw,
                ) as response:
                    if response.status_code == 429:
                        if self.response_recorder is not None:
                            self.response_recorder(response.status_code, b"")
                        raise ProviderRateLimited()
                    if response.status_code != 200:
                        error_body = b""
                        for chunk in response.iter_raw(chunk_size=1024):
                            self._cancel()
                            if len(error_body) + len(chunk) > 8192 or time.monotonic() >= deadline:
                                break
                            error_body += chunk
                        if self.response_recorder is not None:
                            self.response_recorder(response.status_code, error_body)
                        raise ProviderRejected(
                            "provider_http_rejected",
                            http_status=response.status_code,
                            diagnostics=http_error_diagnostics(
                                error_body,
                                response.headers.get("request-id"),
                                development=config.financial_scope == "development_no_spend_cap_v1",
                                credential=self.settings.anthropic_api_key.get_secret_value(),
                            ),
                        )
                    if (
                        response.headers.get("content-type", "").split(";")[0].strip().lower()
                        != "application/json"
                        or response.headers.get("content-encoding", "identity").lower()
                        != "identity"
                    ):
                        raise ProviderRejected("provider_invalid_envelope")
                    chunks, size = [], 0
                    for chunk in response.iter_raw(chunk_size=4096):
                        self._cancel()
                        if time.monotonic() >= deadline:
                            raise ProviderTimeout("provider_timeout")
                        size += len(chunk)
                        if size > config.max_response_bytes:
                            raise ProviderLimit("provider_response_limit")
                        chunks.append(chunk)
                    if self.response_recorder is not None:
                        self.response_recorder(response.status_code, b"".join(chunks))
            self._cancel()
            try:
                result = parse_response(
                    b"".join(chunks),
                    max_input_tokens=config.max_input_tokens,
                    max_output_tokens=config.max_output_tokens,
                    grounded=grounded,
                    wire_format=config.wire_format,
                )
            except ProviderFailure:
                raise ProviderRejected(
                    "provider_invalid_envelope",
                    http_status=200,
                    diagnostics=response_diagnostics(
                        b"".join(chunks), wire_format=config.wire_format, grounded=grounded
                    ),
                ) from None
            if (
                config.financial_scope != "development_no_spend_cap_v1"
                and result.estimated_cost_usd > config.max_cost_usd
            ):
                raise ProviderRejected("provider_cost_limit")
            return ProviderReply(
                content=result.proposal.model_dump_json(warnings="error"),
                finish_reason="complete",
                provider="anthropic",
                model=config.model,
                usage=ReportedUsage(
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cost_usd=result.estimated_cost_usd,
                    basis="provider_reported_tokens_configured_rate_estimate",
                ),
            )
        except (ProviderFailure, ProviderLimit):
            raise
        except httpx.TimeoutException:
            raise ProviderTimeout("provider_timeout") from None
        except Exception:
            raise ProviderRejected("provider_unavailable") from None
