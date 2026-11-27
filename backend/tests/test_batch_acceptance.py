"""Phase 2.10.6 cross-stage invariants; original component fault tests remain authoritative."""

import csv
import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

import pytest
import test_batch_assessments as batch_tests
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from test_batch_assessments import advance, imported, start
from test_csv_imports import total
from test_csv_staging import send
from test_csv_validation import data

from app.models import Alert, Assessment, AssessmentJob, Case, CSVUpload, Decision

base_upload = batch_tests.base_upload
import_fixture = batch_tests.import_fixture
batch_env = batch_tests.batch_env


def test_default_5000_row_limit_fails_before_canonical_work(base_upload):
    env = base_upload
    assert env["settings"].csv_max_rows == 2000
    response = send(env, data([{} for _ in range(5000)]), key="acceptance-large-file-5000")
    assert response.status_code == 413
    for model in (CSVUpload, Alert, Case, AssessmentJob, Assessment, Decision):
        assert total(env, model) == 0
    root = env["settings"].csv_staging_root
    assert not root.exists() or not list(root.iterdir())


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="real approved Linux RF/SHAP/PostgreSQL",
)
def test_cross_stage_conflict_reuse_rejection_history_export_and_replay(batch_env, caplog):
    from app.workers.assessment_worker import AssessmentWorker

    env = batch_env
    original = imported(env, [{}, {"income": "0"}, {"income": "=SYNTHETIC_CELL_CANARY()"}])
    assert original["created_rows"] == 2 and original["excluded_rows"] == 1
    again = imported(
        env, [{"totalSpend90d": "999"}, {"income": "0"}, {"income": "=SYNTHETIC_CELL_CANARY()"}]
    )
    assert again["conflict_rows"] == again["reused_rows"] == again["excluded_rows"] == 1
    assert again["processed_rows"] == 3 and again["created_rows"] == 0
    assert total(env, Case) == total(env, Alert) == 2 and total(env, AssessmentJob) == 0
    requested = start(env, again, key="acceptance-full-pipeline-key", policy="Coverage")
    assert requested.status_code == 202
    bid = requested.json()["batch_id"]
    assert advance(env, bid).total_cases == 1
    assert AssessmentWorker(env["ml"], env["ml_token"]).run_once()["status"] == "succeeded"
    path = requested.headers["location"]
    progress = env["client"].get(path, headers=env["auth"]).json()
    assert (
        progress["status"] == "completed" and progress["succeeded"] == progress["total_cases"] == 1
    )
    results = env["client"].get(path + "/results", headers=env["auth"]).json()
    row = results["items"][0]
    value = row["assessment"]
    assert results["total"] == 1 and row["source_row_number"] == 3
    assert value["model_sha256"] == progress["model_sha256"]
    assert value["policy_version"] == progress["policy_version"]
    assert value["input_provenance"]["feature_contract_version"] == "datarobot_provisional_v1"
    assert (
        value["explanation"]["status"] == "verified" and len(value["explanation"]["features"]) == 27
    )
    assert (
        abs(
            value["explanation"]["base_value"]
            + sum(f["contribution"] for f in value["explanation"]["features"])
            - value["score"]
        )
        <= 1e-6
    )
    cid = row["case_id"]
    history = env["client"].get(f"/api/v1/cases/{cid}/assessments", headers=env["auth"]).json()
    assert history["total"] == 1 and history["items"][0]["assessment_id"] == value["assessment_id"]
    overview = env["client"].get(f"/api/v1/cases/{cid}/overview", headers=env["auth"]).json()
    assert overview["assessment_status"] == "succeeded" and "features" not in overview
    exported = env["client"].get(path + "/export", headers=env["auth"])
    assert exported.status_code == 200
    export = next(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert export["case_id"] == cid and float(export["sar_positive_score"]) == value["score"]
    assert (
        export["recommendation"] == value["recommended_route"]
        and export["human_decision_required"] == "True"
    )
    assert not ({"income", "state", "source_id", "features"} & export.keys())
    replay = start(env, again, key="acceptance-full-pipeline-key", policy="Coverage")
    assert replay.json()["batch_id"] == bid
    assert total(env, Assessment) == total(env, AssessmentJob) == total(env, Decision) == 1
    with Session(env["engine"]) as session:
        case = session.get(Case, UUID(cid))
        assert case.status == "open" and case.disposition is None
        assert session.get(Alert, case.alert_id).features["income"] == 0
        assert session.get(Alert, case.alert_id).source_id == "preview-synthetic-1"
        # Original conflicting source is untouched and has no job.
        alert = session.scalar(select(Alert).where(Alert.source_id == "preview-synthetic-0"))
        assert alert.features["totalSpend90d"] == 0
    assert "SYNTHETIC_CELL_CANARY" not in caplog.text
    assert "SYNTHETIC_CELL_CANARY" not in results.__repr__() + exported.text


@pytest.mark.skipif(
    sys.platform != "linux" or os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="real Linux scientific child SIGKILL and verified restart",
)
@pytest.mark.parametrize("stage", ["rf", "shap"])
def test_real_scientific_stage_kill_recovers_without_partial_result(
    batch_env, monkeypatch, tmp_path, stage
):
    """Kill after the actual stage returns, before its result can be published; never fake success."""
    import subprocess

    from app.workers.assessment_worker import AssessmentWorker

    env = batch_env
    batch = start(env, imported(env, [{"income": "0"}])).json()
    advance(env, batch["batch_id"])
    worker = AssessmentWorker(env["ml"], env["ml_token"])
    marker = tmp_path / "scientific-stage-ready"
    program = r"""
import sys,time
from pathlib import Path
from trueflag_ml.scoring import RFScoringService
from trueflag_ml.explainability import ExplanationService
from app.workers.assessment_child import main
target,method=(RFScoringService,'score_one') if sys.argv[3]=='rf' else (ExplanationService,'explain_one')
original=getattr(target,method)
def gate(*args,**kwargs):
    result=original(*args,**kwargs)
    assert (result.processing_status=='processed') if sys.argv[3]=='rf' else (result.status=='verified')
    Path(sys.argv[2]).write_text('actual-stage-completed')
    while True:time.sleep(.05)
setattr(target,method,gate)
raise SystemExit(main())
"""
    children = []
    original_spawn = subprocess.Popen

    def spawn(*args, **kwargs):
        process = original_spawn(*args, **kwargs)
        children.append(process)
        return process

    with monkeypatch.context() as patch:
        patch.setattr(
            worker.runner,
            "_command",
            lambda: [sys.executable, "-B", "-c", program, str(os.getpid()), str(marker), stage],
        )
        patch.setattr(subprocess, "Popen", spawn)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(worker.run_once)
            deadline = time.monotonic() + 20
            while not marker.exists() and not future.done() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert marker.exists() and len(children) == 1
            children[0].kill()
            failed = future.result(timeout=10)
    assert failed["status"] == "pending" and failed["failure_code"] == "child_failed"
    assert total(env, Assessment) == total(env, Decision) == 0
    with env["engine"].begin() as connection:
        connection.execute(
            text(
                "UPDATE assessment_jobs SET available_at=clock_timestamp()-interval '1 second' WHERE status='pending'"
            )
        )
    assert AssessmentWorker(env["ml"], env["ml_token"]).run_once()["status"] == "succeeded"
    status = env["batch"].get(env["actor_id"], UUID(batch["batch_id"]))
    assert status.succeeded == 1 and status.failed_manual_review == 0
    assert total(env, Assessment) == total(env, Decision) == total(env, AssessmentJob) == 1
    with Session(env["engine"]) as session:
        job = session.scalar(select(AssessmentJob))
        case = session.get(Case, job.case_id)
        assert job.attempts == 2 and case.status == "open" and case.disposition is None
