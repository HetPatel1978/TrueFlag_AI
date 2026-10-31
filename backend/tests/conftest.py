import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from alembic import command
from app.core.config import Settings
from app.core.database import make_engine
from app.main import create_app
from app.models import Case, User
from app.security.auth import password_hash

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def platform(request, monkeypatch):
    postgres = os.environ.get("TRUEFLAG_TEST_POSTGRES_URL")
    owner = None
    schema = None
    if postgres:
        if make_url(postgres).get_backend_name() != "postgresql":
            raise ValueError("TRUEFLAG_TEST_POSTGRES_URL must select PostgreSQL")
        owner = make_engine(postgres)
        schema = "tf_ingestion_test_" + uuid4().hex
        with owner.begin() as connection:
            connection.execute(CreateSchema(schema))
        url = (
            make_url(postgres)
            .update_query_dict({"options": "-csearch_path=" + schema})
            .render_as_string(hide_password=False)
        )
    else:
        tmp_path = request.getfixturevalue("tmp_path")
        url = "sqlite+pysqlite:///" + (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    engine = None
    try:
        command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
        settings = Settings()
        engine = make_engine(url)
        password = secrets.token_urlsafe(24)
        with Session(engine) as session, session.begin():
            for name, role in [("admin", "admin"), ("analyst", "analyst")]:
                session.add(
                    User(username=name, role=role, password_hash=password_hash.hash(password))
                )
        with TestClient(create_app(settings, engine)) as client:
            yield client, engine, settings, password
    finally:
        if engine is not None:
            engine.dispose()
        if owner is not None:
            with owner.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            owner.dispose()


@pytest.fixture
def alert_payload():
    from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures

    fields = {name: 0 for name in AlertFeatures.model_fields}
    fields.update(state="ZZ", kycRiskScore=3, income=None)
    return {
        "source_id": "synthetic-test-001",
        "data_classification": "synthetic",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "features": fields,
    }


@pytest.fixture
def admin_headers(platform):
    from test_foundation import headers

    return {**headers(platform), "Idempotency-Key": str(uuid4())}


@pytest.fixture
def case_team(platform, alert_payload):
    from copy import deepcopy

    from sqlalchemy import select
    from test_foundation import headers

    client, engine, _, password = platform
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                User(
                    username="analysttwo",
                    role="analyst",
                    password_hash=password_hash.hash(password),
                ),
                User(
                    username="supervisor",
                    role="supervisor",
                    password_hash=password_hash.hash(password),
                ),
                User(
                    username="inactive",
                    role="analyst",
                    active=False,
                    password_hash=password_hash.hash(password),
                ),
            ]
        )
    with Session(engine) as session:
        users = {user.username: str(user.id) for user in session.scalars(select(User))}
    auth = {
        name: headers(platform, name) for name in ["admin", "analyst", "analysttwo", "supervisor"]
    }
    receipts = []
    for index in range(4):
        payload = deepcopy(alert_payload)
        payload["source_id"] = f"phase1-synthetic-{index}"
        payload["features"]["income"] = (index + 1) * 1001
        response = client.post(
            "/api/v1/alerts",
            json=payload,
            headers={**auth["admin"], "Idempotency-Key": str(uuid4())},
        )
        assert response.status_code == 201
        receipts.append(response.json())
    with Session(engine) as session, session.begin():
        for index, assignee in enumerate(["analyst", "analysttwo", None, "analyst"]):
            case = session.get(Case, UUID(receipts[index]["case_id"]))
            case.assigned_to = UUID(users[assignee]) if assignee else None
            case.created_at = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
            if index == 3:
                case.status = "in_review"
    return {"auth": auth, "users": users, "ids": [r["case_id"] for r in receipts]}
