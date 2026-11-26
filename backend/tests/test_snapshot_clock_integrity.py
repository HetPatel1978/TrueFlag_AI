"""Real PostgreSQL clock-view faults; never adjust server clocks or expiry rules."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import jwt
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_investigation_coordinator import env as investigation_fixture
from test_investigation_coordinator import submit

from app.models import AuditEvent
from app.models.evidence import EvidenceTransaction
from app.models.investigations import InvestigationPacket
from app.models.snapshot_clock import SnapshotClock
from app.schemas.evidence_read import TransactionRequest
from app.services.evidence import EvidenceNotFound
from app.services.evidence_read import SNAPSHOT_SECONDS, ReadInvalid, SnapshotStale
from app.services.investigation_coordinator import InvestigationLeaseLost
from app.services.investigation_verifier import VerificationFailed
from app.services.snapshot_clock import ClockUnavailable

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture
env = investigation_fixture


@contextmanager
def clock_view(engine, instant):
    """Replace only fixture-engine clock SELECT results with a bound UTC instant.

    Both durable writes and independent verification still use real PostgreSQL.
    The mutable clock allows a step between reads, without process/global patches.
    """
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires PostgreSQL timestamp semantics and real evidence constraints")
    clock = [instant]
    reads = []

    def selected_time(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith("SELECT") and "clock_timestamp()" in statement:
            assert isinstance(parameters, dict) and not many
            reads.append(clock[0])
            return statement.replace("clock_timestamp()", "CAST(%(_g031_clock)s AS timestamptz)"), {
                **parameters,
                "_g031_clock": clock[0],
            }
        return statement, parameters

    event.listen(engine, "before_cursor_execute", selected_time, retval=True)
    try:
        yield clock
    finally:
        event.remove(engine, "before_cursor_execute", selected_time)
        assert reads, "Clock fault must reach a real PostgreSQL query"


def anchor(env):
    with env["platform"][1].connect() as connection:
        now = int(connection.scalar(select(func.clock_timestamp())).timestamp())
        floor = connection.scalar(select(SnapshotClock.high_water).where(SnapshotClock.id == 1))
        # The synthetic clock must start in a valid state even if the host stepped
        # backward between migration bootstrap and fixture setup. Do not reset state.
        return datetime.fromtimestamp(max(now, floor), timezone.utc)


def rows(engine, model):
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


def snapshot(env):
    reader = env["service"].reader
    response = reader.get_case_context(env["users"]["admin"], env["case"])
    return response, TransactionRequest(snapshot=response.data.snapshot_token, limit=1)


def read(env, request):
    return env["service"].reader.get_transactions(env["users"]["admin"], env["case"], request)


@pytest.mark.parametrize("age", [0, SNAPSHOT_SECONDS - 1, SNAPSHOT_SECONDS, SNAPSHOT_SECONDS + 1])
def test_exact_database_expiry_boundary_without_refresh(env, age):
    initial = anchor(env)
    with clock_view(env["platform"][1], initial) as clock:
        response, request = snapshot(env)
        original = jwt.decode(request.snapshot, options={"verify_signature": False})["expires"]
        assert original == int(initial.timestamp()) + SNAPSHOT_SECONDS
        clock[0] = initial + timedelta(seconds=age)
        if age >= SNAPSHOT_SECONDS:
            with pytest.raises(ReadInvalid, match="^invalid_or_expired_evidence_token$"):
                read(env, request)
        else:
            result = read(env, request)
            assert result.snapshot == response.snapshot
            assert result.data.next_cursor is not None
            claims = jwt.decode(result.data.next_cursor, options={"verify_signature": False})
            assert claims["expires"] == original


def test_backward_step_reproduces_pre_tamper_assembly_failure_without_publication(env, monkeypatch):
    engine, service = env["platform"][1], env["service"]
    initial = anchor(env)
    original = service.reader.get_model_assessment
    with clock_view(engine, initial) as clock:
        submit(env)
        claim = service.claim(env["token"])
        identity_before = service.reader.get_case_context(
            env["users"]["admin"], env["case"]
        ).snapshot

        def step_back(*args, **kwargs):
            clock[0] = initial - timedelta(seconds=2)
            return original(*args, **kwargs)

        monkeypatch.setattr(service.reader, "get_model_assessment", step_back)
        with pytest.raises(ClockUnavailable, match="^snapshot_clock_unavailable$"):
            service.assemble(env["token"], claim)
        assert rows(engine, InvestigationPacket) == 0
        clock[0] = initial
        monkeypatch.setattr(service.reader, "get_model_assessment", original)
        assert (
            service.reader.get_case_context(env["users"]["admin"], env["case"]).snapshot
            == identity_before
        )
        body = service.assemble(env["token"], claim)
        with Session(engine) as session:
            expected_total = session.scalar(
                select(func.sum(EvidenceTransaction.amount)).where(
                    EvidenceTransaction.currency == "USD",
                    EvidenceTransaction.event_at >= env["bundle"].window_start,
                    EvidenceTransaction.event_at < env["bundle"].as_of,
                )
            )
        assert body.facts[0].result.observed_total == expected_total
        changed = body.facts[0].model_copy(
            update={
                "result": body.facts[0].result.model_copy(
                    update={"observed_total": expected_total + Decimal(1)}
                )
            }
        )
        tampered = body.model_copy(update={"facts": [changed, *body.facts[1:]]})
        audit_before = rows(engine, AuditEvent)
        with pytest.raises(VerificationFailed, match="^investigation_verification_failed$"):
            service.complete(env["token"], claim, tampered)
        assert rows(engine, InvestigationPacket) == 0
        assert rows(engine, AuditEvent) == audit_before


def test_future_signed_expiry_is_rejected_without_assertion_relaxation(env):
    initial = anchor(env)
    with clock_view(env["platform"][1], initial):
        _, request = snapshot(env)
        claims = jwt.decode(request.snapshot, options={"verify_signature": False})
        forged = env["service"].reader._sign(
            {k: v for k, v in claims.items() if k not in {"iss", "aud"}}
            | {"expires": claims["expires"] + 1}
        )
        with pytest.raises(ReadInvalid):
            read(env, TransactionRequest(snapshot=forged))


@pytest.mark.parametrize("change", ["source", "role"])
def test_clock_restoration_cannot_restore_revoked_authority(env, change):
    initial = anchor(env)
    with clock_view(env["platform"][1], initial) as clock:
        _, request = snapshot(env)
        clock[0] = initial - timedelta(seconds=2)
        with pytest.raises(ClockUnavailable):
            read(env, request)
        clock[0] = initial
        with pytest.raises(ReadInvalid):
            read(env, request)
        _, request = snapshot(env)
        if change == "source":
            env["foundation"].set_source_access(
                env["users"]["admin"], env["case"], env["source"], False
            )
            with pytest.raises(SnapshotStale):
                read(env, request)
        else:
            from app.models import User

            with Session(env["platform"][1]) as session, session.begin():
                session.get(User, env["users"]["admin"]).active = False
            with pytest.raises(EvidenceNotFound):
                read(env, request)
        assert rows(env["platform"][1], InvestigationPacket) == 0


def test_forged_reference_remains_rejected_at_valid_clock(env):
    engine, service = env["platform"][1], env["service"]
    with clock_view(engine, anchor(env)):
        submit(env)
        claim = service.claim(env["token"])
        body = service.assemble(env["token"], claim)
        forged = body.evidence[0].model_copy(update={"record_version_id": uuid4()})
        body = body.model_copy(update={"evidence": [forged, *body.evidence[1:]]})
        with pytest.raises(VerificationFailed):
            service.complete(env["token"], claim, body)
        assert rows(engine, InvestigationPacket) == 0


def test_wall_clock_rewind_cannot_revalidate_previously_expired_snapshot(env):
    """An independent committed floor and epoch survive the expired-read rollback."""
    initial = anchor(env)
    with clock_view(env["platform"][1], initial) as clock:
        _, request = snapshot(env)
        clock[0] = initial + timedelta(seconds=SNAPSHOT_SECONDS)
        with pytest.raises(ReadInvalid):
            read(env, request)
        clock[0] = initial + timedelta(seconds=SNAPSHOT_SECONDS - 1)
        with pytest.raises(ClockUnavailable):
            read(env, request)
        clock[0] = initial + timedelta(seconds=SNAPSHOT_SECONDS + 1)
        with pytest.raises(ReadInvalid):
            read(env, request)
        assert rows(env["platform"][1], InvestigationPacket) == 0


def test_worker_retries_snapshot_rejection_and_publishes_once_after_clock_restoration(
    env, monkeypatch
):
    engine, service = env["platform"][1], env["service"]
    initial = anchor(env)
    original = service.reader.get_model_assessment
    with clock_view(engine, initial) as clock:
        submit(env)

        def step_back(*args, **kwargs):
            clock[0] = initial - timedelta(seconds=2)
            return original(*args, **kwargs)

        monkeypatch.setattr(service.reader, "get_model_assessment", step_back)
        failed = service.run_once(env["token"])
        assert failed["status"] == "pending"
        assert failed["error_code"] == "processing_unavailable"
        assert failed["human_review_required"] is True
        assert rows(engine, InvestigationPacket) == 0
        monkeypatch.setattr(service.reader, "get_model_assessment", original)
        clock[0] = initial + timedelta(seconds=3)
        result = service.run_once(env["token"])
        assert result["status"] == "succeeded" and result["attempts"] == 2
        assert rows(engine, InvestigationPacket) == 1
        assert service.run_once(env["token"]) is None
        assert rows(engine, InvestigationPacket) == 1


def test_backward_clock_cannot_revive_a_fenced_worker_claim(env):
    engine, service = env["platform"][1], env["service"]
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        submit(env)
        old = service.claim(env["token"])
        body = service.assemble(env["token"], old)
        clock[0] = initial + timedelta(seconds=61)
        assert service.recover(env["token"]) == 1
        clock[0] = initial + timedelta(seconds=64)
        new = service.claim(env["token"])
        assert new.lease_token != old.lease_token
        clock[0] = initial
        with pytest.raises(InvestigationLeaseLost):
            service.complete(env["token"], old, body)
        assert rows(engine, InvestigationPacket) == 0
        clock[0] = initial + timedelta(seconds=64)
        service.complete(env["token"], new, service.assemble(env["token"], new))
        assert rows(engine, InvestigationPacket) == 1
