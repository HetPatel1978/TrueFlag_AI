"""Durable, revocable local-account browser grants; synthetic accounts only."""

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from test_browser_session import login

from app.api.routes import SESSION_COOKIE, SESSION_PATH
from app.main import create_app
from app.models import AuditEvent, User
from app.security.auth import password_hash
from app.security.browser_sessions import CREATED, PREFIX, REVOKED


def remembered(platform):
    platform[2].app_env = "local"
    platform[2].access_token_minutes = 60
    platform[2].local_persistent_login_username = "admin"
    response = login(platform)
    assert response.status_code == 200
    return response, platform[0].cookies.get(SESSION_COOKIE)


def test_remembered_cookie_is_opaque_persistent_and_only_hash_is_stored(platform):
    response, cookie = remembered(platform)
    assert (
        cookie.startswith(PREFIX) and "max-age=31536000" in response.headers["set-cookie"].lower()
    )
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    assert claims["exp"] - claims["iat"] == 3600
    with Session(platform[1]) as session:
        grant = session.scalar(select(AuditEvent).where(AuditEvent.action == CREATED))
        assert grant.details["token_sha256"] == hashlib.sha256(cookie.encode()).hexdigest()
        assert cookie not in str(grant.details)
        assert str(grant.id) == claims["sid"]
    restored = platform[0].get(SESSION_PATH)
    assert restored.status_code == 200 and restored.json()["user"]["username"] == "admin"
    assert "max-age=31536000" in restored.headers["set-cookie"].lower()
    assert platform[0].get("/api/v1/auth/me").status_code == 401


def test_expired_access_token_can_be_renewed_only_through_valid_remembered_cookie(platform):
    response, _ = remembered(platform)
    settings = platform[2]
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    claims.update(
        iat=datetime.now(timezone.utc) - timedelta(hours=2),
        exp=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    expired = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        platform[0]
        .get("/api/v1/auth/me", headers={"Authorization": "Bearer " + expired})
        .status_code
        == 401
    )
    restored = platform[0].get(SESSION_PATH)
    assert restored.status_code == 200
    fresh = restored.json()["access_token"]
    assert (
        platform[0].get("/api/v1/auth/me", headers={"Authorization": "Bearer " + fresh}).status_code
        == 200
    )


def test_remembered_grant_survives_new_application_instance(platform):
    _, cookie = remembered(platform)
    with TestClient(create_app(platform[2], platform[1])) as restarted:
        restarted.cookies.set(SESSION_COOKIE, cookie, path=SESSION_PATH)
        assert restarted.get(SESSION_PATH).status_code == 200


def test_logout_revokes_cookie_and_issued_bearer_and_prevents_replay(platform):
    response, cookie = remembered(platform)
    bearer = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert platform[0].post(SESSION_PATH + "/logout").status_code == 200
    assert platform[0].get("/api/v1/auth/me", headers=bearer).status_code == 401
    platform[0].cookies.set(SESSION_COOKIE, cookie, path=SESSION_PATH)
    assert platform[0].get(SESSION_PATH).status_code == 401
    with Session(platform[1]) as session:
        assert (
            len(session.scalars(select(AuditEvent).where(AuditEvent.action == REVOKED)).all()) == 1
        )


@pytest.mark.parametrize("change", ["disabled", "password", "role", "username_setting", "nonlocal"])
def test_revoked_credentials_and_scope_cannot_restore_or_use_old_bearer(platform, change):
    response, _ = remembered(platform)
    if change in {"disabled", "password", "role"}:
        with Session(platform[1]) as session, session.begin():
            user = session.scalar(select(User).where(User.username == "admin"))
            if change == "disabled":
                user.active = False
            elif change == "password":
                user.password_hash = password_hash.hash("replacement-synthetic-password")
            else:
                user.role = "analyst"
    elif change == "username_setting":
        platform[2].local_persistent_login_username = ""
    else:
        platform[2].app_env = "production"
    bearer = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert platform[0].get("/api/v1/auth/me", headers=bearer).status_code == 401
    assert platform[0].get(SESSION_PATH).status_code == 401


