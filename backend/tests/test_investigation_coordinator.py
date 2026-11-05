"""PostgreSQL deterministic packets, raw-record verification, fencing and revocation."""

import json
import os
import secrets
import select as os_select
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from threading import Event
from uuid import uuid4

import pytest
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_evidence_foundation import admit
from test_evidence_foundation import evidence_setup as evidence_fixture

from alembic import command
from app.models import Alert, AuditEvent, Case, User
from app.models.investigations import InvestigationJob, InvestigationPacket, InvestigationRun
from app.schemas.investigations import InvestigationRequest
from app.services.evidence import EvidenceConflict, EvidenceNotFound, EvidenceUnavailable
from app.services.evidence_read import SnapshotStale
from app.services.investigation_coordinator import (
    InvestigationBusy,
    InvestigationCoordinator,
    InvestigationLeaseLost,
)
from app.services.investigation_verifier import VerificationFailed

evidence_setup = evidence_fixture


@pytest.fixture
def env(platform, evidence_setup):
    foundation, users = evidence_setup
    bundle, source, release = admit(foundation, users["admin"])
    case = foundation.create_case(users["admin"], release)
    service = InvestigationCoordinator(platform[1], platform[2])
    token = secrets.token_urlsafe(48)
    worker = service.register_worker(users["admin"], "evidence-worker", token)
    return dict(
        platform=platform,
        foundation=foundation,
        users=users,
        bundle=bundle,
        source=source,
        release=release,
        case=case,
        service=service,
        token=token,
        worker=worker,
    )


def request(env, **overrides):
    context = env["service"].reader.get_case_context(env["users"]["admin"], env["case"])
    fields = dict(
        expected_case_version=context.snapshot.case_version,
        expected_evidence_revision=context.snapshot.evidence_revision,
        expected_access_revision=context.snapshot.access_revision,
        without_assessment_reason="not_selected",
        window={"start": env["bundle"].window_start, "end": env["bundle"].as_of},
        currencies=("USD",),
    )
    fields.update(overrides)
    return InvestigationRequest(**fields)


def submit(env, key="investigation-key-001", **overrides):
    return env["service"].request(
        env["users"]["admin"], env["case"], key, request(env, **overrides)
    )


def view(env, receipt):
    from uuid import UUID

    return env["service"].get(env["users"]["admin"], env["case"], UUID(receipt["run_id"]))


def due(env):
    with env["platform"][1].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_jobs SET not_before=clock_timestamp()-interval '1 second' WHERE status='pending'"
            )
        )


def test_new_evidence_packet_exact_facts_provenance_and_no_case_action(env):
    receipt = submit(env)
    assert receipt["status"] == "pending"
    assert env["service"].run_once(env["token"])["status"] == "succeeded"
    result = view(env, receipt)
    packet = result["packet"]
    assert packet["mode"] == "deterministic_evidence_only" and not packet["provider_used"]
    assert packet["regulatory_citations"] == [] and packet["human_review_required"]
    assert len(packet["transactions"]) == 12 and len(packet["evidence"]) == 16
    fact = packet["facts"][0]["result"]
    assert fact["observed_count"] == 12
    assert Decimal(fact["observed_total"]) == sum(
        (t.amount for t in env["bundle"].records if t.kind == "transaction"), Decimal(0)
    )
    assert (
        packet["model_signal"] is None and "selected_model_assessment" in packet["missing_evidence"]
    )
    assert result["verification"]["transaction_count"] == 12
    assert result["verification"]["human_semantic_review_required"]
    with Session(env["platform"][1]) as session:
        run = session.get(InvestigationRun, __import__("uuid").UUID(receipt["run_id"]))
        serialized = json.dumps(run.input_manifest)
        assert (
            "snapshot_token" not in serialized
            and "annual_income" not in serialized
            and 'income"' not in serialized
        )
        assert run.input_manifest["snapshot"]["evidence_revision"] == 1
        assert session.get(Case, env["case"]).status == "open"
        assert session.get(Case, env["case"]).disposition is None
        assert (
            session.get(Alert, session.get(Case, env["case"]).alert_id).features
            == env["bundle"].declarations
        )
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.investigation.published")
            )
            == 1
        )


