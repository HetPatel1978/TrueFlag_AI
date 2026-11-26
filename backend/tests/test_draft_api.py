"""Real PostgreSQL gateways; deterministic fixture provider, actual worker covered separately."""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_foundation import headers
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import draft_env as draft_env_fixture
from test_investigation_drafts import env as env_fixture
from test_investigation_drafts import evidence_setup as evidence_setup_fixture

from app.models import Case
from app.models.investigation_drafts import DraftJob, DraftRun, StoredDraft
from app.services.draft_api import DraftAPIService
from app.services.investigation_drafts import InvestigationDraftService
from app.services.investigation_provider import DeterministicFakeProvider

env = env_fixture
evidence_setup = evidence_setup_fixture
draft_env = draft_env_fixture
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("TRUEFLAG_TEST_POSTGRES_URL"), reason="requires opt-in PostgreSQL"
    ),
]


def path(e):
    return f"/api/v1/cases/{e['case']}/investigation-drafts"


def parent(e):
    receipt = e["service"].request(
        e["users"]["admin"], e["case"], "gateway-parent-key", packet_request(e)
    )
    for _ in range(3):
        job = e["service"].run_once(e["token"])
        if job and job["status"] != "pending":
            break
    result = e["service"].get(e["users"]["admin"], e["case"], UUID(receipt["run_id"]))
    assert result.get("packet") is not None, result["status"]
    return dict(
        investigation_run_id=receipt["run_id"],
        expected_packet_sha256=result["verification"]["packet_sha256"],
    )


def submit(e, body=None, key="gateway-request-key"):
    return e["platform"][0].post(
        path(e), headers={**headers(e["platform"]), "Idempotency-Key": key}, json=body or parent(e)
    )


def test_async_http_job_real_worker_strict_results_and_history(draft_env):
    e = draft_env
    body = parent(e)
    response = submit(e, body)
    assert response.status_code == 202, response.text
    location = response.headers["Location"]
    assert (
        response.json()["mode"] == "offline_simulation" and response.headers["Retry-After"] == "2"
    )
    auth, client = headers(e["platform"]), e["platform"][0]
    assert client.get(location, headers=auth).json()["draft"] is None
    # Real constrained Linux fake-provider subprocess, no external transport.
    e["drafts"]._runner = InvestigationDraftService(e["platform"][1], e["platform"][2])._runner
    result = e["drafts"].run_once(e["token"])
    assert result["status"] == "succeeded", result
    detail = client.get(location, headers=auth)
    assert detail.status_code == 200, detail.text
    draft = detail.json()["draft"]
    assert draft["verification"] == "source_reference_numeric_checks_passed"
    assert draft["simulation"] and not draft["live_provider_used"]
    assert draft["semantic_review"] == "pending_human_review"
    assert draft["regulatory_context"] == "unavailable_unapproved"
    assert {f["claim_type"] for f in draft["findings"]} == {"observed_fact", "calculated_fact"}
    assert not any(
        key in detail.text
        for key in ['"features"', '"snapshot_token"', '"usage"', '"api_key"', '"annual_income"']
    )
    history = client.get(path(e), headers=auth).json()
    assert (
        history["total"] == 1
        and history["items"][0]["validation_status"] == "stored_not_revalidated"
    )
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(StoredDraft)) == 1
        assert session.get(Case, e["case"]).status == "open"


def test_concurrent_duplicate_requests_and_conflicting_packet_digest(draft_env):
    e = draft_env
    body = parent(e)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: submit(e, body), range(3)))
    assert all(r.status_code == 202 for r in results)
    assert len({r.json()["draft_run_id"] for r in results}) == 1
    assert submit(e, dict(body, expected_packet_sha256="0" * 64)).status_code == 409
    # A new browser request key still reuses the existing unique parent/config intent.
    assert (
        submit(e, body, key="different-browser-key").json()["draft_run_id"]
        == results[0].json()["draft_run_id"]
    )
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftRun)) == 1


@pytest.mark.parametrize("operation", ["request", "history", "detail"])
def test_anonymous_cross_case_and_requester_scoped_history(draft_env, operation):
    e = draft_env
    body = parent(e)
    accepted = submit(e, body)
    assert accepted.status_code == 202, accepted.text
    url = accepted.headers["Location"] if operation == "detail" else path(e)
    client = e["platform"][0]
    args = (
        dict(json=body, headers={"Idempotency-Key": "anonymous-request"})
        if operation == "request"
        else {}
    )
    assert (
        client.post(url, **args) if operation == "request" else client.get(url)
    ).status_code == 401
    wrong = url.replace(str(e["case"]), str(uuid4()))
    auth = headers(e["platform"])
    assert (
        client.post(wrong, json=body, headers={**auth, "Idempotency-Key": "foreign-case-key"})
        if operation == "request"
        else client.get(wrong, headers=auth)
    ).status_code == 404
    with Session(e["platform"][1]) as session, session.begin():
        session.get(Case, e["case"]).assigned_to = e["users"]["analyst"]
    other = headers(e["platform"], "analyst")
    assert client.get(path(e), headers=other).json()["total"] == 0
    assert client.get(accepted.headers["Location"], headers=other).status_code == 404


@pytest.mark.parametrize("changed", ["assignment", "source", "revision"])
def test_revoked_or_stale_inputs_never_return_draft(draft_env, changed):
    e = draft_env
    accepted = submit(e)
    assert accepted.status_code == 202, accepted.text
    if changed == "source":
        e["foundation"].set_source_access(e["users"]["admin"], e["case"], e["source"], False)
    else:
        with Session(e["platform"][1]) as session, session.begin():
            case = session.get(Case, e["case"])
            case.version += 1
            if changed == "assignment":
                case.assigned_to = e["users"]["analyst"]
    result = e["platform"][0].get(accepted.headers["Location"], headers=headers(e["platform"]))
    assert result.status_code in {200, 404, 409}
    if result.status_code == 200:
        assert result.json()["status"] == "invalidated" and result.json()["draft"] is None


