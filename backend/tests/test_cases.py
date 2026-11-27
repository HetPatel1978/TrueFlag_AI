from uuid import UUID, uuid4

import jwt
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import Alert, AuditEvent, Case, Decision, ModelScore, User


def assignment_events(engine):
    with Session(engine) as session:
        return session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action == "case.assignment_changed")
        )


def assign(client, team, actor="supervisor", index=2, target="analyst", version=1):
    return client.put(
        f"/api/v1/cases/{team['ids'][index]}/assignment",
        headers=team["auth"][actor],
        json={
            "assigned_to": team["users"][target] if target else None,
            "expected_version": version,
        },
    )


@pytest.mark.parametrize(
    "name,count", [("analyst", 2), ("analysttwo", 1), ("supervisor", 4), ("admin", 4)]
)
def test_case_list_scope_and_metadata_only(platform, case_team, name, count):
    response = platform[0].get("/api/v1/cases", headers=case_team["auth"][name])
    assert response.status_code == 200
    page = response.json()
    assert page["total"] == len(page["items"]) == count
    assert page["limit"] == 25 and page["offset"] == 0
    for item in page["items"]:
        assert set(item) == {
            "id",
            "alert_id",
            "assigned_to",
            "status",
            "disposition",
            "version",
            "created_at",
            "source_id",
            "priority",
            "assessment_status",
            "latest_job_id",
        }
        if name.startswith("analyst"):
            assert item["assigned_to"] == case_team["users"][name]
    assert "features" not in response.text and "password" not in response.text


@pytest.mark.parametrize("index", [1, 2])
def test_other_and_unassigned_cases_are_indistinguishable_from_missing(platform, case_team, index):
    client = platform[0]
    denied = client.get(
        f"/api/v1/cases/{case_team['ids'][index]}", headers=case_team["auth"]["analyst"]
    )
    missing = client.get(f"/api/v1/cases/{uuid4()}", headers=case_team["auth"]["analyst"])
    assert denied.status_code == missing.status_code == 404
    assert denied.json() == missing.json() == {"detail": "Case not found"}
    assert "alert" not in denied.text


def test_authorized_detail_returns_only_approved_predictors(platform, case_team):
    client, engine, _, _ = platform
    with Session(engine) as session, session.begin():
        case = session.get(Case, UUID(case_team["ids"][0]))
        alert = session.get(Alert, case.alert_id)
        alert.features = {
            **alert.features,
            "SAR": 1,
            "csrNotes": "must-not-leak",
            "password_hash": "must-not-leak",
        }
    response = client.get(
        f"/api/v1/cases/{case_team['ids'][0]}", headers=case_team["auth"]["analyst"]
    )
    assert response.status_code == 200
    features = response.json()["alert"]["features"]
    assert len(features) == 27 and features["income"] == 1001
    assert not {"SAR", "csrNotes", "password_hash"} & set(features)
    assert "must-not-leak" not in response.text and "key_sha256" not in response.text
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ModelScore)) == 0
        assert session.scalar(select(func.count()).select_from(Decision)) == 0


@pytest.mark.parametrize("name", ["admin", "supervisor"])
def test_oversight_can_read_unassigned_case(platform, case_team, name):
    response = platform[0].get(
        f"/api/v1/cases/{case_team['ids'][2]}", headers=case_team["auth"][name]
    )
    assert response.status_code == 200 and response.json()["assigned_to"] is None


def test_filters_and_counts_cannot_expand_analyst_scope(platform, case_team):
    client = platform[0]
    auth = case_team["auth"]["analyst"]
    for query in ["assignment=unassigned", f"assigned_to={case_team['users']['analysttwo']}"]:
        result = client.get("/api/v1/cases?" + query, headers=auth).json()
        assert result["total"] == 0 and result["items"] == []
    result = client.get("/api/v1/cases?status=in_review", headers=auth).json()
    assert result["total"] == 1 and result["items"][0]["id"] == case_team["ids"][3]