@pytest.mark.parametrize(
    "profile",
    [
        "partial",
        "unavailable",
        "timezone_unknown",
        "inconsistent_kyc",
        "multi_currency",
        "missing_income",
        "zero_income",
        "decimal_precision",
        "corrections",
    ],
)
def test_missing_conflicting_multicurrency_reversals_and_decimal_profiles(env, profile):
    bundle, source, release = admit(env["foundation"], env["users"]["admin"], profile)
    env.update(
        bundle=bundle,
        source=source,
        release=release,
        case=env["foundation"].create_case(env["users"]["admin"], release),
    )
    receipt = submit(env)
    outcome = env["service"].run_once(env["token"])
    assert outcome["status"] in {"succeeded", "abstained"}
    packet = view(env, receipt)["packet"]
    if profile in {
        "partial",
        "unavailable",
        "timezone_unknown",
        "inconsistent_kyc",
        "multi_currency",
    }:
        assert packet["outcome"] == "abstained"
    if profile == "unavailable":
        assert (
            packet["transactions"] == [] and packet["facts"][0]["result"]["observed_total"] is None
        )
    if profile == "inconsistent_kyc":
        assert "contradictory_kyc_observations" in packet["conflicts"]
    if profile == "timezone_unknown":
        assert any(t["event_at"] is None for t in packet["transactions"])


def test_legacy_aggregate_case_has_no_invented_transactions(env, case_team):
    from uuid import UUID

    env["case"] = UUID(case_team["ids"][0])
    receipt = submit(env)
    assert env["service"].run_once(env["token"])["status"] == "abstained"
    packet = view(env, receipt)["packet"]
    assert packet["transactions"] == packet["evidence"] == []
    assert all(f["result"]["observed_total"] is None for f in packet["facts"])


def test_idempotent_same_and_different_keys_without_unwanted_reruns(env):
    first = submit(env)
    assert submit(env) == first and submit(env, key="different-intent-key") == first
    with pytest.raises(EvidenceConflict):
        submit(env, currencies=("CAD",))
    env["service"].run_once(env["token"])
    assert submit(env)["run_id"] == first["run_id"]
    assert env["service"].run_once(env["token"]) is None


def test_concurrent_requests_and_worker_claims(env):
    with ThreadPoolExecutor(max_workers=2) as pool:
        receipts = list(pool.map(lambda _: submit(env), range(2)))
    assert receipts[0] == receipts[1]
    second_token = secrets.token_urlsafe(48)
    env["service"].register_worker(env["users"]["admin"], "second-evidence-worker", second_token)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(env["service"].claim, [env["token"], second_token]))
    assert sum(claim is not None for claim in claims) == 1


@pytest.mark.parametrize(
    "tamper", ["amount", "total", "reference", "context", "questions", "regulatory"]
)
def test_independent_validation_rejects_tampered_worker_output(env, tamper):
    submit(env)
    claim = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], claim)
    if tamper == "amount":
        body = body.model_copy(
            update={
                "transactions": [
                    body.transactions[0].model_copy(update={"amount": Decimal(999999)})
                ]
                + body.transactions[1:]
            }
        )
    if tamper == "total":
        body = body.model_copy(
            update={
                "facts": [
                    body.facts[0].model_copy(
                        update={
                            "result": body.facts[0].result.model_copy(
                                update={"observed_total": Decimal(1)}
                            )
                        }
                    )
                ]
                + body.facts[1:]
            }
        )
    if tamper == "reference":
        body = body.model_copy(
            update={
                "evidence": [body.evidence[0].model_copy(update={"record_version_id": uuid4()})]
                + body.evidence[1:]
            }
        )
    if tamper == "context":
        body = body.model_copy(
            update={"context": body.context.model_copy(update={"state": "closed"})}
        )
    if tamper == "questions":
        body = body.model_copy(update={"questions": ["File a SAR automatically"]})
    if tamper == "regulatory":
        body = body.model_copy(update={"regulatory_citations": ("unapproved-reference",)})
    with pytest.raises((VerificationFailed, EvidenceUnavailable)):
        env["service"].complete(env["token"], claim, body)
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 0


def test_producer_numeric_bug_cannot_self_verify(env, monkeypatch):
    submit(env)
    original = env["service"].reader.calculate_activity

    def wrong(*args):
        result = original(*args)
        return result.model_copy(
            update={"data": result.data.model_copy(update={"observed_total": Decimal(123)})}
        )

    monkeypatch.setattr(env["service"].reader, "calculate_activity", wrong)
    result = env["service"].run_once(env["token"])
    assert result["status"] == "failed" and result["error_code"] == "verification_failed"


