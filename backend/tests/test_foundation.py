from datetime import datetime, timedelta, timezone

import jwt
import pytest
from alembic.config import Config
from conftest import BACKEND
from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.models import Alert, AuditEvent, ModelScore, User


def headers(platform, username="admin"):
    client, _, _, password = platform
    response = client.post("/api/v1/auth/token", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_health_and_migrated_readiness(platform):
    client, engine, _, _ = platform
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/ready").status_code == 200
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "users",
        "alerts",
        "cases",
        "evidence",
        "model_scores",
        "decisions",
        "audit_events",
    }


def test_readiness_fails_after_schema_removed(platform):
    client, _, _, _ = platform
    command.downgrade(Config(str(BACKEND / "alembic.ini")), "base")
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize("endpoint", ["/api/v1/auth/me", "/api/v1/admin/audit-events"])
def test_auth_required(platform, endpoint):
    assert platform[0].get(endpoint).status_code == 401


def test_server_enforces_role(platform):
    client = platform[0]
    assert (
        client.get("/api/v1/auth/me", headers=headers(platform, "analyst")).json()["role"]
        == "analyst"
    )
    assert (
        client.get("/api/v1/admin/audit-events", headers=headers(platform, "analyst")).status_code
        == 403
    )
    assert client.get("/api/v1/admin/audit-events", headers=headers(platform)).status_code == 200


def test_extra_role_is_rejected(platform):
    client, _, _, password = platform
    response = client.post(
        "/api/v1/auth/token", json={"username": "analyst", "password": password, "role": "admin"}
    )
    assert response.status_code == 422


def test_passwords_are_hashed_and_failure_is_audited(platform):
    client, engine, _, password = platform
    assert (
        client.post(
            "/api/v1/auth/token", json={"username": "unknown", "password": password}
        ).status_code
        == 401
    )
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.username == "admin"))
        assert user.password_hash.startswith("$argon2") and password not in user.password_hash
        assert session.scalar(select(AuditEvent).where(AuditEvent.action == "auth.login_failed"))


@pytest.mark.parametrize(
    "mutation", ["expired", "wrong_audience", "wrong_issuer", "missing_expiry", "wrong_signature"]
)
def test_invalid_tokens_rejected(platform, mutation):
    client, engine, settings, _ = platform
    with Session(engine) as session:
        user = session.scalar(select(User).where(User.username == "admin"))
        ident = str(user.id)
    now = datetime.now(timezone.utc)
    claims = {
        "sub": ident,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "aud": settings.jwt_audience,
        "iss": settings.jwt_issuer,
    }
    secret = settings.jwt_secret.get_secret_value()
    if mutation == "expired":
        claims["exp"] = now - timedelta(seconds=1)
    if mutation == "wrong_audience":
        claims["aud"] = "other-service"
    if mutation == "wrong_issuer":
        claims["iss"] = "other-issuer"
    if mutation == "missing_expiry":
        claims.pop("exp")
    if mutation == "wrong_signature":
        secret = "untrusted-signature-key-with-sufficient-length"
    token = jwt.encode(claims, secret, algorithm="HS256")
    assert (
        client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_revocation_and_role_changes_apply_immediately(platform):
    client, engine, _, _ = platform
    auth = headers(platform)
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.username == "admin"))
        user.role = "analyst"
    assert client.get("/api/v1/admin/audit-events", headers=auth).status_code == 403
    with Session(engine) as session, session.begin():
        user = session.scalar(select(User).where(User.username == "admin"))
        user.active = False
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401


def test_invalid_score_rollback(platform):
    _, engine, _, _ = platform
    with Session(engine) as session:
        alert = Alert(
            source_id="synthetic-fixture",
            feature_contract_version="test",
            features={},
            input_sha256="0" * 64,
        )
        session.add(alert)
        session.commit()
        session.add(
            ModelScore(
                alert_id=alert.id,
                model_version="test",
                model_sha256="0" * 64,
                input_sha256="0" * 64,
                status="processed",
                score=1.2,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        assert session.scalars(select(ModelScore)).all() == []


def test_short_secret_rejected():
    with pytest.raises(ValidationError):
        Settings(jwt_secret="short")


def test_no_fake_business_endpoints(platform):
    client = platform[0]
    assert client.get("/api/v1/predict").status_code == 404
    assert client.post("/api/v1/investigate", json={}).status_code == 404
    assert client.get("/health").headers["cache-control"] == "no-store"