def test_pagination_sorting_and_filters_are_stable(platform, case_team):
    client = platform[0]
    auth = case_team["auth"]["supervisor"]
    expected = sorted(case_team["ids"])
    for offset in range(4):
        page = client.get(
            f"/api/v1/cases?limit=1&offset={offset}&sort_order=asc", headers=auth
        ).json()
        assert page["total"] == 4 and page["items"][0]["id"] == expected[offset]
    reverse = client.get("/api/v1/cases?sort_order=desc", headers=auth).json()
    assert [item["id"] for item in reverse["items"]] == expected[::-1]
    assert client.get("/api/v1/cases?assignment=unassigned", headers=auth).json()["total"] == 1
    assert client.get("/api/v1/cases?assignment=assigned", headers=auth).json()["total"] == 3
    assert client.get("/api/v1/cases?offset=100", headers=auth).json()["items"] == []


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "offset=-1",
        "offset=10001",
        "status=unknown",
        "sort_by=features",
        "sort_by=created_at;DROP TABLE cases",
        "sort_order=up",
        "role=admin",
        "assigned_to=not-a-uuid",
        "assignment=other",
    ],
)
def test_invalid_case_queries_rejected(platform, case_team, query):
    assert (
        platform[0].get("/api/v1/cases?" + query, headers=case_team["auth"]["admin"]).status_code
        == 422
    )


@pytest.mark.parametrize("action", ["list", "detail", "assign"])
def test_case_endpoints_require_authentication(platform, case_team, action):
    client = platform[0]
    path = f"/api/v1/cases/{case_team['ids'][0]}"
    if action == "list":
        response = client.get("/api/v1/cases")
    elif action == "detail":
        response = client.get(path)
    else:
        response = client.put(
            path + "/assignment", json={"assigned_to": None, "expected_version": 1}
        )
    assert response.status_code == 401


@pytest.mark.parametrize("actor", ["admin", "supervisor"])
def test_assignment_reassignment_unassignment_are_audited(platform, case_team, actor):
    client, engine, _, _ = platform
    for version, target in [(1, "analyst"), (2, "analysttwo"), (3, None)]:
        response = assign(client, case_team, actor=actor, target=target, version=version)
        assert response.status_code == 200 and response.json()["version"] == version + 1
        assert response.json()["status"] == "open" and response.json()["disposition"] is None
    assert assignment_events(engine) == 3
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(AuditEvent)
                .where(AuditEvent.action == "case.assignment_changed")
                .order_by(AuditEvent.created_at)
            )
        )
        assert all(str(row.actor_id) == case_team["users"][actor] for row in rows)
        assert rows[0].details["previous_assigned_to"] is None
        assert rows[1].details["previous_assigned_to"] == case_team["users"]["analyst"]
        assert rows[2].details["assigned_to"] is None


def test_reassignment_removes_old_analyst_access(platform, case_team):
    client = platform[0]
    assert assign(client, case_team, index=0, target="analysttwo").status_code == 200
    path = f"/api/v1/cases/{case_team['ids'][0]}"
    assert client.get(path, headers=case_team["auth"]["analyst"]).status_code == 404
    assert client.get(path, headers=case_team["auth"]["analysttwo"]).status_code == 200
    assert client.get("/api/v1/cases", headers=case_team["auth"]["analyst"]).json()["total"] == 1


def test_analyst_cannot_self_assign_or_reassign(platform, case_team):
    client, engine, _, _ = platform
    for index in [0, 1, 2]:
        assert assign(client, case_team, actor="analyst", index=index).status_code == 403
    assert assignment_events(engine) == 0


@pytest.mark.parametrize("target", ["inactive", "admin", "supervisor", "unknown"])
def test_assignee_must_be_active_analyst(platform, case_team, target):
    client, engine, _, _ = platform
    ident = case_team["users"].get(target, str(uuid4()))
    response = client.put(
        f"/api/v1/cases/{case_team['ids'][2]}/assignment",
        headers=case_team["auth"]["admin"],
        json={"assigned_to": ident, "expected_version": 1},
    )
    assert response.status_code == 422 and response.json() == {
        "detail": "Assignee must be an active analyst"
    }
    assert assignment_events(engine) == 0


@pytest.mark.parametrize("version", [None, True, "1", 0, 2147483647])
def test_assignment_version_is_required_and_strict(platform, case_team, version):
    payload = {"assigned_to": None}
    if version is not None:
        payload["expected_version"] = version
    response = platform[0].put(
        f"/api/v1/cases/{case_team['ids'][2]}/assignment",
        headers=case_team["auth"]["admin"],
        json=payload,
    )
    assert response.status_code == 422