@pytest.mark.parametrize("change", ["source", "role", "case"])
def test_revocation_and_stale_input_block_publication(env, change):
    receipt = submit(env)
    claim = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], claim)
    if change == "source":
        env["foundation"].set_source_access(
            env["users"]["admin"], env["case"], env["source"], False
        )
    else:
        with Session(env["platform"][1]) as session, session.begin():
            if change == "role":
                session.get(User, env["users"]["admin"]).active = False
            else:
                case = session.get(Case, env["case"])
                case.version += 1
                case.status = "in_review"
    with pytest.raises((SnapshotStale, EvidenceNotFound)):
        env["service"].complete(env["token"], claim, body)
    if change != "role":
        result = view(env, receipt)
        assert result["status"] == "invalidated" and result["packet"] is None
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 0


def test_result_hidden_after_evidence_revocation(env):
    receipt = submit(env)
    env["service"].run_once(env["token"])
    env["foundation"].set_source_access(env["users"]["admin"], env["case"], env["source"], False)
    result = view(env, receipt)
    assert result["status"] == "invalidated" and result["packet"] is None
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 1


def test_worker_authority_and_revocation(env):
    submit(env)
    with pytest.raises(EvidenceNotFound):
        env["service"].claim(secrets.token_urlsafe(48))
    claim = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], claim)
    env["service"].revoke_worker(env["users"]["admin"], env["worker"])
    with pytest.raises(EvidenceNotFound):
        env["service"].complete(env["token"], claim, body)
    alternate = secrets.token_urlsafe(48)
    env["service"].register_worker(env["users"]["admin"], "recovery-evidence-worker", alternate)
    assert env["service"].recover(alternate) == 1
    due(env)
    assert env["service"].run_once(alternate)["status"] == "succeeded"


def test_expired_lease_crash_recovery_and_stale_worker_fencing(env):
    receipt = submit(env)
    old = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], old)
    with env["platform"][1].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE run_id=:id"
            ),
            {"id": old.run_id},
        )
    assert env["service"].recover(env["token"]) == 1
    due(env)
    new = env["service"].claim(env["token"])
    assert old.lease_token != new.lease_token
    with pytest.raises(InvestigationLeaseLost):
        env["service"].complete(env["token"], old, body)
    env["service"].complete(env["token"], new, env["service"].assemble(env["token"], new))
    assert view(env, receipt)["attempts"] == 2


def test_restart_with_private_snapshot_signer_needs_no_api_signing_key(env):
    from pydantic import SecretStr

    receipt = submit(env)
    settings = env["platform"][2].model_copy(
        update={"jwt_secret": SecretStr(secrets.token_urlsafe(48))}
    )
    private = InvestigationCoordinator(env["platform"][1], settings)
    assert private.run_once(env["token"])["status"] == "succeeded"
    assert view(env, receipt)["packet"]["outcome"] == "packet_ready"


def test_worker_startup_errors_never_expose_configuration_diagnostics(monkeypatch, capsys):
    from types import SimpleNamespace

    import app.workers.investigation_worker as module

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "argv", ["investigation-worker", "--max-jobs", "1"])
    monkeypatch.setattr(
        module, "Path", lambda _: SimpleNamespace(read_text=lambda **kwargs: "x" * 48)
    )

    def unavailable(**kwargs):
        raise RuntimeError("synthetic_private_diagnostic")

    monkeypatch.setattr(module, "Settings", unavailable)
    with pytest.raises(SystemExit) as stopped:
        module.main()
    assert stopped.value.code == 1
    output = capsys.readouterr()
    assert "synthetic_private_diagnostic" not in output.out + output.err
    assert json.loads(output.out)["event"] == "investigation.worker.unavailable"


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux worker CLI required")
def test_real_worker_cli_uses_own_secret_and_no_api_jwt_key(env, tmp_path):
    receipt = submit(env)
    token_file = tmp_path / "investigation_token"
    token_file.write_text(env["token"], encoding="utf-8")
    token_file.chmod(0o600)
    environment = dict(os.environ)
    environment.pop("JWT_SECRET", None)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "app.workers.investigation_worker",
            "--token-file",
            str(token_file),
            "--max-jobs",
            "1",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=25,
    )
    assert result.returncode == 0
    outcome = json.loads(result.stdout)
    assert outcome["status"] == "succeeded" and outcome["human_review_required"]
    assert env["token"] not in result.stdout + result.stderr
    assert view(env, receipt)["packet"]["mode"] == "deterministic_evidence_only"


