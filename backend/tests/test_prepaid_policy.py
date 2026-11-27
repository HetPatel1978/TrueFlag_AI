"""Read-only balance and fail-closed prepaid policy; no real provider calls."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from test_luminal_provider import config, packet

from app.core.config import Settings
from app.services.luminal_balance import BalanceUnavailable, LuminalBalanceClient, normalize_balance
from app.services.luminal_provider import LuminalProvider, ProviderRejected
from app.services.provider_budget import spend_limit
from app.services.provider_finance import (
    financial_authorization,
    floor_projection,
)


def prepaid(**overrides):
    return Settings(
        _env_file=None,
        jwt_secret="synthetic-finance-test-only-" + "x" * 32,
        investigation_provider_financial_policy="prepaid_floor_v2",
        **overrides,
    )


def test_financial_scope_is_new_and_not_one_USD():
    settings = prepaid()
    assert financial_authorization(settings)["reported_balance_verified"] is False
    assert spend_limit(settings) == Decimal("797")
    assert spend_limit(prepaid(investigation_provider_minimum_balance_usd=300)) == Decimal("697")
    assert spend_limit(prepaid(investigation_provider_financial_authorization_sha256="a" * 64)) == 0
    assert (
        not settings.investigation_external_enabled
        and settings.investigation_provider_call_limit == 0
    )


@pytest.mark.parametrize(
    "values",
    [
        {"investigation_provider_minimum_balance_usd": 199},
        {"investigation_provider_minimum_balance_usd": float("nan")},
        {"investigation_provider_spend_limit_usd": float("inf")},
    ],
)
def test_unsafe_runtime_configuration_rejected(values):
    with pytest.raises(ValidationError):
        prepaid(**values)


def test_legacy_fixture_policy_not_allowed_in_runtime_settings():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            jwt_secret="synthetic-finance-test-only-" + "x" * 32,
            investigation_provider_financial_policy="legacy_probe_v1",
        )


def test_tampered_authorization_fails_closed(tmp_path, monkeypatch):
    import app.services.provider_finance as module

    path = tmp_path / "untrusted.json"
    path.write_text('{"minimum_preserved_balance_usd":"0"}')
    monkeypatch.setattr(module, "AUTHORIZATION_PATH", path)
    assert financial_authorization(prepaid()) is None and spend_limit(prepaid()) == 0


def test_no_prepaid_dispatch_even_with_all_existing_activation_flags():
    settings = prepaid(
        investigation_external_enabled=True,
        investigation_provider_call_limit=3,
        investigation_provider_approval_id="mock-only-not-live-approval",
        investigation_provider_terms_sha256="a" * 64,
        investigation_provider_contract_verified=True,
        investigation_provider_input_usd_per_million=1,
        investigation_provider_output_usd_per_million=2,
        investigation_provider_api_key=SecretStr("synthetic-invalid-key"),
    )
    calls = []
    with pytest.raises(ProviderRejected, match="provider_prepaid_safety_unverified"):
        LuminalProvider(
            settings, transport=httpx.MockTransport(lambda request: calls.append(request))
        ).propose(packet(), config())
    assert calls == []


@pytest.mark.parametrize(
    "balance,age,reserved,upper,reason",
    [
        (None, 0, "0", None, "current_balance_unverified"),
        ("997", 16, "0", "1", "balance_stale_or_invalid"),
        ("997", -1, "0", "1", "balance_stale_or_invalid"),
        ("201", 0, "0", "1", "balance_floor_reached"),
        ("997", 0, "795", "1", "projected_balance_floor_breach"),
        ("997", 0, "0", None, "request_charge_bound_unverified"),
        ("997", 0, "0", "1", "outside_account_usage_unbounded"),
    ],
)
def test_floor_handles_stale_future_near_floor_and_unknown_outside_usage(
    balance, age, reserved, upper, reason
):
    now = datetime.now(timezone.utc)
    observation = (
        None
        if balance is None
        else dict(
            reported_balance_usd=balance, observed_at=(now - timedelta(seconds=age)).isoformat()
        )
    )
    result = floor_projection(
        prepaid(), observation, Decimal(reserved), Decimal(upper) if upper else None, now=now
    )
    assert (
        not result["dispatch_allowed"]
        and not result["floor_guaranteed"]
        and reason in result["blocked_reasons"]
    )


def test_fresh_high_balance_still_does_not_prove_atomic_floor():
    now = datetime.now(timezone.utc)
    result = floor_projection(
        prepaid(),
        dict(reported_balance_usd="997", observed_at=now.isoformat()),
        Decimal(2),
        Decimal(1),
        now=now,
    )
    assert result["projected_headroom_usd"] == "794.0"
    assert "provider_atomic_floor_unverified" in result["blocked_reasons"]
    assert result["dispatch_allowed"] is False


def test_explicit_USD_balance_only_and_no_identifier_exposure():
    secret = SecretStr("synthetic-invalid-key")
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(
            200, json={"balance_usd": "997.00", "private_account": "do-not-return"}
        )

    result = LuminalBalanceClient(transport=httpx.MockTransport(handle)).read(
        secret, authorized=True
    )
    assert result["reported_balance_usd"] == "997.00" and len(seen) == 1
    assert seen[0].method == "GET" and str(seen[0].url) == "https://flash.luminal.cloud/v1/balance"
    assert "do-not-return" not in str(result) and "synthetic-invalid-key" not in str(result)
    assert not result["account_wide_atomic_floor_verified"]


@pytest.mark.parametrize(
    "value",
    [
        {"balance": 997},
        {"credits": 997},
        {"balance_usd": True},
        {"balance_usd": "NaN"},
        {"balance_usd": "-1"},
        {"balance_usd": "1", "currency": "EUR"},
        {"balance_usd": "1", "balance": "2"},
        [],
        {"balance": "997", "currency": "usd"},
    ],
)
def test_unknown_units_types_and_ambiguous_balances_are_not_funds(value):
    with pytest.raises(BalanceUnavailable):
        normalize_balance(value)


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_balance_errors_never_retry_or_reflect_response(status):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive-vendor-error")

    with pytest.raises(BalanceUnavailable, match="balance_http_rejected"):
        LuminalBalanceClient(transport=httpx.MockTransport(handle)).read(
            SecretStr("synthetic-invalid-key"), authorized=True
        )
    assert len(calls) == 1


@pytest.mark.parametrize("authorized,key", [(False, "synthetic"), (True, "")])
def test_balance_lookup_requires_explicit_authority_and_key(authorized, key):
    calls = []
    with pytest.raises(BalanceUnavailable):
        LuminalBalanceClient(
            transport=httpx.MockTransport(lambda request: calls.append(request))
        ).read(SecretStr(key), authorized=authorized)
    assert not calls


@pytest.mark.parametrize("body", [b'{"balance_usd":"1","balance_usd":"2"}', b"x" * 16385])
def test_balance_duplicate_fields_and_oversized_bodies_rejected(body):
    with pytest.raises(BalanceUnavailable):
        LuminalBalanceClient(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, headers={"content-type": "application/json"}, content=body
                )
            )
        ).read(SecretStr("synthetic"), authorized=True)


def test_balance_timeout_does_not_retry():
    calls = []

    def handle(request):
        calls.append(request)
        raise httpx.ReadTimeout("sensitive-timeout")

    with pytest.raises(BalanceUnavailable, match="balance_lookup_unavailable"):
        LuminalBalanceClient(transport=httpx.MockTransport(handle)).read(
            SecretStr("synthetic"), authorized=True
        )
    assert len(calls) == 1


def test_balance_schema_diagnostic_contains_only_allowlisted_field_types():
    shapes = []
    client = LuminalBalanceClient(
        schema_observer=shapes.append,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"balance": 997, "account_id": "private-account", "api_key": "private-key"},
            )
        ),
    )
    with pytest.raises(BalanceUnavailable):
        client.read(SecretStr("synthetic"), authorized=True)
    assert shapes == [{"balance": "int"}]
    assert "private" not in str(shapes)
