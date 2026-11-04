"""Real PostgreSQL evidence acceptance. Synthetic-only; no model success mocks."""

import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from conftest import BACKEND
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from app.models import Alert, AssessmentJob, Case, Evidence, User
from app.models.evidence import (
    EVIDENCE_TABLES,
    CaseEvidenceLink,
    EvidenceCaseBinding,
    EvidenceCustomer,
    EvidenceRecordVersion,
    EvidenceSourceVersion,
    EvidenceTransaction,
)
from app.services.evidence import (
    EvidenceBlocked,
    EvidenceConflict,
    EvidenceNotFound,
    EvidenceService,
    EvidenceUnavailable,
)
from app.services.ingestion import digest
from app.services.synthetic_evidence import generate_scenario

pytestmark = pytest.mark.postgres


@pytest.fixture
def evidence_setup(platform):
    engine = platform[1]
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL evidence constraints/locks required")
    with Session(engine) as session:
        users = {u.username: u.id for u in session.scalars(select(User))}
    service = EvidenceService(engine)
    return service, users


def admit(service, actor, profile="normal", *, seed=17):
    bundle = generate_scenario(uuid4(), seed, profile)
    source = service.register_source(actor, bundle.scenario_id)
    release = service.admit_version(actor, source, bundle)
    return bundle, source, release


def count(engine, model):
    with Session(engine) as session:
        return session.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize(
    "profile,coverage",
    [
        ("normal", "complete_declared_window"),
        ("partial", "partial"),
        ("unavailable", "unavailable"),
        ("timezone_unknown", "partial"),
        ("timezone_offsets", "complete_declared_window"),
        ("multi_currency", "complete_declared_window"),
        ("inconsistent_kyc", "complete_declared_window"),
    ],
)
def test_new_case_exact_linkage_coverage_and_safe_manifest(
    platform, evidence_setup, profile, coverage
):
    service, users = evidence_setup
    actor = users["admin"]
    bundle, source, release = admit(service, actor, profile)
    case_id = service.create_case(actor, release)
    assert service.create_case(actor, release) == case_id
    manifest = service.manifest(actor, case_id)
    assert manifest["coverage"] == coverage
    assert (manifest["evidence_revision"], manifest["access_revision"]) == (1, 2)
    assert len(manifest["sources"]) == 1
    assert "annual_income" not in json.dumps(manifest)
    assert '"declarations"' not in json.dumps(manifest)
    flags = manifest["sources"][0]["quality_flags"]
    assert flags["unknown_transaction_timezone"] is (profile == "timezone_unknown")
    assert flags["multiple_transaction_currencies"] is (profile == "multi_currency")
    assert flags["multiple_kyc_observations"] is (profile == "inconsistent_kyc")
    with Session(platform[1]) as session:
        case = session.get(Case, case_id)
        assert case.status == "open" and case.disposition is None
        assert session.get(Alert, case.alert_id).features == bundle.declarations
        assert session.get(EvidenceCaseBinding, case_id).source_id == source
        assert session.scalar(select(func.count()).select_from(AssessmentJob)) == 0
    service.link_version(actor, case_id, release)
    assert service.manifest(actor, case_id)["evidence_revision"] == 1


def test_corrections_keep_previous_history_and_contradictions(platform, evidence_setup):
    service, users = evidence_setup
    actor = users["admin"]
    bundle, source, first = admit(service, actor, "corrections")
    case_id = service.create_case(actor, first)
    initial = service.manifest(actor, case_id)
    second_bundle = generate_scenario(
        bundle.scenario_id, bundle.seed, bundle.profile, source_revision=2
    )
    second = service.admit_version(actor, source, second_bundle)
    assert service.manifest(actor, case_id)["evidence_revision"] == 1
    service.link_version(actor, case_id, second)
    current = service.manifest(actor, case_id)
    assert current["evidence_revision"] == 2 and current["access_revision"] == 3
    assert len(current["records"]) == 2 * len(initial["records"]) == 34
    assert sum(r["superseded_in_manifest"] for r in current["records"]) == 17
    with Session(platform[1]) as session:
        assert session.scalar(select(func.count()).select_from(EvidenceTransaction)) == 26
        assert (
            session.get(Alert, session.get(Case, case_id).alert_id).features == bundle.declarations
        )


