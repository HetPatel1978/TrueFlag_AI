"""Actual Linux/PostgreSQL/FastAPI/isolated-worker acceptance; no model-success mocks."""

import os
import secrets
import sys
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session
from test_assessments import counts

from app.models import Case
from app.services.assessment_jobs import AssessmentJobService, WorkerLimits
from app.workers.assessment_worker import AssessmentWorker

pytestmark = pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1",
    reason="Opt-in actual Linux RF/SHAP/PostgreSQL API acceptance",
)


def unseen(platform, case_team, alert_payload, income):
    assert sys.platform in {"linux", "win32"} and platform[1].dialect.name == "postgresql"
    alert_payload["source_id"] = "synthetic-api-unseen-" + uuid4().hex
    alert_payload["features"].update(state="QZ", income=income)
    field = next(
        f for f in alert_payload["features"] if f not in {"state", "income", "kycRiskScore"}
    )
    alert_payload["features"][field] = 37
    response = platform[0].post(
        "/api/v1/alerts",
        json=alert_payload,
        headers={**case_team["auth"]["admin"], "Idempotency-Key": str(uuid4())},
    )
    assert response.status_code == 201
    case_id = response.json()["case_id"]
    assignment = platform[0].put(
        f"/api/v1/cases/{case_id}/assignment",
        json={"expected_version": 1, "assigned_to": case_team["users"]["analyst"]},
        headers=case_team["auth"]["supervisor"],
    )
    assert assignment.status_code == 200
    queue = AssessmentJobService(platform[1], limits=WorkerLimits(15, 60, 2))
    token = secrets.token_hex(32)
    queue.register_worker(
        admin_id=UUID(case_team["users"]["admin"]), name="actual-api-worker", token=token
    )
    return case_id, queue, token


@pytest.mark.parametrize("income", [None, 0])
@pytest.mark.parametrize("policy", ["Efficiency", "Balanced", "Coverage"])
def test_actual_http_to_worker_and_verified_result(
    platform, case_team, alert_payload, income, policy
):
    from trueflag_ml.scoring import RFScoringService

    client = platform[0]
    case_id, queue, token = unseen(platform, case_team, alert_payload, income)
    path = f"/api/v1/cases/{case_id}/assessments"
    auth = case_team["auth"]["analyst"]
    body = {"expected_version": 2, "run_id": str(uuid4()), "policy": policy}
    headers = {**auth, "Idempotency-Key": "actual-async-api-request"}
    accepted = client.post(path, json=body, headers=headers)
    assert accepted.status_code == 202 and accepted.json()["status"] == "pending"
    job_url = accepted.headers["location"]
    assert client.get(job_url, headers=auth).json()["status"] == "pending"
    completed = AssessmentWorker(queue, token).run_once()
    assert completed["status"] == "succeeded"
    job = client.get(job_url, headers=auth)
    assert job.status_code == 200 and job.json()["assessment_id"] == completed["assessment_id"]
    detail = client.get(path + "/" + completed["assessment_id"], headers=auth)
    assert detail.status_code == 200
    value = detail.json()
    independently_scored = RFScoringService().score_one(case_id, alert_payload["features"])
    assert value["score"] == independently_scored.score
    assert value["selected_policy"] == policy
    assert value["policy_trace"]["threshold"] == (
        0.19088491043724937 if policy == "Efficiency" else 0.16040515630453706
    )
    explanation = value["explanation"]
    assert (
        explanation["status"] == "verified" and explanation["method"]["positive_class_label"] == 1
    )
    assert (
        abs(
            explanation["base_value"]
            + sum(f["contribution"] for f in explanation["features"])
            - value["score"]
        )
        <= 1e-6
    )
    assert next(f["missing"] for f in explanation["features"] if f["name"] == "income") is (
        income is None
    )
    assert explanation["verification"]["independent_model_and_root_checks"] is True
    assert value["input_provenance"]["hash_schema"] == "trueflag.explanation-input.rational.v1"
    assert value["human_decision_required"] is True
    assert client.get(path, headers=auth).json()["total"] == 1
    replay = client.post(path, json=body, headers=headers)
    assert replay.status_code == 202 and replay.json()["job_id"] == accepted.json()["job_id"]
    assert AssessmentWorker(queue, token).run_once() is None
    assert counts(platform[1]) == [1] * 5
    with Session(platform[1]) as session:
        case = session.get(Case, UUID(case_id))
        assert case.status == "open" and case.version == 2 and case.disposition is None


def test_actual_computation_cannot_publish_after_assignment_revoked(
    platform, case_team, alert_payload, monkeypatch
):
    client = platform[0]
    case_id, queue, token = unseen(platform, case_team, alert_payload, None)
    path = f"/api/v1/cases/{case_id}/assessments"
    response = client.post(
        path,
        json={"expected_version": 2, "run_id": str(uuid4()), "policy": "Coverage"},
        headers={**case_team["auth"]["analyst"], "Idempotency-Key": "actual-inflight-revocation"},
    )
    assert response.status_code == 202
    worker = AssessmentWorker(queue, token)
    actual = worker.runner.run

    def revoke_after_actual_computation(*args):
        result = actual(*args)
        # The real child completed, but the job is still Running and nothing is published.
        assert (
            client.get(response.headers["location"], headers=case_team["auth"]["analyst"]).json()[
                "status"
            ]
            == "running"
        )
        changed = client.put(
            f"/api/v1/cases/{case_id}/assignment",
            json={"expected_version": 2, "assigned_to": case_team["users"]["analysttwo"]},
            headers=case_team["auth"]["supervisor"],
        )
        assert changed.status_code == 200
        return result

    monkeypatch.setattr(worker.runner, "run", revoke_after_actual_computation)
    assert worker.run_once()["status"] == "failed"
    assert counts(platform[1]) == [0] * 5
    assert (
        client.get(response.headers["location"], headers=case_team["auth"]["analyst"]).status_code
        == 404
    )
    visible = client.get(response.headers["location"], headers=case_team["auth"]["analysttwo"])
    assert visible.status_code == 200 and visible.json()["fallback_route"] == "manual_review"


def test_actual_uvicorn_tcp_api_and_worker(platform, case_team, alert_payload):
    import socket
    import threading
    import time

    import httpx
    import uvicorn

    from app.main import create_app

    app = create_app(platform[2], platform[1])
    server = uvicorn.Server(
        uvicorn.Config(app, log_config=None, access_log=False, log_level="error")
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            threading.Event().wait(0.02)
        assert server.started
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=10) as client:
            network_platform = (client, *platform[1:])
            case_id, queue, token = unseen(network_platform, case_team, alert_payload, 0)
            path = f"/api/v1/cases/{case_id}/assessments"
            auth = case_team["auth"]["analyst"]
            accepted = client.post(
                path,
                json={"expected_version": 2, "run_id": str(uuid4()), "policy": "Balanced"},
                headers={**auth, "Idempotency-Key": "actual-tcp-assessment"},
            )
            assert accepted.status_code == 202
            assert AssessmentWorker(queue, token).run_once()["status"] == "succeeded"
            job = client.get(accepted.headers["location"], headers=auth)
            assert job.status_code == 200
            detail = client.get(path + "/" + job.json()["assessment_id"], headers=auth)
            assert (
                detail.status_code == 200 and detail.json()["explanation"]["status"] == "verified"
            )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
