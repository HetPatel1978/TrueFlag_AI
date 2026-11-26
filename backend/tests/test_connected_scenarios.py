"""Real PostgreSQL authorized connected evidence; actual RF/Policy/SHAP Linux worker."""

import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_snapshot_clock_integrity import clock_view

from app.models import Alert, Assessment, AssessmentJob, AuditEvent, Case
from app.models.evidence import EvidenceCaseBinding, EvidenceSourceVersion
from app.models.investigations import InvestigationPacket
from app.schemas.evidence_read import (
    AnalyticsRequest,
    CustomerRequest,
    RelatedRequest,
    TransactionRequest,
)
from app.schemas.investigations import InvestigationRequest
from app.services.connected_scenarios import (
    CATALOG,
    ConnectedScenarioService,
    expected_activity,
    scenario_bundle,
)
from app.services.evidence import EvidenceBlocked, EvidenceNotFound
from app.services.evidence_read import SnapshotStale
from app.services.investigation_coordinator import InvestigationCoordinator
from app.services.investigation_verifier import VerificationFailed
from app.services.snapshot_clock import ClockUnavailable
from app.workers.assessment_worker import AssessmentWorker

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture


@pytest.fixture
def connected(platform, evidence_setup):
    _, users = evidence_setup
    engine = platform[1]
    with engine.connect() as c:
        cluster = str(c.scalar(text("SELECT system_identifier FROM pg_control_system()")))
        database = c.scalar(text("SELECT current_database()"))
    if not database.startswith("tf_g0_3_primary_"):
        pytest.skip(
            "Explicitly isolated rehearsal database required; production target guard remains enforced"
        )
    service = ConnectedScenarioService(
        engine,
        platform[2],
        development=True,
        expected_cluster=cluster,
        forbidden_cluster="not-this-test-cluster",
        expected_database=database,
    )
    return service, users


@pytest.mark.parametrize("spec", CATALOG, ids=lambda s: s.key)
def test_actual_connected_case_assessment_analytics_and_verified_packet(platform, connected, spec):
    if os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1":
        pytest.skip("Pinned Linux actual-artifact worker required")
    service, users = connected
    actor = users["admin"]
    receipt = service.apply(actor, spec.key)
    case = UUID(receipt["case_id"])
    token = secrets.token_hex(32)
    service.queue.register_worker(admin_id=actor, name="g1-real-worker", token=token)
    result = AssessmentWorker(service.queue, token).run_once()
    assert result["status"] == "succeeded"
    job = service.queue.get(actor_id=actor, case_id=case, job_id=UUID(receipt["job"]["job_id"]))
    assessment = UUID(job["assessment_id"])
    stored = service.queue.assessments.get(actor_id=actor, case_id=case, assessment_id=assessment)
    assert stored["explanation"]["status"] == "verified"
    assert len(stored["explanation"]["features"]) == 27
    observed = service.verify_activity(actor, spec.key, case)
    bundle = scenario_bundle(spec.key)
    context = service.reader.get_case_context(actor, case, assessment)
    snapshot = context.data.snapshot_token
    for currency in observed:
        oracle = expected_activity(bundle, currency=currency)
        for calculation in ("velocity", "concentration"):
            query = AnalyticsRequest(
                snapshot=snapshot,
                calculation=calculation,
                currency=currency,
                window={"start": bundle.window_start, "end": bundle.as_of},
            )
            output = service.reader.calculate_activity(actor, case, query).data
            assert output.observed_count == oracle["count"]
            if calculation == "velocity":
                assert sum(b.observed_count for b in output.buckets) == oracle["count"]
                assert {
                    b.window.start.date().isoformat(): b.observed_count
                    for b in output.buckets
                    if b.observed_count
                } == oracle["daily_counts"]
            else:
                assert sorted(Decimal(v) for v in oracle["counterparties"].values()) == sorted(
                    p.observed_total for p in output.concentration
                )
        if spec.key == "corrections":
            query = query.model_copy(
                update={"calculation": "count_totals", "treatment": "exclude_verified_reversals"}
            )
            net = service.reader.calculate_activity(actor, case, query).data
            expected = expected_activity(bundle, net=True)
            assert net.observed_count == expected["count"] and net.observed_total == Decimal(
                expected["total"]
            )
            assert net.verified_reversal_pairs_excluded == 1
    # Customer/account reads use the same current case snapshot and authorized boundary.
    customers = service.reader.get_customer_context(actor, case, CustomerRequest(snapshot=snapshot))
    related = service.reader.get_related_evidence(actor, case, RelatedRequest(snapshot=snapshot))
    assert customers.data.total >= 1 and related.data.total >= 3
    coordinator = InvestigationCoordinator(platform[1], platform[2])
    itoken = secrets.token_urlsafe(48)
    coordinator.register_worker(actor, "g1-packet-worker", itoken)
    request = InvestigationRequest(
        expected_case_version=context.snapshot.case_version,
        expected_evidence_revision=context.snapshot.evidence_revision,
        expected_access_revision=context.snapshot.access_revision,
        assessment_id=assessment,
        window={"start": bundle.window_start, "end": bundle.as_of},
        currencies=tuple(observed),
    )
    run = coordinator.request(actor, case, "g1_packet_request", request)
    claim = coordinator.claim(itoken)
    assembled = coordinator.assemble(itoken, claim)
    if spec.key == "multi_currency":
        # Later-currency references AND amounts must be checked after concentration sorting.
        for invalid_fact in (
            assembled.facts[2].model_copy(update={"input_record_ids": [uuid4()]}),
            assembled.facts[2].model_copy(
                update={
                    "result": assembled.facts[2].result.model_copy(
                        update={
                            "observed_total": assembled.facts[2].result.observed_total + Decimal(1)
                        }
                    )
                }
            ),
        ):
            bad = assembled.model_copy(
                update={"facts": assembled.facts[:2] + [invalid_fact] + assembled.facts[3:]}
            )
            with pytest.raises(VerificationFailed):
                coordinator.complete(itoken, claim, bad)
    assert coordinator.complete(itoken, claim, assembled)["status"] in {"succeeded", "abstained"}
    packet = coordinator.get(actor, case, UUID(run["run_id"]))
    assert packet["packet"]["model_signal"]["score"] == stored["score"]["score"]
    assert packet["verification"]["human_semantic_review_required"]
    assert packet["packet"]["regulatory_citations"] == []
    with Session(platform[1]) as session:
        case_row = session.get(Case, case)
        binding = session.get(EvidenceCaseBinding, case)
        assert str(binding.source_id) == receipt["source_id"]
        assert (
            session.get(Alert, case_row.alert_id).features
            == scenario_bundle(spec.key, revision=1).declarations
        )
        assert case_row.status == "open" and case_row.disposition is None
        assert session.scalar(select(func.count()).select_from(Assessment)) == 1
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "assessment.completed")
            )
            == 1
        )
        assert (
            session.scalar(select(func.count()).select_from(EvidenceSourceVersion)) == spec.revision
        )
    # Same deterministic run must return existing history, not reassess on rerun.
    again = service.apply(actor, spec.key)
    assert (
        again["case_id"] == receipt["case_id"]
        and again["job"]["assessment_id"] == job["assessment_id"]
    )