def test_missing_declaration_preserves_evidence_only_without_orphan_case(platform, evidence_setup):
    service, users = evidence_setup
    _, _, release = admit(service, users["admin"], "incomplete_features")
    with pytest.raises(EvidenceBlocked, match="incomplete_feature_support"):
        service.create_case(users["admin"], release)
    assert count(platform[1], EvidenceSourceVersion) == 1
    assert count(platform[1], Alert) == count(platform[1], Case) == 0


def test_corrected_declarations_flag_divergence_without_overwriting_rf_input(
    platform, evidence_setup
):
    service, users = evidence_setup
    actor = users["admin"]
    bundle, source, first = admit(service, actor, "missing_income")
    case_id = service.create_case(actor, first)
    correction = generate_scenario(
        bundle.scenario_id, bundle.seed, "zero_income", source_revision=2
    )
    second = service.admit_version(actor, source, correction)
    service.link_version(actor, case_id, second)
    manifest = service.manifest(actor, case_id)
    sources = {r["source_version_id"]: r for r in manifest["sources"]}
    assert sources[str(first)]["is_case_creation_release"] is True
    assert sources[str(first)]["case_input_reconciliation"] == "matches_declared_inputs"
    assert sources[str(second)]["case_input_reconciliation"] == "differs_from_immutable_case_input"
    with pytest.raises(EvidenceConflict, match="bound_case_input_conflict"):
        service.create_case(actor, second)
    with Session(platform[1]) as session:
        assert session.get(Alert, session.get(Case, case_id).alert_id).features["income"] is None
        assert session.scalar(select(func.count()).select_from(Case)) == 1


def test_revocation_replay_and_link_revocation_revisions(platform, evidence_setup):
    service, users = evidence_setup
    actor = users["admin"]
    _, source, release = admit(service, actor)
    case_id = service.create_case(actor, release)
    service.set_source_access(actor, case_id, source, False)
    service.set_source_access(actor, case_id, source, False)
    denied = service.manifest(actor, case_id)
    assert denied["records"] == denied["sources"] == []
    assert denied["coverage"] == "unavailable"
    assert (denied["evidence_revision"], denied["access_revision"]) == (1, 3)
    with pytest.raises(EvidenceNotFound):
        service.link_version(actor, case_id, release)
    service.set_source_access(actor, case_id, source, True)
    record = UUID(service.manifest(actor, case_id)["records"][0]["record_version_id"])
    service.revoke_links(actor, case_id, source, (record,))
    service.revoke_links(actor, case_id, source, (record,))
    partial = service.manifest(actor, case_id)
    assert partial["coverage"] == "partial"
    assert (partial["evidence_revision"], partial["access_revision"]) == (2, 5)


def test_case_source_isolation_role_and_assignment_revocation(platform, evidence_setup, case_team):
    service, users = evidence_setup
    actor = users["admin"]
    bundle, source, release = admit(service, actor)
    case_id = service.create_case(actor, release)
    _, other_source, other_release = admit(service, actor)
    other_case = service.create_case(actor, other_release)
    with pytest.raises(EvidenceNotFound):
        service.link_version(actor, other_case, release)
    with pytest.raises(EvidenceNotFound):
        service.set_source_access(actor, case_id, other_source, False)
    with pytest.raises(EvidenceNotFound):
        service.link_version(actor, UUID(case_team["ids"][0]), release)
    with pytest.raises(EvidenceNotFound):
        service.manifest(users["analyst"], case_id)
    with Session(platform[1]) as session, session.begin():
        session.get(Case, case_id).assigned_to = users["analyst"]
    assert service.manifest(users["analyst"], case_id)["records"]
    with pytest.raises(EvidenceNotFound):
        service.admit_version(users["analyst"], source, bundle)
    with pytest.raises(EvidenceNotFound):
        service.set_source_access(users["analyst"], case_id, source, False)
    with Session(platform[1]) as session, session.begin():
        session.get(Case, case_id).assigned_to = UUID(case_team["users"]["analysttwo"])
    with pytest.raises(EvidenceNotFound):
        service.manifest(users["analyst"], case_id)
    with Session(platform[1]) as session, session.begin():
        session.get(User, actor).role = "analyst"
    with pytest.raises(EvidenceNotFound):
        service.register_source(actor, uuid4())
    with pytest.raises(EvidenceNotFound):
        service.manifest(actor, case_id)


def test_other_admin_cannot_admit_or_bind_owned_source(platform, evidence_setup):
    service, users = evidence_setup
    bundle, source, release = admit(service, users["admin"])
    with Session(platform[1]) as session, session.begin():
        other = User(username="otheradmin", password_hash="test-disabled", role="admin")
        session.add(other)
        session.flush()
        other_id = other.id
    for operation in (
        lambda: service.admit_version(other_id, source, bundle),
        lambda: service.create_case(other_id, release),
    ):
        with pytest.raises(EvidenceNotFound):
            operation()