def test_bounded_retries_end_in_manual_review(env):
    receipt = submit(env)
    for attempt in range(3):
        claim = env["service"].claim(env["token"])
        result = env["service"].fail(env["token"], claim, "processing_unavailable", retryable=True)
        if attempt < 2:
            assert result["status"] == "pending"
            due(env)
    assert result["status"] == "failed" and result["human_review_required"]
    assert view(env, receipt)["packet"] is None


def test_publish_audit_database_failure_rolls_back_packet_and_job(env):
    submit(env)
    claim = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], claim)

    def fail(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO investigation_packets"):
            connection.exec_driver_sql("SELECT pg_terminate_backend(pg_backend_pid())")

    event.listen(env["platform"][1], "before_cursor_execute", fail)
    try:
        with pytest.raises(EvidenceUnavailable):
            env["service"].complete(env["token"], claim, body)
    finally:
        event.remove(env["platform"][1], "before_cursor_execute", fail)
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 0
        assert session.get(InvestigationJob, claim.run_id).status == "running"
    assert env["service"].complete(env["token"], claim, body)["status"] == "succeeded"


@pytest.mark.parametrize(
    "table", ["investigation_runs", "investigation_requests", "investigation_packets"]
)
def test_postgres_immutable_history(env, table):
    submit(env)
    env["service"].run_once(env["token"])
    for statement in [
        f"DELETE FROM {table}",
        f"UPDATE {table} SET "
        + ("run_id=run_id" if table == "investigation_requests" else "id=id"),
        f"TRUNCATE {table} CASCADE",
    ]:
        with pytest.raises(DBAPIError):
            with env["platform"][1].begin() as connection:
                connection.execute(text(statement))


def test_capacity_authorization_and_requester_isolation(env, case_team):
    from uuid import UUID

    service = InvestigationCoordinator(env["platform"][1], env["platform"][2], queue_capacity=1)
    receipt = submit(env)
    with pytest.raises(InvestigationBusy):
        service.request(
            env["users"]["admin"], env["case"], "new-intent-key", request(env, currencies=("CAD",))
        )
    with pytest.raises(EvidenceNotFound):
        service.get(UUID(case_team["users"]["analysttwo"]), env["case"], UUID(receipt["run_id"]))
    with pytest.raises(EvidenceNotFound):
        service.register_worker(
            UUID(case_team["users"]["analyst"]), "not-allowed-worker", secrets.token_urlsafe(48)
        )


def test_schema_drift_and_retained_downgrade(env):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.check(config)
    with pytest.raises(RuntimeError, match="retained investigation history"):
        command.downgrade(config, "0013_reference_corpus")


def test_empty_investigation_migration_roundtrip(platform):
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.downgrade(config, "0013_reference_corpus")
    command.upgrade(config, "head")
    if platform[1].dialect.name == "postgresql":
        command.check(config)


def test_assigned_analyst_scope_then_reassignment_blocks_result(env, case_team):
    from uuid import UUID

    actor = UUID(case_team["users"]["analyst"])
    with Session(env["platform"][1]) as session, session.begin():
        case = session.get(Case, env["case"])
        case.assigned_to = actor
        case.version += 1
    receipt = env["service"].request(actor, env["case"], "analyst-investigation", request(env))
    claim = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], claim)
    with Session(env["platform"][1]) as session, session.begin():
        case = session.get(Case, env["case"])
        case.assigned_to = UUID(case_team["users"]["analysttwo"])
        case.version += 1
    with pytest.raises(EvidenceNotFound):
        env["service"].complete(env["token"], claim, body)
    with pytest.raises(EvidenceNotFound):
        env["service"].get(actor, env["case"], UUID(receipt["run_id"]))


@pytest.mark.parametrize("stage", ["request", "publication"])
def test_audit_failure_rolls_back_all_consequential_writes(env, stage):
    query = request(env)
    if stage == "publication":
        submit(env)
        claim = env["service"].claim(env["token"])
        body = env["service"].assemble(env["token"], claim)

    def deny(connection, cursor, statement, parameters, context, many):
        if statement.startswith("INSERT INTO audit_events"):
            raise RuntimeError("must never expose private diagnostics")

    event.listen(env["platform"][1], "before_cursor_execute", deny)
    try:
        with pytest.raises(EvidenceUnavailable, match="^evidence_operation_unavailable$"):
            if stage == "request":
                env["service"].request(
                    env["users"]["admin"], env["case"], "rollback-request-key", query
                )
            else:
                env["service"].complete(env["token"], claim, body)
    finally:
        event.remove(env["platform"][1], "before_cursor_execute", deny)
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 0
        if stage == "request":
            assert session.scalar(select(func.count()).select_from(InvestigationRun)) == 0
            assert session.scalar(select(func.count()).select_from(InvestigationJob)) == 0
        else:
            assert session.get(InvestigationJob, claim.run_id).status == "running"