def test_stale_closed_and_missing_case_assignment(platform, case_team):
    client, engine, _, _ = platform
    assert assign(client, case_team).status_code == 200
    assert assign(client, case_team, target="analysttwo").status_code == 409
    with Session(engine) as session, session.begin():
        case = session.get(Case, UUID(case_team["ids"][0]))
        case.status = "closed"
    assert assign(client, case_team, index=0).status_code == 409
    response = client.put(
        f"/api/v1/cases/{uuid4()}/assignment",
        headers=case_team["auth"]["admin"],
        json={"assigned_to": None, "expected_version": 1},
    )
    assert response.status_code == 404 and assignment_events(engine) == 1


def test_assignment_noop_keeps_version_and_audit_count(platform, case_team):
    client, engine, _, _ = platform
    response = assign(client, case_team, index=0)
    assert response.status_code == 200 and response.json()["version"] == 1
    assert assignment_events(engine) == 0


@pytest.mark.parametrize("stage", ["update", "audit", "commit"])
def test_assignment_database_failure_rolls_back(platform, case_team, stage):
    client, engine, _, _ = platform

    def fail_statement(connection, cursor, statement, parameters, context, many):
        sql = statement.lower().lstrip()
        if (stage == "update" and sql.startswith("update cases")) or (
            stage == "audit" and sql.startswith("insert into audit_events")
        ):
            raise OperationalError("private-failure-marker", None, RuntimeError("must-not-leak"))

    def fail_commit(connection):
        raise OperationalError("private-failure-marker", None, RuntimeError("must-not-leak"))

    name, callback = (
        ("commit", fail_commit) if stage == "commit" else ("before_cursor_execute", fail_statement)
    )
    event.listen(engine, name, callback)
    try:
        response = assign(client, case_team)
        assert response.status_code == 503 and "private-failure" not in response.text
    finally:
        event.remove(engine, name, callback)
    with Session(engine) as session:
        case = session.get(Case, UUID(case_team["ids"][2]))
        assert case.assigned_to is None and case.version == 1
    assert assignment_events(engine) == 0
    assert assign(client, case_team).status_code == 200


def test_forged_role_claim_does_not_authorize_case_access(platform, case_team):
    client, _, settings, _ = platform
    original = case_team["auth"]["analyst"]["Authorization"].split()[1]
    claims = jwt.decode(original, options={"verify_signature": False})
    claims["role"] = "admin"
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    auth = {"Authorization": "Bearer " + token}
    assert client.get(f"/api/v1/cases/{case_team['ids'][1]}", headers=auth).status_code == 404
    assert (
        client.put(
            f"/api/v1/cases/{case_team['ids'][2]}/assignment",
            headers=auth,
            json={"assigned_to": None, "expected_version": 1},
        ).status_code
        == 403
    )


def test_revoked_supervisor_and_inactive_analyst_access(platform, case_team):
    client, engine, _, _ = platform
    with Session(engine) as session, session.begin():
        supervisor = session.get(User, UUID(case_team["users"]["supervisor"]))
        supervisor.role = "analyst"
        analyst = session.get(User, UUID(case_team["users"]["analyst"]))
        analyst.active = False
    assert assign(client, case_team).status_code == 403
    assert client.get("/api/v1/cases", headers=case_team["auth"]["supervisor"]).json()["total"] == 0
    assert (
        client.get(
            f"/api/v1/cases/{case_team['ids'][0]}", headers=case_team["auth"]["analyst"]
        ).status_code
        == 401
    )


@pytest.mark.parametrize("field", ["actor", "role", "status", "version", "disposition", "alert_id"])
def test_assignment_mass_assignment_fields_rejected(platform, case_team, field):
    body = {"assigned_to": None, "expected_version": 1, field: "forbidden"}
    response = platform[0].put(
        f"/api/v1/cases/{case_team['ids'][2]}/assignment",
        headers=case_team["auth"]["admin"],
        json=body,
    )
    assert response.status_code == 422
    assert assignment_events(platform[1]) == 0