def test_concurrent_admission_and_case_creation_are_idempotent(platform, evidence_setup):
    service, users = evidence_setup
    actor = users["admin"]
    bundle = generate_scenario(uuid4(), 17)
    with ThreadPoolExecutor(max_workers=2) as pool:
        sources = list(
            pool.map(lambda _: service.register_source(actor, bundle.scenario_id), range(2))
        )
        assert sources[0] == sources[1]
        releases = list(
            pool.map(lambda _: service.admit_version(actor, sources[0], bundle), range(2))
        )
        assert releases[0] == releases[1]
        cases = list(pool.map(lambda _: service.create_case(actor, releases[0]), range(2)))
        assert cases[0] == cases[1]
    assert count(platform[1], EvidenceSourceVersion) == 1
    assert count(platform[1], Case) == count(platform[1], Alert) == 1


def test_conflicting_version_and_tampered_bundle_are_rejected(platform, evidence_setup):
    service, users = evidence_setup
    bundle, source, _ = admit(service, users["admin"])
    conflict = generate_scenario(bundle.scenario_id, 18)
    with pytest.raises(EvidenceConflict):
        service.admit_version(users["admin"], source, conflict)
    bundle.declarations["income"] = 999
    with pytest.raises(EvidenceBlocked, match="unsupported_synthetic_content"):
        service.admit_version(users["admin"], source, bundle)
    assert count(platform[1], EvidenceSourceVersion) == 1


def test_composite_source_fk_and_deferred_payload_release_integrity(platform, evidence_setup):
    service, users = evidence_setup
    actor = users["admin"]
    _, source, release_id = admit(service, actor)
    case_id = service.create_case(actor, release_id)
    _, _, other_release = admit(service, actor)
    with Session(platform[1]) as session:
        foreign = session.scalar(
            select(EvidenceRecordVersion).where(
                EvidenceRecordVersion.source_version_id == other_release
            )
        )
        foreign_id, foreign_kind = foreign.id, foreign.kind
    with pytest.raises(DBAPIError), Session(platform[1]) as session, session.begin():
        session.add(
            CaseEvidenceLink(
                case_id=case_id,
                record_version_id=foreign_id,
                source_id=source,
                kind=foreign_kind,
                changed_by=actor,
            )
        )
    with Session(platform[1]) as session:
        original = session.get(EvidenceSourceVersion, release_id)
        attributes = {
            c.name: getattr(original, c.name)
            for c in original.__table__.columns
            if c.name not in {"id", "version", "created_at", "content_sha256"}
        }
        member = session.scalar(
            select(EvidenceRecordVersion).where(
                EvidenceRecordVersion.source_version_id == release_id
            )
        )
        identity, kind, predecessor = member.identity_id, member.kind, member.id
    for add_record in (False, True):
        replacement = uuid4()
        values = {**attributes, "manifest": {"record_sha256": {"one": "0" * 64}}}
        with pytest.raises(DBAPIError), Session(platform[1]) as session, session.begin():
            session.add(
                EvidenceSourceVersion(id=replacement, version=2, content_sha256="1" * 64, **values)
            )
            session.flush()
            if add_record:
                session.add(
                    EvidenceRecordVersion(
                        id=uuid4(),
                        source_id=source,
                        source_version_id=replacement,
                        identity_id=identity,
                        kind=kind,
                        version=2,
                        content_sha256="0" * 64,
                        supersedes_id=predecessor,
                    )
                )
                # No typed payload: the deferred constraint must reject commit.
    assert count(platform[1], EvidenceSourceVersion) == 2


def test_database_disconnect_rolls_back_typed_admission(platform, evidence_setup, caplog):
    service, users = evidence_setup
    bundle = generate_scenario(uuid4(), 17)
    actor = users["admin"]
    source = service.register_source(actor, bundle.scenario_id)
    disconnected = False

    def terminate(connection, cursor, statement, parameters, context, many):
        nonlocal disconnected
        if not disconnected and statement.lower().startswith("insert into evidence_transactions"):
            disconnected = True
            pid = connection.scalar(text("SELECT pg_backend_pid()"))
            with platform[1].begin() as killer:
                assert killer.scalar(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})

    event.listen(platform[1], "before_cursor_execute", terminate)
    try:
        with pytest.raises(EvidenceUnavailable) as error:
            service.admit_version(actor, source, bundle)
        assert str(error.value) == "evidence_operation_unavailable"
    finally:
        event.remove(platform[1], "before_cursor_execute", terminate)
    assert disconnected
    assert count(platform[1], EvidenceSourceVersion) == count(platform[1], EvidenceTransaction) == 0
    assert all(
        r.alias not in caplog.text for r in bundle.records if r.kind in {"customer", "account"}
    )
    assert service.admit_version(actor, source, bundle)


