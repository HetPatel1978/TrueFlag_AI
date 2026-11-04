"""Actual PostgreSQL/FastAPI source-scope, deterministic analytics and revocation acceptance."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session
from test_evidence_foundation import admit
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_foundation import headers

from app.models import Alert, AuditEvent, Case, Evidence, User
from app.models.evidence import EvidenceRecordVersion
from app.schemas.evidence_read import AnalyticsRequest, ReadRequest, TransactionRequest, Window
from app.services.evidence import EvidenceNotFound
from app.services.evidence_read import EvidenceReadService, ReadInvalid, SnapshotStale
from app.services.synthetic_evidence import generate_scenario

evidence_setup = evidence_fixture
pytestmark = pytest.mark.postgres


@pytest.fixture
def read_env(platform, evidence_setup):
    foundation, users = evidence_setup
    bundle, source, release = admit(foundation, users["admin"])
    case = foundation.create_case(users["admin"], release)
    reader = EvidenceReadService(platform[1], platform[2])
    return dict(
        foundation=foundation,
        users=users,
        bundle=bundle,
        source=source,
        release=release,
        case=case,
        reader=reader,
        platform=platform,
        auth=headers(platform),
    )


def context(env, actor=None, case=None, assessment=None):
    return env["reader"].get_case_context(
        actor or env["users"]["admin"], case or env["case"], assessment
    )


def query(env, model=TransactionRequest, **kwargs):
    return model(snapshot=context(env).data.snapshot_token, **kwargs)


def path(env, suffix=""):
    return f"/api/v1/cases/{env['case']}/evidence" + suffix


def test_typed_context_and_stable_paginated_transactions(read_env):
    env = read_env
    first = context(env)
    assert first.classification == "case_context"
    assert first.data.available_categories == ["customer", "account", "relationship", "transaction"]
    assert first.data.model_signal is None
    assert len(first.evidence) == 16 and first.sources[0].membership_complete
    reader, actor, case = env["reader"], env["users"]["admin"], env["case"]
    request = TransactionRequest(snapshot=first.data.snapshot_token, limit=2)
    seen = []
    while True:
        page = reader.get_transactions(actor, case, request)
        assert page.data.total == 12 and page.coverage.status == "complete_declared_window"
        assert page.parameters.limit == 2
        assert reader.get_transactions(actor, case, request).reference_id == page.reference_id
        seen += [str(r.reference.record_version_id) for r in page.data.items]
        if page.data.next_cursor is None:
            break
        request = request.model_copy(update={"cursor": page.data.next_cursor})
    assert len(seen) == len(set(seen)) == 12
    with Session(env["platform"][1]) as session:
        stored = session.scalars(
            select(EvidenceRecordVersion).where(
                EvidenceRecordVersion.source_version_id == env["release"],
                EvidenceRecordVersion.kind == "transaction",
            )
        ).all()
        assert set(seen) == {str(r.id) for r in stored}
        assert all(
            r.content_sha256
            == next(ref.sha256 for ref in page.evidence if ref.record_version_id == r.id)
            for r in stored
        )


def test_authenticated_http_workflow_all_projections_and_filters(read_env):
    env = read_env
    client = env["platform"][0]
    ctx = client.get(path(env), headers=env["auth"]).json()
    token = ctx["data"]["snapshot_token"]
    transactions = client.post(
        path(env, "/transactions"),
        json={"snapshot": token, "direction": "credit", "status": "not_recorded"},
        headers=env["auth"],
    )
    assert transactions.status_code == 200
    assert transactions.json()["data"]["total"] == 4
    assert all(r["direction"] == "credit" for r in transactions.json()["data"]["items"])
    for suffix in ["/customers", "/related", "/model"]:
        response = client.post(path(env, suffix), json={"snapshot": token}, headers=env["auth"])
        assert response.status_code == 200
        assert response.json()["snapshot"]["id"] == ctx["snapshot"]["id"]
    related = client.post(
        path(env, "/related"), json={"snapshot": token, "limit": 1}, headers=env["auth"]
    ).json()
    seen = []
    while True:
        seen.extend(r["reference"]["record_version_id"] for r in related["data"]["items"])
        cursor = related["data"]["next_cursor"]
        if cursor is None:
            break
        related = client.post(
            path(env, "/related"),
            json={"snapshot": token, "limit": 1, "cursor": cursor},
            headers=env["auth"],
        ).json()
    assert len(seen) == len(set(seen)) == 3
    for calculation in [
        "count_totals",
        "incoming_outgoing",
        "velocity",
        "concentration",
        "patterns",
        "kyc_comparison",
    ]:
        body = {
            "snapshot": token,
            "calculation": calculation,
            "window": {
                "start": env["bundle"].window_start.isoformat(),
                "end": env["bundle"].as_of.isoformat(),
            },
            "currency": "USD",
        }
        if calculation == "patterns":
            body["large_amount"] = "50.00"
        response = client.post(path(env, "/activity"), json=body, headers=env["auth"])
        assert response.status_code == 200, response.text
        assert response.json()["classification"] == "derived_fact"
        assert response.json()["data"]["calculation_version"] == "trueflag.transaction-analytics.v1"
        assert response.json()["parameters"]["currency"] == "USD"


def test_assignment_revocation_through_existing_api_and_hidden_model_selection(read_env, case_team):
    env = read_env
    client = env["platform"][0]
    admin_snapshot = context(env).data.snapshot_token
    response = client.put(
        f"/api/v1/cases/{env['case']}/assignment",
        json={"expected_version": 1, "assigned_to": case_team["users"]["analyst"]},
        headers=case_team["auth"]["supervisor"],
    )
    assert response.status_code == 200
    with pytest.raises(SnapshotStale):
        env["reader"].get_transactions(
            env["users"]["admin"], env["case"], TransactionRequest(snapshot=admin_snapshot)
        )
    analyst_token = context(env, actor=env["users"]["analyst"]).data.snapshot_token
    response = client.put(
        f"/api/v1/cases/{env['case']}/assignment",
        json={"expected_version": 2, "assigned_to": case_team["users"]["analysttwo"]},
        headers=case_team["auth"]["supervisor"],
    )
    assert response.status_code == 200
    denied = client.post(
        path(env, "/transactions"),
        json={"snapshot": analyst_token},
        headers=case_team["auth"]["analyst"],
    )
    assert denied.status_code == 404
    assert (
        client.get(path(env) + f"?assessment_id={uuid4()}", headers=env["auth"]).status_code == 404
    )
    assert (
        client.get(
            path(env) + "?actor_id=" + str(env["users"]["admin"]), headers=env["auth"]
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "profile",
    [
        "normal",
        "burst",
        "partial",
        "unavailable",
        "missing_income",
        "zero_income",
        "corrections",
        "out_of_order",
        "multi_currency",
        "timezone_unknown",
        "timezone_offsets",
        "inconsistent_kyc",
        "decimal_precision",
    ],
)
def test_numeric_oracle_from_original_generated_observations(read_env, profile):
    env = read_env
    bundle, _, release = admit(env["foundation"], env["users"]["admin"], profile)
    case = env["foundation"].create_case(env["users"]["admin"], release)
    snapshot = context(env, case=case).data.snapshot_token
    window = Window(start=bundle.window_start, end=bundle.as_of)
    # Independent oracle uses generated source observations, not retrieval projections/calculator.
    unique = {r.key: r for r in bundle.records if r.kind == "transaction"}
    for currency in ("USD", "CAD"):
        request = AnalyticsRequest(
            snapshot=snapshot, calculation="count_totals", window=window, currency=currency
        )
        actual = env["reader"].calculate_activity(env["users"]["admin"], case, request)
        expected = [
            r
            for r in unique.values()
            if r.currency == currency
            and r.event_at is not None
            and window.start <= r.event_at < window.end
        ]
        assert actual.data.observed_count == len(expected)
        if expected:
            assert actual.data.observed_total == sum((r.amount for r in expected), Decimal(0))
        elif actual.coverage.status != "complete_declared_window":
            assert actual.data.observed_total is None
        assert actual.data.incoming_count == sum(r.direction == "credit" for r in expected)
        assert actual.data.outgoing_count == sum(r.direction == "debit" for r in expected)
        assert (
            actual.reference_id
            == env["reader"].calculate_activity(env["users"]["admin"], case, request).reference_id
        )


def test_filters_status_missing_time_and_kyc_limits(read_env):
    env = read_env
    bundle, _, release = admit(env["foundation"], env["users"]["admin"], "timezone_unknown")
    case = env["foundation"].create_case(env["users"]["admin"], release)
    ctx = context(env, case=case)
    token = ctx.data.snapshot_token
    result = env["reader"].get_transactions(
        env["users"]["admin"],
        case,
        TransactionRequest(
            snapshot=token, window=Window(start=bundle.window_start, end=bundle.as_of)
        ),
    )
    assert result.data.total == 11 and result.coverage.unknown_time_excluded == 1
    assert result.coverage.status == "partial"
    all_rows = env["reader"].get_transactions(
        env["users"]["admin"], case, TransactionRequest(snapshot=token)
    )
    assert all_rows.data.total == 12 and all_rows.data.items[-1].event_at is None
    response = env["platform"][0].post(
        f"/api/v1/cases/{case}/evidence/transactions",
        json={"snapshot": token, "status": "posted"},
        headers=env["auth"],
    )
    assert response.status_code == 422
    from app.schemas.evidence_read import CustomerRequest

    customer = env["reader"].get_customer_context(
        env["users"]["admin"], case, CustomerRequest(snapshot=token, stale_after_days=30)
    )
    assert customer.data.items[0].stale is True
    assert customer.data.items[0].expected_activity is None
    assert "declared_expected_activity_not_recorded" in customer.coverage.limitations


def test_contradictory_kyc_and_missing_zero_are_not_merged(read_env):
    from app.schemas.evidence_read import CustomerRequest

    env = read_env
    for profile, income in [
        ("missing_income", None),
        ("zero_income", Decimal(0)),
        ("inconsistent_kyc", Decimal(72000)),
    ]:
        _, _, release = admit(env["foundation"], env["users"]["admin"], profile)
        case = env["foundation"].create_case(env["users"]["admin"], release)
        value = env["reader"].get_customer_context(
            env["users"]["admin"],
            case,
            CustomerRequest(snapshot=context(env, case=case).data.snapshot_token),
        )
        assert value.data.items[0].annual_income == income
        if profile == "inconsistent_kyc":
            assert value.data.total == 2 and all(
                r.contradictory_observations for r in value.data.items
            )


def test_correction_snapshot_invalidation_and_no_historical_double_count(read_env):
    env = read_env
    old = context(env)
    old_query = TransactionRequest(snapshot=old.data.snapshot_token, limit=2)
    cursor = (
        env["reader"]
        .get_transactions(env["users"]["admin"], env["case"], old_query)
        .data.next_cursor
    )
    bundle = generate_scenario(env["bundle"].scenario_id, 17, "zero_income", source_revision=2)
    second = env["foundation"].admit_version(env["users"]["admin"], env["source"], bundle)
    # Unlinked admission cannot silently change a case snapshot.
    assert (
        env["reader"].get_transactions(env["users"]["admin"], env["case"], old_query).data.total
        == 12
    )
    env["foundation"].link_version(env["users"]["admin"], env["case"], second)
    with pytest.raises(SnapshotStale):
        env["reader"].get_transactions(env["users"]["admin"], env["case"], old_query)
    current = context(env)
    assert current.sources[0].case_input_reconciliation == "differs_from_immutable_case_input"
    assert current.snapshot.evidence_revision == old.snapshot.evidence_revision + 1
    result = env["reader"].get_transactions(
        env["users"]["admin"], env["case"], TransactionRequest(snapshot=current.data.snapshot_token)
    )
    assert result.data.total == 12 and result.coverage.historical_versions_excluded == 16
    assert all(r.reference.version == 2 for r in result.data.items)
    with pytest.raises(ReadInvalid):
        env["reader"].get_transactions(
            env["users"]["admin"],
            env["case"],
            TransactionRequest(snapshot=current.data.snapshot_token, limit=2, cursor=cursor),
        )
    removed = result.data.items[0].reference.record_version_id
    env["foundation"].revoke_links(env["users"]["admin"], env["case"], env["source"], (removed,))
    remaining = env["reader"].get_transactions(env["users"]["admin"], env["case"], query(env))
    assert remaining.data.total == 11 and remaining.coverage.status == "partial"
    assert removed not in {r.record_version_id for r in remaining.evidence}
    assert all(r.reference.version == 2 for r in remaining.data.items)


def test_cross_case_actor_account_and_cursor_forgery(read_env, case_team):
    env = read_env
    actor = env["users"]["admin"]
    _, _, other_release = admit(env["foundation"], actor)
    other_case = env["foundation"].create_case(actor, other_release)
    original = context(env)
    other = context(env, case=other_case)
    with pytest.raises(EvidenceNotFound):
        env["reader"].get_transactions(
            actor, other_case, TransactionRequest(snapshot=original.data.snapshot_token)
        )
    with pytest.raises(EvidenceNotFound):
        env["reader"].get_transactions(
            actor,
            env["case"],
            TransactionRequest(
                snapshot=original.data.snapshot_token, account_handle=other.data.account_handles[0]
            ),
        )
    with pytest.raises(EvidenceNotFound):
        context(env, actor=env["users"]["analyst"])
    with Session(env["platform"][1]) as session, session.begin():
        session.get(Case, env["case"]).assigned_to = env["users"]["analyst"]
    with pytest.raises(EvidenceNotFound):
        env["reader"].get_transactions(
            env["users"]["analyst"],
            env["case"],
            TransactionRequest(snapshot=original.data.snapshot_token),
        )
    original = context(env)
    q = TransactionRequest(snapshot=original.data.snapshot_token, limit=2)
    cursor = env["reader"].get_transactions(actor, env["case"], q).data.next_cursor
    with pytest.raises(ReadInvalid):
        env["reader"].get_transactions(
            actor, env["case"], q.model_copy(update={"currency": "CAD", "cursor": cursor})
        )
    with pytest.raises(ReadInvalid):
        env["reader"].get_transactions(
            actor, env["case"], q.model_copy(update={"cursor": cursor + "x"})
        )


def test_shared_counterparty_alias_is_not_authority_for_another_source(read_env):
    from app.schemas.evidence_read import RelatedRequest

    env = read_env
    with Session(env["platform"][1]) as session, session.begin():
        other = User(username="other-owner", role="admin", password_hash="test-disabled")
        session.add(other)
        session.flush()
        other_id = other.id
    bundle = env["bundle"]  # Same scenario => identical aliases; different source ownership.
    source = env["foundation"].register_source(other_id, bundle.scenario_id)
    release = env["foundation"].admit_version(other_id, source, bundle)
    case = env["foundation"].create_case(other_id, release)
    other_context = context(env, actor=other_id, case=case)
    current = context(env)
    assert not set(other_context.data.account_handles) & set(current.data.account_handles)
    with pytest.raises(EvidenceNotFound):
        env["reader"].get_related_evidence(
            env["users"]["admin"],
            env["case"],
            RelatedRequest(
                snapshot=current.data.snapshot_token,
                entity_handle=other_context.data.account_handles[0],
            ),
        )
    allowed = env["reader"].get_related_evidence(
        env["users"]["admin"], env["case"], RelatedRequest(snapshot=current.data.snapshot_token)
    )
    text_result = allowed.model_dump_json()
    assert str(source) not in text_result and str(case) not in text_result


def test_withdrawn_counterparty_is_not_recovered_through_transactions(read_env):
    from app.schemas.evidence_read import RelatedRequest

    env = read_env
    initial = env["reader"].get_transactions(env["users"]["admin"], env["case"], query(env))
    counterparty = initial.data.items[0].counterparty_handle
    record = next(r.record_version_id for r in initial.evidence if r.identity_id == counterparty)
    env["foundation"].revoke_links(env["users"]["admin"], env["case"], env["source"], (record,))
    snapshot = context(env).data.snapshot_token
    current = env["reader"].get_transactions(
        env["users"]["admin"], env["case"], TransactionRequest(snapshot=snapshot)
    )
    assert all(r.counterparty_handle is None for r in current.data.items)
    assert str(counterparty) not in current.model_dump_json()
    with pytest.raises(EvidenceNotFound):
        env["reader"].get_related_evidence(
            env["users"]["admin"],
            env["case"],
            RelatedRequest(snapshot=snapshot, entity_handle=counterparty),
        )
    request = AnalyticsRequest(
        snapshot=snapshot,
        calculation="concentration",
        currency="USD",
        window=Window(start=env["bundle"].window_start, end=env["bundle"].as_of),
    )
    totals = env["reader"].calculate_activity(env["users"]["admin"], env["case"], request)
    assert totals.data.unknown_counterparty_count == 12 and totals.data.concentration == []


def test_reversal_partner_withdrawal_prevents_adjusted_totals(read_env):
    env = read_env
    bundle, source, release = admit(env["foundation"], env["users"]["admin"], "corrections")
    case = env["foundation"].create_case(env["users"]["admin"], release)
    initial = context(env, case=case)
    transactions = env["reader"].get_transactions(
        env["users"]["admin"], case, TransactionRequest(snapshot=initial.data.snapshot_token)
    )
    reversal = next(r for r in transactions.data.items if r.event_kind == "reversal")
    target = next(
        r.reference.record_version_id
        for r in transactions.data.items
        if r.reference.identity_id == reversal.reverses_handle
    )
    request = AnalyticsRequest(
        snapshot=initial.data.snapshot_token,
        calculation="count_totals",
        currency="USD",
        treatment="exclude_verified_reversals",
        window=Window(start=bundle.window_start, end=bundle.as_of),
    )
    valid = env["reader"].calculate_activity(env["users"]["admin"], case, request)
    assert valid.data.verified_reversal_pairs_excluded == 1 and valid.data.observed_count == 11
    env["foundation"].revoke_links(env["users"]["admin"], case, source, (target,))
    current = context(env, case=case)
    invalid = env["reader"].calculate_activity(
        env["users"]["admin"],
        case,
        request.model_copy(update={"snapshot": current.data.snapshot_token}),
    )
    assert invalid.data.status == "insufficient_evidence" and invalid.data.observed_total is None
    assert invalid.data.unmatched_reversals == 1


def test_customer_cursor_is_bound_to_threshold_and_related_operation(read_env):
    from app.schemas.evidence_read import CustomerRequest, RelatedRequest

    env = read_env
    _, _, release = admit(env["foundation"], env["users"]["admin"], "inconsistent_kyc")
    case = env["foundation"].create_case(env["users"]["admin"], release)
    token = context(env, case=case).data.snapshot_token
    request = CustomerRequest(snapshot=token, limit=1, stale_after_days=30)
    first = env["reader"].get_customer_context(env["users"]["admin"], case, request)
    second = env["reader"].get_customer_context(
        env["users"]["admin"], case, request.model_copy(update={"cursor": first.data.next_cursor})
    )
    assert (
        first.data.items[0].reference.record_version_id
        != second.data.items[0].reference.record_version_id
    )
    assert first.data.items[0].stale is True and second.data.items[0].stale is False
    with pytest.raises(ReadInvalid):
        env["reader"].get_customer_context(
            env["users"]["admin"],
            case,
            request.model_copy(update={"cursor": first.data.next_cursor, "stale_after_days": 60}),
        )
    with pytest.raises(ReadInvalid):
        env["reader"].get_related_evidence(
            env["users"]["admin"],
            case,
            RelatedRequest(snapshot=token, limit=1, cursor=first.data.next_cursor),
        )


def test_response_limit_fails_before_sensitive_audit_or_disclosure(read_env, monkeypatch):
    import app.services.evidence_read as module

    env = read_env
    token = context(env).data.snapshot_token
    monkeypatch.setattr(module, "MAX_RESPONSE_BYTES", 10)
    response = env["platform"][0].post(
        path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"]
    )
    assert response.status_code == 413 and "amount" not in response.text
    with Session(env["platform"][1]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.retrieval.transactions")
            )
            == 0
        )


def test_database_disconnect_read_audit_rolls_back_and_retry_is_safe(read_env, caplog):
    env = read_env
    engine = env["platform"][1]
    token = context(env).data.snapshot_token
    interrupted = False

    def disconnect(connection, cursor, statement, parameters, context, many):
        nonlocal interrupted
        if (
            not interrupted
            and statement.lower().startswith("insert into audit_events")
            and isinstance(parameters, dict)
            and parameters.get("action") == "evidence.retrieval.transactions"
        ):
            interrupted = True
            pid = connection.scalar(text("SELECT pg_backend_pid()"))
            with engine.begin() as killer:
                assert killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

    event.listen(engine, "before_cursor_execute", disconnect)
    try:
        result = env["platform"][0].post(
            path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"]
        )
        assert result.status_code == 503 and "amount" not in result.text
    finally:
        event.remove(engine, "before_cursor_execute", disconnect)
    assert interrupted
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.retrieval.transactions")
            )
            == 0
        )
    retry = env["platform"][0].post(
        path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"]
    )
    assert retry.status_code == 200
    assert env["bundle"].records[0].alias not in caplog.text


def test_revocation_expiry_and_role_changes(read_env):
    env = read_env
    token = context(env).data.snapshot_token
    claims = jwt.decode(token, options={"verify_signature": False})
    expired = env["reader"]._sign(
        {k: v for k, v in claims.items() if k not in {"iss", "aud"}} | {"expires": 1}
    )
    with pytest.raises(ReadInvalid):
        env["reader"].get_transactions(
            env["users"]["admin"], env["case"], TransactionRequest(snapshot=expired)
        )
    env["foundation"].set_source_access(env["users"]["admin"], env["case"], env["source"], False)
    response = env["platform"][0].post(
        path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"]
    )
    assert response.status_code == 409
    new = context(env)
    assert new.evidence == new.sources == []
    env["foundation"].set_source_access(env["users"]["admin"], env["case"], env["source"], True)
    with pytest.raises(SnapshotStale):
        env["reader"].get_transactions(
            env["users"]["admin"], env["case"], TransactionRequest(snapshot=token)
        )
    with Session(env["platform"][1]) as session, session.begin():
        session.get(User, env["users"]["admin"]).role = "analyst"
    with pytest.raises(EvidenceNotFound):
        context(env)


@pytest.mark.parametrize(
    "suffix", ["", "/transactions", "/customers", "/related", "/model", "/activity"]
)
def test_anonymous_and_cross_analyst_http_denial(read_env, suffix):
    env = read_env
    client = env["platform"][0]
    result = client.get(path(env)) if not suffix else client.post(path(env, suffix), json={})
    assert result.status_code == 401
    result = (
        client.get(path(env), headers=headers(env["platform"], "analyst"))
        if not suffix
        else client.post(
            path(env, suffix),
            json={"snapshot": context(env).data.snapshot_token},
            headers=headers(env["platform"], "analyst"),
        )
    )
    assert result.status_code in {404, 422}  # Invalid operation schemas reveal no case data.


@pytest.mark.parametrize(
    "body",
    [
        {"limit": 51},
        {"limit": True},
        {"account_handle": "' OR TRUE--"},
        {"sql": "SELECT * FROM users"},
        {"status": "posted"},
        {"currency": "USD; DROP TABLE cases"},
        {"window": {"start": "2025-12-01", "end": "2025-12-02"}},
    ],
)
def test_malformed_filters_are_sanitized(read_env, body, caplog):
    env = read_env
    response = env["platform"][0].post(
        path(env, "/transactions"),
        json={"snapshot": context(env).data.snapshot_token, **body},
        headers=env["auth"],
    )
    assert response.status_code == 422
    assert "SELECT *" not in response.text + caplog.text
    assert "DROP TABLE" not in response.text + caplog.text


def test_json_limits_shared_rate_capacity_and_no_raw_predictors(read_env):
    env = read_env
    client = env["platform"][0]
    result = client.get(path(env), headers=env["auth"])
    assert result.status_code == 200 and result.headers["cache-control"] == "no-store"
    token = result.json()["data"]["snapshot_token"]
    assert '"declarations"' not in result.text and '"features"' not in result.text
    data = '{"snapshot":' + json.dumps(token) + ',"limit":1,"limit":2}'
    assert (
        client.post(
            path(env, "/transactions"),
            content=data,
            headers={**env["auth"], "Content-Type": "application/json"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            path(env, "/transactions"),
            content='"' + "x" * 12289 + '"',
            headers={**env["auth"], "Content-Type": "application/json"},
        ).status_code
        == 413
    )
    slots = client.app.state.evidence_read_slots
    for _ in range(4):
        assert slots.acquire(False)
    try:
        assert (
            client.post(
                path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"]
            ).status_code
            == 429
        )
    finally:
        for _ in range(4):
            slots.release()
    env["platform"][2].assessment_api_rate_limit = 1
    assert client.get(path(env), headers=env["auth"]).status_code == 429


def test_audit_failure_discloses_nothing_and_committed_read_is_immutable(read_env, caplog):
    env = read_env
    token = context(env).data.snapshot_token
    engine = env["platform"][1]
    with engine.begin() as c:
        c.execute(
            text("""CREATE FUNCTION reject_read_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'private-evidence-marker'; END; $$""")
        )
        c.execute(
            text("""CREATE TRIGGER reject_read_audit BEFORE INSERT ON audit_events FOR EACH ROW
            WHEN (NEW.action='evidence.retrieval.transactions') EXECUTE FUNCTION reject_read_audit()""")
        )
    response = env["platform"][0].post(
        path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"]
    )
    assert (
        response.status_code == 503 and "private-evidence-marker" not in response.text + caplog.text
    )
    with Session(engine) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.retrieval.transactions")
            )
            == 0
        )
    with engine.begin() as c:
        c.execute(text("DROP TRIGGER reject_read_audit ON audit_events"))
    assert (
        env["platform"][0]
        .post(path(env, "/transactions"), json={"snapshot": token}, headers=env["auth"])
        .status_code
        == 200
    )
    from sqlalchemy.exc import DBAPIError

    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text("DELETE FROM audit_events WHERE action LIKE 'evidence.retrieval.%'"))


def test_read_serializes_with_source_revocation_and_next_call_fails(read_env):
    env = read_env
    ready, release, revoking = Event(), Event(), Event()
    engine = env["platform"][1]
    token = context(env).data.snapshot_token
    request = TransactionRequest(snapshot=token)

    def pause(connection, cursor, statement, parameters, context, many):
        if (
            statement.lower().startswith("insert into audit_events")
            and isinstance(parameters, dict)
            and parameters.get("action") == "evidence.retrieval.transactions"
        ):
            ready.set()
            assert release.wait(10)

    def revoke():
        revoking.set()
        env["foundation"].set_source_access(
            env["users"]["admin"], env["case"], env["source"], False
        )

    event.listen(engine, "before_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            reading = pool.submit(
                env["reader"].get_transactions, env["users"]["admin"], env["case"], request
            )
            assert ready.wait(10)
            revoked = pool.submit(revoke)
            assert revoking.wait(5) and not revoked.done()
            release.set()
            assert reading.result(15).data.total == 12
            revoked.result(15)
    finally:
        release.set()
        event.remove(engine, "before_cursor_execute", pause)
    with pytest.raises(SnapshotStale):
        env["reader"].get_transactions(env["users"]["admin"], env["case"], request)


def test_legacy_aggregate_case_is_explicitly_insufficient(read_env, case_team):
    env = read_env
    case = UUID(case_team["ids"][0])
    with Session(env["platform"][1]) as session, session.begin():
        session.add(
            Evidence(
                case_id=case,
                source_uri="synthetic://unverified",
                content_sha256="0" * 64,
                source_kind="legacy",
                metadata_json={},
            )
        )
    ctx = context(env, case=case)
    assert ctx.coverage.status == "unavailable" and ctx.data.missing_categories == [
        "customer",
        "account",
        "relationship",
        "transaction",
    ]
    request = AnalyticsRequest(
        snapshot=ctx.data.snapshot_token,
        calculation="count_totals",
        currency="USD",
        window=Window(start=env["bundle"].window_start, end=env["bundle"].as_of),
    )
    value = env["reader"].calculate_activity(env["users"]["admin"], case, request)
    assert value.data.observed_total is None and value.data.status == "insufficient_evidence"
    assert not value.evidence and not value.sources
    assert (
        env["reader"]
        .get_model_assessment(
            env["users"]["admin"], case, ReadRequest(snapshot=ctx.data.snapshot_token)
        )
        .data.assessment
        is None
    )


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="Actual pinned Linux RF/SHAP required",
)
def test_explicit_stored_real_assessment_is_model_signal_not_observed_evidence(read_env):
    from app.services.assessments import AssessmentService

    env = read_env
    stored, _ = AssessmentService(env["platform"][1]).assess(
        actor_id=env["users"]["admin"],
        case_id=env["case"],
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="evidence-read-real-model",
        policy="Coverage",
    )
    selected = context(env, assessment=UUID(stored["assessment_id"]))
    assert selected.data.model_signal.score == stored["score"]["score"]
    result = env["reader"].get_model_assessment(
        env["users"]["admin"], env["case"], ReadRequest(snapshot=selected.data.snapshot_token)
    )
    assert (
        result.classification == "model_signal"
        and result.data.assessment.explanation.status == "verified"
    )
    assert result.data.assessment.explanation.method.positive_class_label == 1
    assert result.data.assessment.input_sha256 == stored["input_sha256"]
    response = env["platform"][0].get(
        path(env) + f"?assessment_id={stored['assessment_id']}", headers=env["auth"]
    )
    assert response.status_code == 200
    response = env["platform"][0].post(
        path(env, "/model"),
        json={"snapshot": response.json()["data"]["snapshot_token"]},
        headers=env["auth"],
    )
    assert (
        response.status_code == 200
        and response.json()["data"]["assessment"]["score"] == stored["score"]["score"]
    )
    _, _, other_release = admit(env["foundation"], env["users"]["admin"])
    other_case = env["foundation"].create_case(env["users"]["admin"], other_release)
    with pytest.raises(EvidenceNotFound):
        context(env, case=other_case, assessment=UUID(stored["assessment_id"]))
    assert context(env).data.model_signal is None  # Never silently choose latest.
    with pytest.raises(EvidenceNotFound):
        context(env, assessment=uuid4())
    with Session(env["platform"][1]) as session:
        case = session.get(Case, env["case"])
        assert case.status == "open" and case.disposition is None
        assert session.get(Alert, case.alert_id).features == env["bundle"].declarations