def test_tampered_cookie_and_wrong_account_grant_are_denied(platform):
    response, cookie = remembered(platform)
    claims = jwt.decode(response.json()["access_token"], options={"verify_signature": False})
    with Session(platform[1]) as session:
        claims["sub"] = str(session.scalar(select(User.id).where(User.username == "analyst")))
    forged_actor = jwt.encode(claims, platform[2].jwt_secret.get_secret_value(), algorithm="HS256")
    assert (
        platform[0]
        .get("/api/v1/auth/me", headers={"Authorization": "Bearer " + forged_actor})
        .status_code
        == 401
    )
    prefix, secret = cookie.rsplit(".", 1)
    bad = prefix + "." + ("A" if secret[0] != "A" else "B") + secret[1:]
    platform[0].cookies.set(SESSION_COOKIE, bad, path=SESSION_PATH)
    assert platform[0].get(SESSION_PATH).status_code == 401


def test_only_configured_local_account_is_remembered_and_api_login_stays_stateless(platform):
    platform[2].local_persistent_login_username = "anotheraccount"
    assert not platform[0].cookies.get(SESSION_COOKIE)
    response = login(platform)
    assert not platform[0].cookies.get(SESSION_COOKIE).startswith(PREFIX)
    assert "max-age=3600" in response.headers["set-cookie"].lower()
    platform[2].local_persistent_login_username = "admin"
    platform[0].cookies.clear()
    api = platform[0].post(
        "/api/v1/auth/token", json={"username": "admin", "password": platform[3]}
    )
    assert api.status_code == 200 and "set-cookie" not in api.headers
    claims = jwt.decode(api.json()["access_token"], options={"verify_signature": False})
    assert "sid" not in claims


def test_relogin_rotates_grant_and_invalidates_previous_remembered_access(platform):
    original, _ = remembered(platform)
    assert login(platform).status_code == 200
    assert (
        platform[0]
        .get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + original.json()["access_token"]},
        )
        .status_code
        == 401
    )


def test_failed_logout_rolls_back_revocation_and_does_not_claim_cookie_cleared(platform):
    remembered(platform)

    def reject_revocation(session, context, instances):
        if any(isinstance(row, AuditEvent) and row.action == REVOKED for row in session.new):
            raise SQLAlchemyError("synthetic-revocation-failure")

    event.listen(Session, "before_flush", reject_revocation)
    try:
        response = platform[0].post(SESSION_PATH + "/logout")
    finally:
        event.remove(Session, "before_flush", reject_revocation)
    assert response.status_code == 503 and "set-cookie" not in response.headers
    assert "synthetic-revocation-failure" not in response.text
    assert platform[0].get(SESSION_PATH).status_code == 200
    with Session(platform[1]) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == REVOKED)
            )
            == 0
        )


@pytest.mark.parametrize("path,method", [(SESSION_PATH, "get"), (SESSION_PATH + "/logout", "post")])
def test_cross_site_requests_cannot_refresh_or_revoke_remembered_login(platform, path, method):
    remembered(platform)
    response = getattr(platform[0], method)(
        path, headers={"Origin": "https://untrusted.example", "Sec-Fetch-Site": "cross-site"}
    )
    assert response.status_code == 403 and "set-cookie" not in response.headers
    assert platform[0].get(SESSION_PATH).status_code == 200


@pytest.mark.skipif(
    not os.environ.get("TRUEFLAG_TEST_POSTGRES_URL"), reason="PostgreSQL locking acceptance"
)
def test_concurrent_restore_and_logout_cannot_resurrect_revoked_grant(platform):
    response, cookie = remembered(platform)
    headers = {"Cookie": SESSION_COOKIE + "=" + cookie}
    with ThreadPoolExecutor(max_workers=2) as pool:
        restore = pool.submit(platform[0].get, SESSION_PATH, headers=headers)
        logout = pool.submit(platform[0].post, SESSION_PATH + "/logout", headers=headers)
        restored, ended = restore.result(), logout.result()
    assert ended.status_code == 200 and restored.status_code in {200, 401}
    tokens = [response.json()["access_token"]]
    if restored.status_code == 200:
        tokens.append(restored.json()["access_token"])
    for token in tokens:
        assert (
            platform[0]
            .get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
            .status_code
            == 401
        )
    assert platform[0].get(SESSION_PATH, headers=headers).status_code == 401
    with Session(platform[1]) as session:
        assert (
            session.scalar(
                select(func.count()).select_from(AuditEvent).where(AuditEvent.action == REVOKED)
            )
            == 1
        )