def test_malformed_provider_controls_disabled_mode_and_bounded_history(draft_env):
    e = draft_env
    body = parent(e)
    assert submit(e, dict(body, provider="luminal")).status_code == 422
    for query in ["?limit=21", "?offset=1001", "?limit=0"]:
        assert (
            e["platform"][0].get(path(e) + query, headers=headers(e["platform"])).status_code == 422
        )
    e["platform"][2].investigation_external_enabled = True
    assert submit(e, body).status_code == 503
    e["platform"][2].investigation_external_enabled = False
    e["platform"][2].investigation_simulation_enabled = False
    assert submit(e, body).status_code == 503
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftJob)) == 0


def test_bad_financial_proposal_is_not_publishable(draft_env):
    e = draft_env
    accepted = submit(e)
    assert accepted.status_code == 202, accepted.text

    class InvalidSimulation:
        def invoke(self, packet, config):
            reply = DeterministicFakeProvider().propose(packet, config)
            value = json.loads(reply.content)
            fact = next(f for f in value["findings"] if f["claim_type"] == "calculated_fact")
            fact["numeric_statements"] = [
                dict(
                    metric="observed_count",
                    value="999999",
                    currency="USD",
                    window=packet.financial_facts[0]["result"]["window"],
                )
            ]
            return reply.model_copy(update=dict(content=json.dumps(value)))

    e["drafts"]._runner = InvalidSimulation()
    assert e["drafts"].run_once(e["token"])["status"] == "failed"
    detail = (
        e["platform"][0].get(accepted.headers["Location"], headers=headers(e["platform"])).json()
    )
    assert detail["draft"] is None and detail["error_code"] == "verification_failed"


def test_api_intent_and_audit_failure_roll_back_atomically(draft_env, monkeypatch):
    import app.services.investigation_drafts as module

    e = draft_env
    body = parent(e)
    original = module.audit

    def broken(session, actor, action, resource, **details):
        if action == "investigation.draft.requested":
            raise RuntimeError("controlled audit failure")
        return original(session, actor, action, resource, **details)

    monkeypatch.setattr(module, "audit", broken)
    assert submit(e, body).status_code == 503
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(DraftRun)) == 0
        assert session.scalar(select(func.count()).select_from(DraftJob)) == 0


def test_detail_poll_and_worker_use_the_same_gate_before_actor_locks(draft_env):
    """A reader must not own the actor row while waiting on the worker's advisory gate."""
    e = draft_env
    accepted = submit(e)
    assert accepted.status_code == 202, accepted.text
    run = UUID(accepted.json()["draft_run_id"])
    gateway = DraftAPIService(e["platform"][1], e["platform"][2])
    held, reader_started = Event(), Event()
    original = gateway.drafts.coordinator._gate

    def observed_gate(session):
        reader_started.set()
        return original(session)

    gateway.drafts.coordinator._gate = observed_gate

    def worker_transaction():
        with Session(e["platform"][1]) as session, session.begin():
            e["service"]._gate(session)
            held.set()
            assert reader_started.wait(3)
            # This current-permission read is the worker's real source validation path.
            e["service"].reader._context(session, e["users"]["admin"], e["case"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        worker = pool.submit(worker_transaction)
        assert held.wait(3)
        reader = pool.submit(gateway.detail, e["users"]["admin"], e["case"], run)
        worker.result(timeout=8)
        result = reader.result(timeout=8)
    assert result.status == "pending" and result.draft is None


def test_revoked_analyst_assignment_denies_status_history_and_requests(draft_env):
    e = draft_env
    actor = e["users"]["analyst"]
    with Session(e["platform"][1]) as session, session.begin():
        session.get(Case, e["case"]).assigned_to = actor
    receipt = e["service"].request(actor, e["case"], "analyst-parent-key", packet_request(e))
    assert e["service"].run_once(e["token"])["status"] == "succeeded"
    result = e["service"].get(actor, e["case"], UUID(receipt["run_id"]))
    body = dict(
        investigation_run_id=receipt["run_id"],
        expected_packet_sha256=result["verification"]["packet_sha256"],
    )
    auth = {**headers(e["platform"], "analyst"), "Idempotency-Key": "analyst-draft-key"}
    response = e["platform"][0].post(path(e), json=body, headers=auth)
    assert response.status_code == 202, response.text
    with Session(e["platform"][1]) as session, session.begin():
        session.get(Case, e["case"]).assigned_to = None
    assert e["platform"][0].get(response.headers["Location"], headers=auth).status_code == 404
    assert e["platform"][0].get(path(e), headers=auth).status_code == 404
    assert e["platform"][0].post(path(e), json=body, headers=auth).status_code == 404


def test_clock_uncertainty_denies_detail_without_publishing_values(draft_env, monkeypatch):
    from app.services.snapshot_clock import ClockUnavailable, SnapshotTime

    e = draft_env
    response = submit(e)
    assert response.status_code == 202, response.text
    auth = headers(e["platform"])

    def denied(_):
        raise ClockUnavailable("controlled_clock_denial")

    monkeypatch.setattr(SnapshotTime, "observe", denied)
    result = e["platform"][0].get(response.headers["Location"], headers=auth)
    assert result.status_code == 503 and result.headers["X-TrueFlag-Reason"] == "clock_uncertainty"
    assert '"draft"' not in result.text and '"findings"' not in result.text
