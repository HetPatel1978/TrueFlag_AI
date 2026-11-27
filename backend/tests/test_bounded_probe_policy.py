"""The withdrawn balance floor must not bypass exact-probe safety gates."""

from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr
from test_luminal_provider import config, packet

from app.core.config import Settings
from app.services.luminal_provider import LuminalProvider, ProviderRejected
from app.services.provider_budget import finance_dispatch_allowed, spend_limit


def test_new_policy_removes_balance_floor_but_retains_original_probe_budget():
    settings = Settings(_env_file=None, jwt_secret=SecretStr("x" * 32))
    assert settings.investigation_provider_financial_policy == "bounded_probe_v3"
    assert spend_limit(settings) == Decimal("1.00")
    assert not finance_dispatch_allowed(settings)


def test_new_policy_cannot_send_with_unverified_bootstrap():
    settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("x" * 32),
        investigation_external_enabled=True,
        investigation_provider_call_limit=3,
        investigation_provider_approval_id="mock-only-not-live-approval",
        investigation_provider_terms_sha256="a" * 64,
        investigation_provider_contract_verified=True,
        investigation_provider_input_usd_per_million=1,
        investigation_provider_output_usd_per_million=2,
        investigation_provider_api_key=SecretStr("synthetic-key"),
    )
    calls = []
    with pytest.raises(ProviderRejected, match="provider_probe_bootstrap_unverified"):
        LuminalProvider(
            settings, transport=httpx.MockTransport(lambda request: calls.append(request))
        ).propose(packet(), config())
    assert calls == []