def test_revocation_serializes_with_admission_commit(platform, evidence_setup):
    service, users = evidence_setup
    actor = users["admin"]
    bundle = generate_scenario(uuid4(), 17)
    source = service.register_source(actor, bundle.scenario_id)
    inserting, release, revoking = Event(), Event(), Event()

    def pause(connection, cursor, statement, parameters, context, many):
        if statement.lower().startswith("insert into evidence_source_versions"):
            inserting.set()
            assert release.wait(timeout=10)

    def revoke():
        revoking.set()
        with Session(platform[1]) as session, session.begin():
            user = session.scalar(select(User).where(User.id == actor).with_for_update())
            user.active = False

    event.listen(platform[1], "before_cursor_execute", pause)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            admission = pool.submit(service.admit_version, actor, source, bundle)
            assert inserting.wait(timeout=10)
            revocation = pool.submit(revoke)
            assert revoking.wait(timeout=5) and not revocation.done()
            release.set()
            assert admission.result(timeout=15)
            revocation.result(timeout=15)
    finally:
        release.set()
        event.remove(platform[1], "before_cursor_execute", pause)
    with pytest.raises(EvidenceNotFound):
        service.admit_version(actor, source, bundle)
    assert count(platform[1], EvidenceSourceVersion) == 1


@pytest.mark.parametrize(
    "profile,expected",
    [
        ("missing_income", None),
        ("zero_income", Decimal(0)),
        ("decimal_precision", Decimal("0.12345678")),
    ],
)
def test_exact_decimal_null_zero_and_currency_storage(platform, evidence_setup, profile, expected):
    service, users = evidence_setup
    _, _, release = admit(service, users["admin"], profile)
    case_id = service.create_case(users["admin"], release)
    assert service.manifest(users["admin"], case_id)["records"]
    with Session(platform[1]) as session:
        if profile == "decimal_precision":
            amounts = session.scalars(select(EvidenceTransaction.amount)).all()
            assert expected in amounts
        else:
            assert session.scalar(select(EvidenceCustomer.annual_income)) == expected


def test_audit_failure_rolls_back_all_admission_and_case_writes(platform, evidence_setup):
    service, users = evidence_setup
    actor = users["admin"]
    bundle = generate_scenario(uuid4(), 17)
    source = service.register_source(actor, bundle.scenario_id)
    with platform[1].begin() as connection:
        connection.execute(
            text("""CREATE FUNCTION reject_evidence_audit() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'private-marker'; END; $$""")
        )
        connection.execute(
            text("""CREATE TRIGGER reject_evidence_audit BEFORE INSERT ON audit_events
            FOR EACH ROW WHEN (NEW.action IN ('evidence.source_version_admitted','evidence.case_bound'))
            EXECUTE FUNCTION reject_evidence_audit()""")
        )
    with pytest.raises(EvidenceUnavailable) as error:
        service.admit_version(actor, source, bundle)
    assert str(error.value) == "evidence_operation_unavailable"
    assert (
        count(platform[1], EvidenceSourceVersion) == count(platform[1], EvidenceRecordVersion) == 0
    )
    with platform[1].begin() as connection:
        connection.execute(text("DROP TRIGGER reject_evidence_audit ON audit_events"))
        connection.execute(
            text("""CREATE TRIGGER reject_evidence_audit BEFORE INSERT ON audit_events
            FOR EACH ROW WHEN (NEW.action='evidence.case_bound') EXECUTE FUNCTION reject_evidence_audit()""")
        )
    release = service.admit_version(actor, source, bundle)
    with pytest.raises(EvidenceUnavailable):
        service.create_case(actor, release)
    assert (
        count(platform[1], Case)
        == count(platform[1], Alert)
        == count(platform[1], CaseEvidenceLink)
        == 0
    )


