"""Real PostgreSQL human casework acceptance. Synthetic evidence and offline provider only."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_draft_api import submit as draft_submit
from test_foundation import headers
from test_investigation_coordinator import request as packet_request
from test_investigation_drafts import draft_env as draft_fixture
from test_investigation_drafts import env as env_fixture
from test_investigation_drafts import evidence_setup as evidence_fixture

from alembic import command
from app.models import AuditEvent, Case, User
from app.models.casework import CaseworkEntry
from app.models.investigation_drafts import StoredDraft
from app.security.auth import password_hash
from app.services.case_workflows import CaseWorkflowService
from app.services.casework import CaseworkService
from app.services.snapshot_clock import ClockUnavailable

env, evidence_setup, draft_env = env_fixture, evidence_fixture, draft_fixture
pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        not os.environ.get("TRUEFLAG_TEST_POSTGRES_URL"), reason="Requires real isolated PostgreSQL"
    ),
]


@pytest.fixture
def work(draft_env):
    e = draft_env
    with Session(e["platform"][1]) as session, session.begin():
        for name in ["supervisor", "managerother"]:
            user = User(
                username=name, role="supervisor", password_hash=password_hash.hash(e["platform"][3])
            )
            session.add(user)
            session.flush()
            e["users"][name] = user.id
    e["casework"] = CaseworkService(e["platform"][1], e["platform"][2])
    return e


def url(e):
    return f"/api/v1/cases/{e['case']}/casework"


def auth_for(e, actor="admin"):
    cache = e.setdefault("casework_auth", {})
    if actor not in cache:
        cache[actor] = headers(e["platform"], actor)
    return cache[actor]


def post(e, kind="note", *, actor="admin", key=None, expected=None, **fields):
    c = e["service"].reader.get_case_context(e["users"][actor], e["case"])
    current = e["casework"].history(e["users"][actor], e["case"])
    body = dict(
        kind=kind,
        snapshot=c.data.snapshot_token,
        expected_revision=current.revision if expected is None else expected,
        rationale="Reviewed the source records and documented a human rationale.",
        supporting_records=[],
    )
    body.update(fields)
    return e["platform"][0].post(
        url(e),
        headers={**auth_for(e, actor), "Idempotency-Key": key or uuid4().hex},
        json=body,
    )


def reviewed(e):
    parent_receipt = e["service"].request(
        e["users"]["admin"], e["case"], uuid4().hex, packet_request(e)
    )
    assert e["service"].run_once(e["token"])["status"] == "succeeded"
    packet = e["service"].get(e["users"]["admin"], e["case"], UUID(parent_receipt["run_id"]))
    receipt = draft_submit(
        e,
        dict(
            investigation_run_id=parent_receipt["run_id"],
            expected_packet_sha256=packet["verification"]["packet_sha256"],
        ),
        key=uuid4().hex,
    )
    assert receipt.status_code == 202, receipt.text
    assert e["drafts"].run_once(e["token"])["status"] == "succeeded"
    detail = e["platform"][0].get(receipt.headers["Location"], headers=auth_for(e))
    assert detail.status_code == 200, detail.text
    body = detail.json()["draft"]
    response = post(
        e,
        "finding_review",
        draft_run_id=body["draft_run_id"],
        reference_id=body["findings"][0]["reference_id"],
        expected_draft_sha256=body["content_sha256"],
        decision="reject",
    )
    assert response.status_code == 201, response.text
    return body


def approve(e, outcome="investigation_completed"):
    assert post(e).status_code == 201
    reviewed(e)
    escalation = post(e, "escalation")
    assert escalation.status_code == 201, escalation.text
    response = post(
        e,
        "supervisor_response",
        actor="supervisor",
        parent_id=escalation.json()["id"],
        decision="approve_resolution",
        proposed_outcome=outcome,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_full_human_workflow_four_eyes_history_audit_and_original_finding(work):
    e = work
    context = e["service"].reader.get_case_context(e["users"]["admin"], e["case"])
    refs = [context.evidence[0].model_dump(mode="json")]
    note = post(e, supporting_records=refs)
    assert note.status_code == 201, note.text
    correction = post(
        e,
        parent_id=note.json()["id"],
        rationale="Correction: only observed activity was reviewed; no criminal conclusion.",
    )
    assert correction.status_code == 201
    request = post(
        e, "information_request", category="transaction_clarification", due_date="2026-12-01"
    )
    assert request.status_code == 201, request.text
    resolution = post(
        e,
        "information_response",
        parent_id=request.json()["id"],
        status="resolved",
        supporting_records=refs,
    )
    assert resolution.status_code == 201, resolution.text
    draft = reviewed(e)
    escalation = post(e, "escalation")
    q = e["platform"][0].get("/api/v1/supervisor-review-queue", headers=auth_for(e, "supervisor"))
    assert q.status_code == 200 and q.json()["total"] == 1
    response = post(
        e,
        "supervisor_response",
        actor="supervisor",
        parent_id=escalation.json()["id"],
        decision="approve_resolution",
        proposed_outcome="investigation_completed",
    )
    assert response.status_code == 201, response.text
    final = post(
        e,
        "resolution",
        actor="supervisor",
        parent_id=response.json()["id"],
        outcome="investigation_completed",
        confirmed=True,
    )
    assert final.status_code == 201, final.text
    history = e["casework"].history(e["users"]["supervisor"], e["case"])
    assert history.resolution == "investigation_completed" and history.total == 8
    assert history.open_information_requests == history.pending_escalations == 0
    with Session(e["platform"][1]) as session:
        case = session.get(Case, e["case"])
        assert case.status == "closed" and case.disposition == "close"
        stored = session.scalar(select(StoredDraft))
        assert stored.content_sha256 == draft["content_sha256"]
        assert session.scalar(select(func.count()).select_from(CaseworkEntry)) == 8
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(
                    AuditEvent.action.in_(
                        [
                            "evidence.casework." + k
                            for k in [
                                "note",
                                "information_request",
                                "information_response",
                                "finding_review",
                                "escalation",
                                "supervisor_response",
                                "resolution",
                            ]
                        ]
                    )
                )
            )
            == 8
        )
    activity = e["platform"][0].get(
        f"/api/v1/cases/{e['case']}/activity", headers=auth_for(e, "supervisor")
    )
    assert activity.status_code == 200 and any(
        r["event_type"] == "casework_resolution" for r in activity.json()["items"]
    )
    assert "rationale" not in activity.text


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE casework_entries SET author='forged'",
        "DELETE FROM casework_entries",
        "TRUNCATE casework_entries",
    ],
)
def test_database_submitted_history_is_immutable(work, sql):
    assert post(work).status_code == 201
    with pytest.raises(DBAPIError), work["platform"][1].begin() as con:
        con.execute(text(sql))
    assert work["casework"].history(work["users"]["admin"], work["case"]).total == 1


def test_idempotent_concurrency_conflicts_and_revision_fences(work):
    e = work
    context = e["service"].reader.get_case_context(e["users"]["admin"], e["case"])
    body = dict(
        kind="note",
        snapshot=context.data.snapshot_token,
        expected_revision=0,
        rationale="Independent concurrent note submission.",
    )
    auth = {**auth_for(e), "Idempotency-Key": "concurrent-human-note"}
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(
            pool.map(lambda _: e["platform"][0].post(url(e), headers=auth, json=body), range(3))
        )
    assert [r.status_code for r in responses] == [201] * 3
    assert len({r.json()["id"] for r in responses}) == 1
    assert (
        e["platform"][0]
        .post(
            url(e),
            headers=auth,
            json={**body, "rationale": "Different submission with the same idempotency key."},
        )
        .status_code
        == 409
    )
    assert post(e, expected=0).status_code == 409


def test_concurrent_resolution_one_winner(work):
    e = work
    approval = approve(e)
    context = e["service"].reader.get_case_context(e["users"]["supervisor"], e["case"])
    body = dict(
        kind="resolution",
        snapshot=context.data.snapshot_token,
        expected_revision=approval["revision"],
        parent_id=approval["id"],
        outcome="investigation_completed",
        confirmed=True,
        rationale="The supervisor confirms this internal synthetic outcome.",
    )
    auth = auth_for(e, "supervisor")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: e["platform"][0].post(
                    url(e), headers={**auth, "Idempotency-Key": uuid4().hex}, json=body
                ),
                range(2),
            )
        )
    assert sorted(r.status_code for r in results) == [201, 409]
    with Session(e["platform"][1]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseworkEntry)
                .where(CaseworkEntry.kind == "resolution")
            )
            == 1
        )


def test_cross_case_assignment_revocation_and_anonymous(work):
    e = work
    client = e["platform"][0]
    assert client.get(url(e)).status_code == 401
    assert client.get(url(e), headers=auth_for(e, "analyst")).status_code == 404
    with Session(e["platform"][1]) as session, session.begin():
        session.get(Case, e["case"]).assigned_to = e["users"]["analyst"]
    assert client.get(url(e), headers=auth_for(e, "analyst")).status_code == 200
    snapshot = (
        e["service"].reader.get_case_context(e["users"]["analyst"], e["case"]).data.snapshot_token
    )
    with Session(e["platform"][1]) as session, session.begin():
        session.get(Case, e["case"]).assigned_to = None
    body = dict(
        kind="note",
        snapshot=snapshot,
        expected_revision=0,
        rationale="Previously assigned analyst cannot submit after revocation.",
    )
    assert (
        client.post(
            url(e),
            json=body,
            headers={**auth_for(e, "analyst"), "Idempotency-Key": uuid4().hex},
        ).status_code
        == 404
    )
    assert (
        client.get(url(e).replace(str(e["case"]), str(uuid4())), headers=auth_for(e)).status_code
        == 404
    )
    assert (
        client.get("/api/v1/supervisor-review-queue", headers=auth_for(e, "analyst")).status_code
        == 403
    )


def test_roles_self_approval_and_unauthorized_note_correction(work):
    e = work
    original = post(e).json()
    assert post(e, actor="supervisor", parent_id=original["id"]).status_code == 403
    escalation = post(e, "escalation").json()
    assert (
        post(
            e,
            "supervisor_response",
            parent_id=escalation["id"],
            decision="approve_resolution",
            proposed_outcome="investigation_completed",
        ).status_code
        == 403
    )
    with Session(e["platform"][1]) as session, session.begin():
        session.get(Case, e["case"]).assigned_to = e["users"]["analyst"]
    assert (
        post(
            e,
            "supervisor_response",
            actor="analyst",
            parent_id=escalation["id"],
            decision="return_for_investigation",
            proposed_outcome="additional_review_required",
        ).status_code
        == 403
    )


def test_stale_forged_revoked_source_and_hidden_history(work):
    e = work
    ctx = e["service"].reader.get_case_context(e["users"]["admin"], e["case"])
    ref = ctx.evidence[0].model_dump(mode="json")
    assert post(e, supporting_records=[{**ref, "sha256": "0" * 64}]).status_code == 404
    assert post(e, supporting_records=[ref, ref]).status_code == 404
    assert post(e, supporting_records=[ref]).status_code == 201
    e["foundation"].set_source_access(e["users"]["admin"], e["case"], e["source"], False)
    history = e["casework"].history(e["users"]["admin"], e["case"])
    assert (
        history.items[0].payload is None
        and history.items[0].content_status == "withheld_source_changed"
    )
    response = e["platform"][0].post(
        url(e),
        json=dict(
            kind="note",
            snapshot=ctx.data.snapshot_token,
            expected_revision=1,
            rationale="An expired evidence snapshot must never be accepted.",
        ),
        headers={**auth_for(e), "Idempotency-Key": uuid4().hex},
    )
    assert response.status_code == 409


def test_missing_evidence_can_request_information_but_not_finalize(work):
    e = work
    e["foundation"].set_source_access(e["users"]["admin"], e["case"], e["source"], False)
    assert post(e).status_code == 201
    req = post(e, "information_request", category="activity_history")
    assert req.status_code == 201
    assert (
        post(e, "information_response", parent_id=req.json()["id"], status="resolved").status_code
        == 409
    )
    escalated = post(e, "escalation").json()
    assert (
        post(
            e,
            "supervisor_response",
            actor="supervisor",
            parent_id=escalated["id"],
            decision="approve_resolution",
            proposed_outcome="investigation_completed",
        ).status_code
        == 409
    )
    assert (
        post(
            e,
            "supervisor_response",
            actor="supervisor",
            parent_id=escalated["id"],
            decision="return_for_investigation",
            proposed_outcome="additional_review_required",
        ).status_code
        == 201
    )


def test_audit_failure_rolls_back_all_writes(work):
    e = work

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO casework_entries"):
            raise RuntimeError("synthetic database interruption")

    event.listen(e["platform"][1], "before_cursor_execute", fail)
    try:
        assert post(e).status_code == 503
    finally:
        event.remove(e["platform"][1], "before_cursor_execute", fail)
    with Session(e["platform"][1]) as session:
        assert session.scalar(select(func.count()).select_from(CaseworkEntry)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.casework.note")
            )
            == 0
        )
    assert post(e).status_code == 201


def test_clock_uncertainty_sanitized_and_no_entry(work, monkeypatch):
    e = work
    from app.services.snapshot_clock import SnapshotTime

    def deny(self):
        raise ClockUnavailable("snapshot_clock_unavailable")

    monkeypatch.setattr(SnapshotTime, "observe", deny)
    response = e["platform"][0].get(url(e), headers=auth_for(e))
    assert (
        response.status_code == 503 and response.headers["X-TrueFlag-Reason"] == "clock_uncertainty"
    )
    assert "snapshot_clock_unavailable" not in response.text


def test_strict_input_no_patch_and_bounded_pagination(work):
    e = work
    assert post(e, rationale=" ").status_code == 422
    assert post(e, provider="luminal").status_code == 422
    assert e["platform"][0].get(url(e) + "?limit=21", headers=auth_for(e)).status_code == 422
    assert (
        e["platform"][0]
        .patch(url(e), headers=auth_for(e), json={"rationale": "Changed"})
        .status_code
        == 405
    )


def test_migration_rollback_empty_and_refuse_retained_history(work):
    e = work
    engine = e["platform"][1]
    # Only this fixture's random schema. Existing environment URL is already schema-scoped.
    cfg = Config("backend/alembic.ini")
    command.downgrade(cfg, "0017_live_provider")
    command.upgrade(cfg, "head")
    assert post(e).status_code == 201
    with pytest.raises(RuntimeError, match="retained human casework"):
        command.downgrade(cfg, "0017_live_provider")
    with engine.connect() as con:
        from app.core.schema import EXPECTED_SCHEMA_REVISION

        assert (
            con.scalar(text("SELECT version_num FROM alembic_version")) == EXPECTED_SCHEMA_REVISION
        )


def test_changed_casework_invalidates_approval(work):
    e = work
    approval = approve(e)
    assert (
        post(
            e, rationale="An additional note changes the information considered after approval."
        ).status_code
        == 201
    )
    assert (
        post(
            e,
            "resolution",
            actor="supervisor",
            parent_id=approval["id"],
            outcome="investigation_completed",
            confirmed=True,
        ).status_code
        == 409
    )
    with Session(e["platform"][1]) as session:
        assert session.get(Case, e["case"]).status == "open"


def test_supervisor_role_revocation_prevents_resolution(work):
    e = work
    approval = approve(e)
    context = e["service"].reader.get_case_context(e["users"]["supervisor"], e["case"])
    auth_headers = auth_for(e, "supervisor")
    with Session(e["platform"][1]) as session, session.begin():
        session.get(User, e["users"]["supervisor"]).active = False
    response = e["platform"][0].post(
        url(e),
        headers={**auth_headers, "Idempotency-Key": uuid4().hex},
        json=dict(
            kind="resolution",
            snapshot=context.data.snapshot_token,
            expected_revision=approval["revision"],
            parent_id=approval["id"],
            outcome="investigation_completed",
            confirmed=True,
            rationale="A revoked identity must never finalize an outcome.",
        ),
    )
    assert response.status_code in {401, 403}
    with Session(e["platform"][1]) as session:
        assert session.get(Case, e["case"]).status == "open"


def test_forged_finding_reference_and_content_hash_rejected(work):
    e = work
    body = reviewed(e)
    for ref, sha in [
        (str(uuid4()), body["content_sha256"]),
        (body["findings"][0]["reference_id"], "0" * 64),
    ]:
        response = post(
            e,
            "finding_review",
            draft_run_id=body["draft_run_id"],
            reference_id=ref,
            expected_draft_sha256=sha,
            decision="accept_for_consideration",
        )
        assert response.status_code in {404, 409}
    with Session(e["platform"][1]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseworkEntry)
                .where(CaseworkEntry.kind == "finding_review")
            )
            == 1
        )


def test_database_failure_rolls_back_resolution_and_audit(work):
    e = work
    approval = approve(e)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO casework_entries"):
            raise RuntimeError("synthetic resolution persistence interruption")

    event.listen(e["platform"][1], "before_cursor_execute", fail)
    try:
        assert (
            post(
                e,
                "resolution",
                actor="supervisor",
                parent_id=approval["id"],
                outcome="investigation_completed",
                confirmed=True,
            ).status_code
            == 503
        )
    finally:
        event.remove(e["platform"][1], "before_cursor_execute", fail)
    with Session(e["platform"][1]) as session:
        assert session.get(Case, e["case"]).status == "open"
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseworkEntry)
                .where(CaseworkEntry.kind == "resolution")
            )
            == 0
        )

        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "evidence.casework.resolution")
            )
            == 0
        )


def test_interim_resolution_allows_new_verified_review_without_erasing_history(work):
    e = work
    approval = approve(e, "additional_review_required")
    first = post(
        e,
        "resolution",
        actor="supervisor",
        parent_id=approval["id"],
        outcome="additional_review_required",
        confirmed=True,
    )
    assert first.status_code == 201, first.text
    workflows = CaseWorkflowService(e["platform"][1])
    # The case record carries the recorded resolution even when the case stays open.
    shown = workflows.overview(e["users"]["supervisor"], e["case"])
    assert (shown["status"], shown["resolution"]) == ("in_review", "additional_review_required")
    assert post(e).status_code == 201
    reviewed(e)
    escalation = post(e, "escalation").json()
    response = post(
        e,
        "supervisor_response",
        actor="supervisor",
        parent_id=escalation["id"],
        decision="approve_resolution",
        proposed_outcome="investigation_completed",
    )
    assert response.status_code == 201, response.text
    final = post(
        e,
        "resolution",
        actor="supervisor",
        parent_id=response.json()["id"],
        outcome="investigation_completed",
        confirmed=True,
    )
    assert final.status_code == 201, final.text
    assert workflows.overview(e["users"]["supervisor"], e["case"])["resolution"] == (
        "investigation_completed"
    )  # the latest resolution wins
    with Session(e["platform"][1]) as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseworkEntry)
                .where(CaseworkEntry.kind == "finding_review")
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(CaseworkEntry)
                .where(CaseworkEntry.kind == "resolution")
            )
            == 2
        )


def test_stale_escalation_can_only_be_returned_for_new_investigation(work):
    e = work
    escalation = post(e, "escalation").json()
    e["foundation"].set_source_access(e["users"]["admin"], e["case"], e["source"], False)
    assert (
        post(
            e,
            "supervisor_response",
            actor="supervisor",
            parent_id=escalation["id"],
            decision="approve_resolution",
            proposed_outcome="investigation_completed",
        ).status_code
        == 409
    )
    assert (
        post(
            e,
            "supervisor_response",
            actor="supervisor",
            parent_id=escalation["id"],
            decision="return_for_investigation",
            proposed_outcome="additional_review_required",
        ).status_code
        == 201
    )
    assert post(e, "escalation").status_code == 201
