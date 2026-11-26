"""Real PostgreSQL HTTP gateway, coordinator execution, authorization and stale-result fencing."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_evidence_foundation import admit
from test_evidence_foundation import evidence_setup as evidence_fixture
from test_foundation import headers
from test_investigation_coordinator import env as investigation_fixture
from test_investigation_coordinator import request as investigation_request
from test_snapshot_clock_integrity import anchor, clock_view

from app.models import AuditEvent, Case, User
from app.models.investigations import InvestigationPacket, InvestigationRun
from app.services.synthetic_evidence import generate_scenario

pytestmark = pytest.mark.postgres
evidence_setup = evidence_fixture
env = investigation_fixture


def url(env):
    return f"/api/v1/cases/{env['case']}/investigations"


def body(env):
    return investigation_request(env).model_dump(mode="json")


def submit(env, *, key="gateway-request-001", payload=None, auth=None):
    return env["platform"][0].post(
        url(env),
        json=payload or body(env),
        headers={**(headers(env["platform"]) if auth is None else auth), "Idempotency-Key": key},
    )


def test_request_worker_publication_history_and_provenance(env):
    client = env["platform"][0]
    auth = headers(env["platform"])
    result = submit(env)
    assert result.status_code == 202
    assert result.json()["status"] == "pending"
    location = result.headers["Location"]
    assert result.headers["Retry-After"] == "2"
    pending = client.get(location, headers=auth)
    assert pending.status_code == 200 and pending.json()["packet"] is None
    assert env["service"].run_once(env["token"])["status"] == "succeeded"
    detail = client.get(location, headers=auth)
    assert detail.status_code == 200, detail.text
    data = detail.json()
    assert data["verification"]["status"] == "source_numeric_reference_checks_passed"
    assert len(data["packet"]["transactions"]) == 12
    assert data["packet"]["regulatory_citations"] == [] and not data["packet"]["provider_used"]
    assert "snapshot_token" not in detail.text and "annual_income" not in detail.text
    history = client.get(url(env), headers=auth).json()
    assert history["total"] == 1 and history["items"][0]["run_id"] == data["run_id"]
    assert history["items"][0]["validation_status"] == "stored_not_revalidated"
    with Session(env["platform"][1]) as session:
        assert session.get(Case, env["case"]).status == "open"
        assert session.scalar(select(func.count()).select_from(InvestigationPacket)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.investigation.history")
            )
            == 1
        )


def test_idempotency_conflicts_concurrency_and_actor_scoped_history(env):
    payload, auth = body(env), headers(env["platform"])
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(lambda _: submit(env, payload=payload, auth=auth), range(3)))
    assert all(r.status_code == 202 for r in responses)
    assert len({r.json()["run_id"] for r in responses}) == 1
    changed = {**payload, "currencies": ["CAD"]}
    assert submit(env, payload=changed, auth=auth).status_code == 409
    with Session(env["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationRun)) == 1
    for name in ["analyst"]:
        assert (
            env["platform"][0].get(url(env), headers=headers(env["platform"], name)).status_code
            == 404
        )


@pytest.mark.parametrize("method", ["post", "list", "detail"])
def test_anonymous_and_cross_case_enumeration_denied(env, method):
    client = env["platform"][0]
    receipt = submit(env)
    location = receipt.headers["Location"]
    path = url(env) if method != "detail" else location
    response = (
        client.post(path, json=body(env), headers={"Idempotency-Key": "anonymous-request"})
        if method == "post"
        else client.get(path)
    )
    assert response.status_code == 401
    analyst = headers(env["platform"], "analyst")
    response = submit(env, auth=analyst) if method == "post" else client.get(path, headers=analyst)
    assert response.status_code == 404 and "transactions" not in response.text
    _, _, release = admit(env["foundation"], env["users"]["admin"])
    other = env["foundation"].create_case(env["users"]["admin"], release)
    otherpath = location.replace(str(env["case"]), str(other))
    assert client.get(otherpath, headers=headers(env["platform"])).status_code == 404


@pytest.mark.parametrize("change", ["source", "assignment"])
def test_revocation_invalidates_packet_without_data(env, change):
    client, engine = env["platform"][:2]
    actor = env["users"]["admin"]
    if change == "assignment":
        with Session(engine) as session, session.begin():
            session.get(Case, env["case"]).assigned_to = env["users"]["analyst"]
        auth = headers(env["platform"], "analyst")
    else:
        auth = headers(env["platform"])
    receipt = submit(env, auth=auth)
    assert receipt.status_code == 202
    assert env["service"].run_once(env["token"])["status"] == "succeeded"
    if change == "source":
        env["foundation"].set_source_access(actor, env["case"], env["source"], False)
    else:
        with Session(engine) as session, session.begin():
            row = session.get(Case, env["case"])
            row.assigned_to = None
            row.version += 1
    response = client.get(receipt.headers["Location"], headers=auth)
    if change == "assignment":
        assert response.status_code == 404
    else:
        assert response.status_code == 200
        assert response.json()["status"] == "invalidated" and response.json()["packet"] is None


def test_source_revision_and_current_role_rechecked(env, monkeypatch):
    client, engine = env["platform"][:2]
    old = body(env)
    revised = generate_scenario(env["bundle"].scenario_id, 17, source_revision=2)
    release = env["foundation"].admit_version(env["users"]["admin"], env["source"], revised)
    env["foundation"].link_version(env["users"]["admin"], env["case"], release)
    assert submit(env, payload=old).status_code == 409
    from app.services.investigation_coordinator import InvestigationCoordinator

    original = InvestigationCoordinator.request

    def revoked(service, actor, *args):
        with Session(engine) as session, session.begin():
            session.get(User, actor).active = False
        return original(service, actor, *args)

    payload = body(env)
    monkeypatch.setattr(InvestigationCoordinator, "request", revoked)
    assert submit(env, payload=payload).status_code == 404


def test_clock_503_is_explicit_and_does_not_enqueue(env):
    client, engine = env["platform"][:2]
    auth = headers(env["platform"])
    initial = anchor(env)
    with clock_view(engine, initial) as clock:
        payload = body(env)
        clock[0] -= timedelta(seconds=1)
        response = submit(env, payload=payload, auth=auth)
        assert (
            response.status_code == 503
            and response.headers["X-TrueFlag-Reason"] == "clock_uncertainty"
        )
        response = client.get(f"/api/v1/cases/{env['case']}/evidence", headers=auth)
        assert response.status_code == 503 and "SELECT" not in response.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(InvestigationRun)) == 0


@pytest.mark.parametrize("mutate", ["score", "window", "choice"])
def test_invalid_requests_are_rejected_without_feature_reflection(env, mutate):
    payload = body(env)
    if mutate == "score":
        payload["model_score"] = 0.001
    elif mutate == "window":
        payload["window"]["end"] = payload["window"]["start"]
    else:
        payload.pop("without_assessment_reason")
    response = submit(env, payload=payload)
    assert response.status_code == 422 and "0.001" not in response.text


def test_pagination_duplicate_json_capacity_and_sanitized_failures(env, monkeypatch):
    client = env["platform"][0]
    auth = headers(env["platform"])
    assert client.get(url(env) + "?limit=21", headers=auth).status_code == 422
    assert client.get(url(env) + "?offset=1001", headers=auth).status_code == 422
    text = __import__("json").dumps(body(env))
    duplicate = text[:-1] + ',"currencies":["USD"]}'
    response = client.post(
        url(env),
        content=duplicate,
        headers={
            **auth,
            "Content-Type": "application/json",
            "Idempotency-Key": "duplicate-json-key",
        },
    )
    assert response.status_code == 422
    slots = client.app.state.evidence_read_slots
    for _ in range(4):
        slots.acquire()
    try:
        assert submit(env, auth=auth).status_code == 429
    finally:
        for _ in range(4):
            slots.release()


@pytest.mark.skipif(
    os.environ.get("TRUEFLAG_TEST_REAL_ASSESSMENT") != "1", reason="Actual pinned RF/SHAP required"
)
@pytest.mark.parametrize("concurrent", [False, True])
def test_scored_context_supports_transaction_and_three_analytics_reads(env, concurrent):
    from sqlalchemy import event

    from app.services.assessments import AssessmentService

    client, engine = env["platform"][:2]
    result, created = AssessmentService(engine).assess(
        actor_id=env["users"]["admin"],
        case_id=env["case"],
        expected_version=1,
        run_id=uuid4(),
        idempotency_key="gateway-real-assessment",
        policy="Coverage",
    )
    assert created and result["explanation"]["status"] == "verified"
    path = f"/api/v1/cases/{env['case']}/evidence"
    auth = headers(env["platform"])
    response = client.get(path + "?assessment_id=" + result["assessment_id"], headers=auth)
    assert response.status_code == 200
    context = response.json()
    assert context["data"]["model_signal"]["score"] == result["score"]["score"]
    parameters = {
        "snapshot": context["data"]["snapshot_token"],
        "window": body(env)["window"],
        "currency": "USD",
    }
    queries = [("transactions", {"limit": 25})] + [
        ("activity", {"calculation": name})
        for name in ["incoming_outgoing", "velocity", "concentration"]
    ]
    failures = []

    def diagnostic(context):
        # Never include SQL text, parameters, exception messages or evidence values.
        failures.append(
            {
                "type": type(context.original_exception).__name__,
                "sqlstate": getattr(context.original_exception, "sqlstate", None),
            }
        )

    def read(query):
        suffix, fields = query
        return client.post(path + "/" + suffix, json={**parameters, **fields}, headers=auth)

    event.listen(engine, "handle_error", diagnostic)
    try:
        if concurrent:
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(read, queries))
        else:
            responses = list(map(read, queries))
    finally:
        event.remove(engine, "handle_error", diagnostic)
    assert [r.status_code for r in responses] == [200] * 4, {"database_errors": failures}
