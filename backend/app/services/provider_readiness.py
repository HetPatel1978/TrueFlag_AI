"""Read-only technical inventory. Configuration is never human authorization or a probe."""

from app.schemas.provider_live import LIVE_PROMPT_SHA, LIVE_PROMPT_VERSION, LiveProviderConfig
from app.services.provider_budget import spend_limit


def provider_configuration_report(settings):
    # An explicit output allowlist: never serialize Settings, env, secrets or exception text.
    return {
        "report_version": "trueflag.provider-preflight.v1",
        "scope": "configuration_only_no_network_or_database",
        "candidate": {
            "provider": "luminal",
            "base_url": LiveProviderConfig.model_fields["base_url"].default,
            "model": LiveProviderConfig.model_fields["model"].default,
            "prompt_version": LIVE_PROMPT_VERSION,
            "prompt_sha256": LIVE_PROMPT_SHA,
            "required_key_variable": "INVESTIGATION_PROVIDER_API_KEY",
            "alternate_key_variable": "LLM_API_KEY",
            "data_scope": "synthetic_only",
            "response_format_required": "json_schema_strict",
        },
        "configured": {
            "api_key_present": bool(settings.investigation_provider_api_key.get_secret_value()),
            "external_execution_enabled": settings.investigation_external_enabled,
            "simulation_enabled": settings.investigation_simulation_enabled,
            "approval_id_present": bool(settings.investigation_provider_approval_id),
            "terms_digest_present": bool(settings.investigation_provider_terms_sha256),
            "contract_verified_flag": settings.investigation_provider_contract_verified,
            "grant_reservation_ceiling_usd": settings.investigation_provider_spend_limit_usd,
            "input_usd_per_million": settings.investigation_provider_input_usd_per_million,
            "output_usd_per_million": settings.investigation_provider_output_usd_per_million,
        },
        "candidate_defaults_not_operator_approval": {
            name: LiveProviderConfig.model_fields[name].default
            for name in [
                "max_input_tokens",
                "max_output_tokens",
                "total_token_budget",
                "max_request_bytes",
                "max_response_bytes",
                "request_deadline_seconds",
                "max_attempts",
            ]
        },
        "grant_wide_call_ceiling": getattr(settings, "investigation_provider_call_limit", 0),
        "hard_request_ceiling": 3,
        "hard_application_spend_ceiling_usd": str(spend_limit(settings)),
        "financial_policy": getattr(
            settings, "investigation_provider_financial_policy", "unavailable"
        ),
        "provider_floor_guaranteed": False,
        "grant_expiry": None,
        "human_authorization_evaluated": False,
        "authenticated_compatibility_evaluated": False,
        "semantic_quality_evaluated": False,
        "live_requests_executed": 0,
        "activation_authorized_by_this_report": False,
    }