def test_immutable_history_audit_and_truncate_guards(platform, evidence_setup):
    service, users = evidence_setup
    _, _, release = admit(service, users["admin"])
    service.create_case(users["admin"], release)
    immutable = [
        t.name
        for t in EVIDENCE_TABLES
        if t.name not in {"case_evidence_states", "case_evidence_links", "evidence_source_access"}
    ]
    for table in immutable:
        column = (
            "id"
            if table
            not in {
                "evidence_customers",
                "evidence_accounts",
                "evidence_relationships",
                "evidence_transactions",
                "evidence_case_bindings",
            }
            else "case_id"
            if table == "evidence_case_bindings"
            else "record_version_id"
        )
        for statement in (
            f"UPDATE {table} SET {column}={column}",
            f"DELETE FROM {table}",
            f"TRUNCATE {table} CASCADE",
        ):
            with pytest.raises(DBAPIError), platform[1].begin() as connection:
                connection.execute(text(statement))
    for statement in (
        "DELETE FROM case_evidence_links",
        "DELETE FROM evidence_source_access",
        "UPDATE case_evidence_states SET evidence_revision=0",
        "UPDATE audit_events SET action='rewritten' WHERE action LIKE 'evidence.%'",
        "DELETE FROM audit_events WHERE action LIKE 'evidence.%'",
    ):
        with pytest.raises(DBAPIError), platform[1].begin() as connection:
            connection.execute(text(statement))


def test_upgrade_empty_rollback_preserves_legacy_and_rejects_destructive_rollback(
    platform, evidence_setup, case_team
):
    service, users = evidence_setup
    config = Config(str(BACKEND / "alembic.ini"))
    command.downgrade(config, "0011_batch_assessments")
    old_case_id = UUID(case_team["ids"][0])
    with Session(platform[1]) as session, session.begin():
        legacy = Evidence(
            case_id=old_case_id,
            source_uri="synthetic://legacy-only",
            content_sha256="0" * 64,
            source_kind="legacy",
            metadata_json={"unverified": True},
        )
        session.add(legacy)
    with Session(platform[1]) as session:
        before = digest([a.features for a in session.scalars(select(Alert).order_by(Alert.id))])
    command.upgrade(config, "head")
    assert {t.name for t in EVIDENCE_TABLES} <= set(inspect(platform[1]).get_table_names())
    assert service.manifest(users["admin"], old_case_id)["coverage"] == "unavailable"
    assert count(platform[1], Evidence) == 1
    assert count(platform[1], EvidenceCaseBinding) == 0
    with Session(platform[1]) as session:
        after = digest([a.features for a in session.scalars(select(Alert).order_by(Alert.id))])
    assert before == after
    command.check(config)
    # Even a manifest read audit is retained history; downgrade must refuse it.
    with pytest.raises(RuntimeError, match="Refusing to erase evidence"):
        command.downgrade(config, "0011_batch_assessments")


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1", reason="Pinned Linux RF/SHAP required"
)
@pytest.mark.parametrize("profile", ["missing_income", "zero_income"])
def test_new_scenario_existing_worker_scores_real_pipeline(platform, evidence_setup, profile):
    from app.services.assessment_jobs import AssessmentJobService, WorkerLimits
    from app.services.assessments import AssessmentService
    from app.workers.assessment_worker import AssessmentWorker
    from trueflag_ml.scoring import RFScoringService

    service, users = evidence_setup
    bundle, _, release = admit(service, users["admin"], profile)
    case_id = service.create_case(users["admin"], release)
    queue = AssessmentJobService(platform[1], limits=WorkerLimits(15, 60, 2))
    token = secrets.token_hex(32)
    queue.register_worker(admin_id=users["admin"], name="evidence-real-worker", token=token)
    accepted, _ = queue.enqueue(
        actor_id=users["admin"],
        case_id=case_id,
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="evidence-explicit-assessment",
        policy="Coverage",
    )
    assert accepted["status"] == "pending"
    completed = AssessmentWorker(queue, token).run_once()
    assert completed["status"] == "succeeded"
    result = AssessmentService(platform[1]).get(
        actor_id=users["admin"], case_id=case_id, assessment_id=UUID(completed["assessment_id"])
    )
    actual = RFScoringService().score_one(str(case_id), bundle.declarations)
    assert actual.score == result["score"]["score"] == result["explanation"]["model_score"]
    assert result["explanation"]["status"] == "verified"
    assert next(f for f in result["explanation"]["features"] if f["name"] == "income")[
        "missing"
    ] is (profile == "missing_income")
    with Session(platform[1]) as session:
        assert session.get(Case, case_id).status == "open"
        assert session.get(Case, case_id).disposition is None