def test_duplicate_concurrent_setup_and_unauthorized_actor(platform, connected):
    service, users = connected
    with pytest.raises(EvidenceNotFound):
        service.apply(users["analyst"], "ordinary")
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: service.apply(users["admin"], "ordinary"), range(3)))
    assert len({r["case_id"] for r in results}) == len({r["job"]["job_id"] for r in results}) == 1
    with Session(platform[1]) as session:
        assert session.scalar(select(func.count()).select_from(Case)) == 1
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 1


def test_cross_case_forged_accounts_revocation_and_stale_revision(platform, connected):
    service, users = connected
    actor = users["admin"]
    one = service.apply(actor, "source_revocation")
    two = service.apply(actor, "source_revision")
    first, second = UUID(one["case_id"]), UUID(two["case_id"])
    context = service.reader.get_case_context(actor, first)
    other = service.reader.get_case_context(actor, second)
    with pytest.raises(EvidenceNotFound):
        service.reader.get_transactions(
            users["analyst"], first, TransactionRequest(snapshot=context.data.snapshot_token)
        )
    with pytest.raises(EvidenceNotFound):
        service.reader.get_transactions(
            actor, second, TransactionRequest(snapshot=context.data.snapshot_token)
        )
    with pytest.raises(EvidenceNotFound):
        service.reader.get_transactions(
            actor,
            first,
            TransactionRequest(snapshot=context.data.snapshot_token, account_handle=uuid4()),
        )
    assert not set(context.data.account_handles) & set(other.data.account_handles)
    service.revoke_source(actor, "source_revocation", first)
    with pytest.raises(SnapshotStale):
        service.reader.get_transactions(
            actor, first, TransactionRequest(snapshot=context.data.snapshot_token)
        )
    with pytest.raises(EvidenceBlocked):
        service.verify_activity(actor, "ordinary", second)


def test_clock_uncertainty_prevents_scenario_writes(platform, connected):
    service, users = connected
    engine = platform[1]
    # Seed one valid durable observation, then deliberately move only this test's DB clock view.
    with engine.connect() as c:
        initial = c.scalar(text("SELECT clock_timestamp()"))
    with clock_view(engine, initial) as clock:
        service.gate(users["admin"])
        clock[0] = initial - timedelta(seconds=2)
        with pytest.raises(ClockUnavailable):
            service.apply(users["admin"], "ordinary")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Case)) == 0


def test_target_guard_rejects_live_identity_and_wrong_database(platform):
    with pytest.raises(EvidenceBlocked):
        ConnectedScenarioService(
            platform[1],
            platform[2],
            development=True,
            expected_cluster="1",
            forbidden_cluster="1",
            expected_database="tf_g0_3_primary_test",
        )
    with pytest.raises(EvidenceBlocked):
        ConnectedScenarioService(
            platform[1],
            platform[2],
            development=False,
            expected_cluster="1",
            forbidden_cluster="2",
            expected_database="trueflag",
        )


def test_worker_identity_reuse_never_rotates_or_reactivates(connected):
    service, users = connected
    actor = users["admin"]
    token = secrets.token_hex(32)
    identity = service.ensure_worker(actor, token)
    assert service.ensure_worker(actor, token) == identity
    with pytest.raises(EvidenceBlocked):
        service.ensure_worker(actor, secrets.token_hex(32))
    service.queue.revoke_worker(admin_id=actor, worker_id=identity)
    with pytest.raises(EvidenceBlocked):
        service.ensure_worker(actor, token)


def test_revision_invalidates_old_snapshot_without_replacing_original_alert(connected):
    service, users = connected
    actor = users["admin"]
    initial = scenario_bundle("source_revision", revision=1)
    source = service.foundation.register_source(actor, initial.scenario_id)
    version = service.foundation.admit_version(actor, source, initial)
    case = service.foundation.create_case(actor, version)
    context = service.reader.get_case_context(actor, case)
    result = service.apply(actor, "source_revision")
    assert UUID(result["case_id"]) == case
    with pytest.raises(SnapshotStale):
        service.reader.get_transactions(
            actor, case, TransactionRequest(snapshot=context.data.snapshot_token)
        )
