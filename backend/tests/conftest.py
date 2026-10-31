import os
import secrets
from pathlib import Path
from uuid import uuid4

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
from app.models import User
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
