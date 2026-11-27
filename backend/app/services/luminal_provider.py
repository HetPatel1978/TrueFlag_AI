"""Fixed-host candidate chat adapter. No discovery calls, tools, redirects or automatic retries."""

import json
import time
from decimal import Decimal

import httpx

from app.schemas.investigation_drafts import ProviderReply, ReportedUsage
from app.schemas.provider_live import LIVE_PROMPT, AIProposal, LiveProviderConfig
from app.services.investigation_provider import (
    ProviderFailure,
    ProviderLimit,
    ProviderTimeout,
    strict_json,
)
from app.services.provider_budget import call_limit, finance_dispatch_allowed, spend_limit


class ProviderRejected(ProviderFailure):
    """Terminal rejection or ambiguous delivery; must not cause an automatic paid retry."""

    def __init__(self, message, *, http_status=None, diagnostics=None):
        self.http_status = http_status
        self.diagnostics = diagnostics
        super().__init__(message)


class ProviderRateLimited(ProviderFailure):
    def __init__(self, retry_after=2):
        self.http_status = 429
        self.retry_after = max(2, min(30, retry_after))
        super().__init__("provider_rate_limited")


def authorize(settings, config):
    if not finance_dispatch_allowed(settings):
        reason = (
            "provider_prepaid_safety_unverified"
            if settings.investigation_provider_financial_policy == "prepaid_floor_v2"
            else "provider_probe_bootstrap_unverified"
        )
        raise ProviderRejected(reason)
    if (
        not isinstance(config, LiveProviderConfig)
        or config.provider != "luminal"
        or not (
            settings.investigation_external_enabled
            and call_limit(settings) > 0
            and config.max_attempts == 1
            and config.approval_id == settings.investigation_provider_approval_id
            and config.terms_sha256 == settings.investigation_provider_terms_sha256
            and config.input_usd_per_million
            == Decimal(str(settings.investigation_provider_input_usd_per_million))
            and config.output_usd_per_million
            == Decimal(str(settings.investigation_provider_output_usd_per_million))
            and settings.investigation_provider_approval_id
            and settings.investigation_provider_terms_sha256
            and settings.investigation_provider_contract_verified
            and settings.investigation_provider_api_key.get_secret_value()
            and spend_limit(settings) >= config.max_cost_usd
        )
    ):
        raise ProviderRejected("provider_activation_unavailable")


def strict_output_schema():
    schema = AIProposal.model_json_schema()

    # Strict JSON-schema dialect: every property present, optional values nullable.
    def visit(value):
        if isinstance(value, dict):
            if value.get("type") == "object" and "properties" in value:
                value["additionalProperties"] = False
                value["required"] = list(value["properties"])
            value.pop("default", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


def request_body(packet, config):
    # Serialize only the already-minimized typed projection. No raw documents/instructions.
    raw = json.dumps(
        dict(
            model=config.model,
            stream=False,
            n=1,
            messages=[
                dict(role="system", content=LIVE_PROMPT),
                dict(role="user", content=packet.model_dump_json(warnings="error")),
            ],
            max_tokens=config.max_output_tokens,
            response_format=dict(
                type="json_schema",
                json_schema=dict(
                    name="trueflag_findings", strict=True, schema=strict_output_schema()
                ),
            ),
        ),
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    # Byte ceiling is a conservative admission unit, not a vendor-tokenizer proof.
    if len(raw) > config.max_request_bytes or len(raw) > config.max_input_tokens:
        raise ProviderLimit("provider_input_limit")
    return raw


class LuminalProvider:
    def __init__(self, settings, *, transport=None, cancelled=None):
        self.settings, self.transport, self.cancelled = settings, transport, cancelled

    def _cancel(self):
        if self.cancelled is not None and self.cancelled.is_set():
            raise ProviderRejected("provider_cancelled")

    def propose(self, packet, config):
        authorize(self.settings, config)
        return self._perform_request(packet, config)

    def _perform_request(self, packet, config):
        """Existing fixed-host transport; callers must enforce their own authorization."""
        self._cancel()
        raw = request_body(packet, config)
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
                    config.base_url + "/chat/completions",
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.investigation_provider_api_key.get_secret_value(),
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                    content=raw,
                ) as response:
                    if response.status_code == 429:
                        hint = response.headers.get("retry-after", "2")
                        raise ProviderRateLimited(
                            int(hint) if hint.isdigit() and len(hint) <= 6 else 30
                        )
                    if response.status_code != 200:
                        # Includes auth rejection, unsupported json_schema, redirects and ambiguous 5xx.
                        raise ProviderRejected(
                            "provider_http_rejected", http_status=response.status_code
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
            self._cancel()
            try:
                return self._reply(b"".join(chunks), config)
            except ProviderRejected as error:
                error.http_status = 200
                raise
        except (ProviderFailure, ProviderLimit):
            raise
        except httpx.TimeoutException:
            raise ProviderTimeout("provider_timeout") from None
        except Exception:
            # No upstream response/error strings, URLs, headers or credentials cross this boundary.
            raise ProviderRejected("provider_unavailable") from None

    def _reply(self, raw, config):
        try:
            value = strict_json(raw.decode("utf-8"), config.max_response_bytes)
            if value.get("model") != config.model or len(value["choices"]) != 1:
                raise ValueError
            choice = value["choices"][0]
            msg = choice["message"]
            if (
                choice.get("index") != 0
                or msg.get("role") != "assistant"
                or msg.get("tool_calls")
                or msg.get("function_call")
            ):
                raise ValueError
            reason = choice["finish_reason"]
            finish = (
                "refused"
                if msg.get("refusal") or reason == "content_filter"
                else "incomplete"
                if reason == "length"
                else "complete"
                if reason == "stop"
                else None
            )
            if finish is None:
                raise ValueError
            content = msg.get("content") or ""
            if finish == "complete" and (type(content) is not str or not content.strip()):
                raise ValueError
            if type(content) is not str or len(content.encode()) > min(
                16384, config.max_response_bytes
            ):
                raise ValueError
            usage = value["usage"]
            incoming, outgoing, total = (
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
            )
            if (
                any(type(v) is not int or v < 0 for v in [incoming, outgoing, total])
                or total != incoming + outgoing
                or incoming > config.max_input_tokens
                or outgoing > config.max_output_tokens
            ):
                raise ValueError
            cost = (
                incoming * config.input_usd_per_million + outgoing * config.output_usd_per_million
            ) / 1_000_000
            if cost > config.max_cost_usd:
                raise ValueError
            return ProviderReply(
                content=content,
                finish_reason=finish,
                provider="luminal",
                model=config.model,
                usage=ReportedUsage(
                    input_tokens=incoming,
                    output_tokens=outgoing,
                    cost_usd=cost,
                    basis="provider_reported_tokens_configured_rate_estimate",
                ),
            )
        except Exception:
            raise ProviderRejected("provider_invalid_envelope") from None
