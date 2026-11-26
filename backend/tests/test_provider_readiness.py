"""Offline inventory must not leak secrets or imply approval, even with every flag enabled."""

import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.services.provider_readiness import provider_configuration_report


@pytest.mark.parametrize("enabled", [False, True])
def test_inventory_never_exposes_credentials_or_establishes_authorization(enabled):
    secret = "synthetic-preflight-secret-not-a-real-credential"
    settings = SimpleNamespace(
        investigation_provider_api_key=SecretStr(secret),
        investigation_external_enabled=enabled,
        investigation_simulation_enabled=False,
        investigation_provider_approval_id="synthetic-owner-identifier",
        investigation_provider_terms_sha256="a" * 64,
        investigation_provider_contract_verified=enabled,
        investigation_provider_spend_limit_usd=1,
        investigation_provider_input_usd_per_million=1,
        investigation_provider_output_usd_per_million=2,
        database_url="private-database-canary",
    )
    report = provider_configuration_report(settings)
    raw = json.dumps(report)
    assert secret not in raw and "private-database-canary" not in raw
    assert "synthetic-owner-identifier" not in raw
    assert report["configured"]["api_key_present"] is True
    assert report["activation_authorized_by_this_report"] is False
    assert report["human_authorization_evaluated"] is False
    assert report["authenticated_compatibility_evaluated"] is False
    assert report["live_requests_executed"] == 0
    assert report["grant_wide_call_ceiling"] == 0


def test_preflight_missing_key_is_only_a_presence_check():
    from test_luminal_provider import settings

    values = settings(investigation_provider_api_key=SecretStr(""))
    values.investigation_simulation_enabled = False
    result = provider_configuration_report(values)
    assert result["configured"]["api_key_present"] is False
    assert result["candidate"]["base_url"] == "https://flash.luminal.cloud/v1"
    assert result["candidate"]["model"] == "deepseek-ai/DeepSeek-V4.1-Flash"
