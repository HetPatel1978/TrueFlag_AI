"""Real PostgreSQL metadata authorization/audit; all external reads are mocked."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_foundation import headers
from test_investigation_coordinator import request as packet_request
from test_live_provider_integration import (
    env as env_fixture,
)
from test_live_provider_integration import (
    evidence_setup as evidence_fixture,
)
from test_live_provider_integration import (
    setup,
)
from test_luminal_provider import config

from app.models import AuditEvent, User
from app.services.evidence import EvidenceBlocked, EvidenceNotFound
from app.services.luminal_balance import BalanceUnavailable
from app.services.provider_finance import reservation_totals
from app.services.provider_usage import ProviderUsageService

env, evidence_setup = env_fixture, evidence_fixture

pytestmark = pytest.mark.postgres


@pytest.fixture(autouse=True)
def historical_prepaid_policy(platform):
    # These existing cases exercise the archived v2 policy explicitly.
    platform[2].investigation_provider_financial_policy = "prepaid_floor_v2"


def test_new_probe_policy_does_not_report_or_require_withdrawn_floor(platform):
    platform[2].investigation_provider_financial_policy = "bounded_probe_v3"
    response = platform[0].get("/api/v1/internal/provider-usage", headers=headers(platform))
    assert response.status_code == 200
    result = response.json()
    assert result["financial_policy"] == "bounded_probe_v3"
    assert result["minimum_balance_usd"] is None
    assert result["indicative_spending_ceiling_usd"] == "1.00"
    assert result["dispatch_allowed"] is False
    assert "probe_bootstrap_unverified" in result["blocked_reasons"]
    assert "provider_atomic_floor_unverified" not in result["blocked_reasons"]


def enabled(platform):
    from pydantic import SecretStr

    platform[2].investigation_provider_balance_lookup_enabled = True
    platform[2].investigation_provider_api_key = SecretStr("synthetic-invalid-key")
    with Session(platform[1]) as session:
        return session.scalar(select(User.id).where(User.username == "admin"))


class MockBalance:
    def __init__(self):
        self.calls = 0

    def read(self, secret, *, authorized):
        assert authorized
        self.calls += 1
        return {"reported_balance_usd": "997.00"}


def test_usage_requires_current_admin_and_hides_sensitive_values(platform):
    client, engine, _, _ = platform
    path = "/api/v1/internal/provider-usage"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(platform, "analyst")).status_code == 403
    auth = headers(platform)
    result = client.get(path, headers=auth)
    assert result.status_code == 200
    body = result.json()
    assert (
        body["minimum_balance_usd"] == "200.0"
        and body["indicative_spending_ceiling_usd"] == "797.0"
    )
    assert body["reported_balance_usd"] is None and body["dispatch_allowed"] is False
    assert body["inference_attempts"] == 0 and body["floor_guaranteed"] is False
    assert body["inference_attempts_this_month"] == 0
    assert body["estimated_usage_cost_this_month_usd"] == "0"
    assert "api_key" not in result.text and "features" not in result.text
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.username == "admin"))
        user.role = "analyst"
    assert client.get(path, headers=auth).status_code == 403


def test_balance_refresh_disabled_by_default(platform):
    response = platform[0].post(
        "/api/v1/internal/provider-usage/balance-refresh", headers=headers(platform)
    )
    assert response.status_code == 409


def test_explicit_refresh_is_audited_immutable_and_does_not_enable_dispatch(platform):
    actor = enabled(platform)
    client = MockBalance()
    service = ProviderUsageService(platform[1], platform[2], balance_client=client)
    result = service.refresh(actor)
    assert client.calls == 1 and result["reported_balance_usd"] == "997.00"
    assert result["dispatch_allowed"] is False and result["floor_guaranteed"] is False
    with Session(platform[1]) as session:
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "evidence.investigation.provider.balance_observed"
            )
        )
        assert event and event.details["reported_balance_usd"] == "997.00"
        identity = event.id
    with pytest.raises(DBAPIError), platform[1].begin() as connection:
        connection.execute(text("DELETE FROM audit_events WHERE id=:id"), {"id": identity})
    with pytest.raises(EvidenceBlocked):
        service.refresh(actor)
    assert client.calls == 1


def test_concurrent_refreshes_make_only_one_mock_read(platform):
    actor = enabled(platform)
    client = MockBalance()
    service = ProviderUsageService(platform[1], platform[2], balance_client=client)

    def run(_):
        try:
            return service.refresh(actor)["reported_balance_usd"]
        except EvidenceBlocked:
            return "limited"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sorted(results) == ["997.00", "limited"] and client.calls == 1


def test_role_revocation_during_metadata_read_denies_publication(platform):
    actor = enabled(platform)

    class RevokingBalance(MockBalance):
        def read(self, secret, *, authorized):
            with Session(platform[1]) as session, session.begin():
                session.get(User, actor).role = "analyst"
            return super().read(secret, authorized=authorized)

    client = RevokingBalance()
    with pytest.raises(EvidenceNotFound):
        ProviderUsageService(platform[1], platform[2], balance_client=client).refresh(actor)
    assert client.calls == 1
    with Session(platform[1]) as session:
        assert (
            session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.action == "evidence.investigation.provider.balance_observed"
                )
            )
            is None
        )


def test_unverified_balance_units_are_logged_as_failure_not_available_funds(platform):
    actor = enabled(platform)

    class UnknownBalance:
        def read(self, *args, **kwargs):
            raise BalanceUnavailable("balance_units_unverified")

    result = ProviderUsageService(
        platform[1], platform[2], balance_client=UnknownBalance()
    ).refresh(actor)
    assert result["reported_balance_usd"] is None and result["dispatch_allowed"] is False
    assert result["last_refresh_status"] == "balance_units_unverified"


def test_usage_api_post_rechecks_admin_and_has_no_inference_fields(platform):
    response = platform[0].post(
        "/api/v1/internal/provider-usage/balance-refresh", headers=headers(platform, "analyst")
    )
    assert response.status_code == 403
    assert "score" not in response.text


def test_balance_observation_from_old_clock_epoch_is_not_current_funds(platform):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func
    from test_snapshot_clock_integrity import clock_view

    from app.models.snapshot_clock import SnapshotClock
    from app.services.snapshot_clock import ClockUnavailable, SnapshotTime

    actor = enabled(platform)
    service = ProviderUsageService(platform[1], platform[2], balance_client=MockBalance())
    assert service.refresh(actor)["reported_balance_usd"] == "997.00"
    with Session(platform[1]) as session:
        instant = max(
            session.scalar(select(func.clock_timestamp())),
            datetime.fromtimestamp(session.get(SnapshotClock, 1).high_water, timezone.utc),
        )
    with clock_view(platform[1], instant) as clock:
        SnapshotTime(platform[1]).observe()
        clock[0] = instant - timedelta(seconds=1)
        with pytest.raises(ClockUnavailable):
            SnapshotTime(platform[1]).observe()
    result = service.status(actor)
    assert result["reported_balance_usd"] is None and result["projected_headroom_usd"] is None
    assert not result["dispatch_allowed"]


def test_usage_audit_database_failure_rolls_back_and_sanitizes_response(platform):
    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    client, engine, _, _ = platform
    auth = headers(platform)

    def failure(connection, cursor, statement, *args):
        if statement.lower().lstrip().startswith("insert into audit_events"):
            raise OperationalError(
                "private-vendor-or-database-error", None, RuntimeError("private-value")
            )

    event.listen(engine, "before_cursor_execute", failure)
    try:
        response = client.get("/api/v1/internal/provider-usage", headers=auth)
    finally:
        event.remove(engine, "before_cursor_execute", failure)
    assert response.status_code == 503 and "private" not in response.text
    with Session(engine) as session:
        assert (
            session.scalar(
                select(AuditEvent.id).where(
                    AuditEvent.action == "evidence.investigation.provider.usage_viewed"
                )
            )
            is None
        )


def test_account_projection_includes_multiple_grants_and_unknown_reservations(env):
    from decimal import Decimal

    service, _, calls = setup(env)
    assert service.run_once(env["token"])["status"] == "succeeded"
    env["platform"][2].investigation_provider_approval_id = "second-synthetic-grant"
    cfg = config(approval_id="second-synthetic-grant")
    service.request(
        env["users"]["admin"], env["case"], "second-financial-grant-001", packet_request(env), cfg
    )
    # The unchanged authorized manifest reuses its already completed parent packet.
    parent = env["service"].run_once(env["token"])
    assert parent is None or parent["status"] in {"succeeded", "abstained"}
    # Leave the second grant prepared with an unknown delivery outcome. A new
    # idempotency key for the same intent must not fabricate a third attempt.
    claim = service.claim(env["token"])
    assert claim and service.prepare(env["token"], claim) is not None
    with Session(env["platform"][1]) as session:
        assert reservation_totals(session)[0] == 2
        assert reservation_totals(session, "second-synthetic-grant")[0] == 1
    view = ProviderUsageService(env["platform"][1], env["platform"][2]).status(
        env["users"]["admin"]
    )
    assert view["inference_attempts"] == 2 and view["unreconciled_attempts"] == 1
    assert view["inference_attempts_this_month"] == 2  # both attempts were created this month
    assert Decimal(view["retained_reservations_usd"]) == Decimal("0.147456")
    assert len(calls) == 1 and view["dispatch_allowed"] is False


def test_anthropic_usage_is_admin_only_read_only_and_secret_free(platform):
    path = "/api/v1/internal/provider-usage/anthropic"
    assert platform[0].get(path).status_code == 401
    response = platform[0].get(path, headers=headers(platform))
    assert response.status_code == 200
    value = response.json()
    assert value["provider"] == "anthropic"
    assert value["requests_this_month"] == 0 and value["spent_this_month_usd"] == "0.00"
    assert value["requests_total"] == 0
    assert "one request per approval" in value["approval_rule"]
    assert not any(k in response.text.lower() for k in ["api_key", "sk-ant", "token", "secret"])