def test_revocation_serializes_with_atomic_publication(env, monkeypatch):
    import app.services.investigation_coordinator as module

    receipt = submit(env)
    claim = env["service"].claim(env["token"])
    body = env["service"].assemble(env["token"], claim)
    entered, release = Event(), Event()
    original = module.verify_packet

    def paused(*args):
        value = original(*args)
        entered.set()
        assert release.wait(1.5)
        return value

    monkeypatch.setattr(module, "verify_packet", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        publication = pool.submit(env["service"].complete, env["token"], claim, body)
        assert entered.wait(2)
        revocation = pool.submit(
            env["foundation"].set_source_access,
            env["users"]["admin"],
            env["case"],
            env["source"],
            False,
        )
        release.set()
        assert publication.result(timeout=5)["status"] == "succeeded"
        revocation.result(timeout=5)
    assert view(env, receipt)["packet"] is None


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux process death required")
def test_real_worker_process_death_then_restart_has_one_packet(env):
    receipt = submit(env)
    script = """
import json,sys,signal
def safe_exception(kind,value,traceback):
    print('CHILD_ERROR:'+kind.__name__,flush=True)
sys.excepthook=safe_exception
from app.core.config import Settings
from app.core.database import make_engine
from app.services.investigation_coordinator import InvestigationCoordinator
p=json.loads(sys.stdin.readline())
settings=Settings(database_url=p['database_url'],jwt_secret=p['jwt_secret'])
s=InvestigationCoordinator(make_engine(settings.database_url),settings)
c=s.claim(p['token']); original=s.reader.get_transactions
def paused(*args):
    result=original(*args)
    print('RETRIEVED',flush=True)
    signal.pause()
s.reader.get_transactions=paused
s.assemble(p['token'],c)
"""
    process = subprocess.Popen(
        [sys.executable, "-B", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    payload = dict(
        database_url=env["platform"][2].database_url,
        jwt_secret=env["platform"][2].jwt_secret.get_secret_value(),
        token=env["token"],
    )
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.close()
    try:
        ready, _, _ = os_select.select([process.stdout], [], [], 20)
        assert ready and process.stdout.readline().strip() == "RETRIEVED"
        process.kill()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
    with env["platform"][1].begin() as connection:
        connection.execute(
            text(
                "UPDATE investigation_jobs SET lease_until=clock_timestamp()-interval '1 second' WHERE status='running'"
            )
        )
    restarted = InvestigationCoordinator(env["platform"][1], env["platform"][2])
    assert restarted.recover(env["token"]) == 1
    due(env)
    assert restarted.run_once(env["token"])["status"] == "succeeded"
    assert view(env, receipt)["attempts"] == 2
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 1


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="pinned Linux real RF/SHAP required",
)
def test_real_stored_model_signal_is_bound_without_new_inference(env):
    from uuid import UUID

    from app.services.assessments import AssessmentService

    result, _ = AssessmentService(env["platform"][1]).assess(
        actor_id=env["users"]["admin"],
        case_id=env["case"],
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="investigation-real-model",
        policy="Coverage",
    )
    receipt = submit(
        env, assessment_id=UUID(result["assessment_id"]), without_assessment_reason=None
    )
    env["service"].run_once(env["token"])
    packet = view(env, receipt)["packet"]
    assert packet["model_signal"]["score"] == result["score"]["score"]
    assert packet["model_signal"]["explanation"]["status"] == "verified"
    assert packet["model_interpretation"] == "model_signal_not_fact_or_proof_of_crime"


@pytest.mark.parametrize(
    "override",
    [
        {"expected_case_version": True},
        {"expected_access_revision": -1},
        {"currencies": ("USD", "USD")},
        {"currencies": ("XXX",)},
        {"without_assessment_reason": None},
        {"regulatory_context_id": str(uuid4())},
        {"question_template": "file_a_sar"},
    ],
)
def test_strict_request_contract(override):
    from datetime import datetime, timezone

    fields = dict(
        expected_case_version=1,
        expected_evidence_revision=0,
        expected_access_revision=0,
        without_assessment_reason="not_selected",
        window={
            "start": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "end": datetime(2026, 1, 2, tzinfo=timezone.utc),
        },
        currencies=("USD",),
    )
    with pytest.raises(ValidationError):
        InvestigationRequest(**{**fields, **override})
