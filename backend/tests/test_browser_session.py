"""Short-lived HttpOnly restoration; bearer API contracts and RBAC stay unchanged."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import SESSION_COOKIE, SESSION_PATH
from app.models import User


def login(platform, **options):
    return platform[0].post(
        SESSION_PATH, json={"username": "admin", "password": platform[3]}, **options
    )


def test_browser_login_cookie_restores_original_token_without_extending_expiry(platform):
    client, _, settings, _ = platform
    response = login(platform)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "domain=" not in cookie
    assert "path=" + SESSION_PATH in cookie
    assert f"max-age={settings.access_token_minutes * 60}" in cookie
    token = response.json()["access_token"]
    restored = client.get(SESSION_PATH)
    assert restored.status_code == 200 and restored.json()["access_token"] == token
    assert restored.json()["user"]["role"] == "admin"
    assert "set-cookie" not in restored.headers
    # A session cookie never becomes implicit authorization for case/bearer APIs.
    assert client.get("/api/v1/auth/me").status_code == 401


def test_api_token_endpoint_does_not_set_or_replace_browser_cookies(platform):
    response = platform[0].post(
        "/api/v1/auth/token", json={"username": "admin", "password": platform[3]}
    )
    assert response.status_code == 200 and "set-cookie" not in response.headers


def test_one_hour_session_token_and_cookie_match_and_restore_past_fifteen_minutes(platform):
    client, _, settings, _ = platform
    settings.access_token_minutes = 60
    response = login(platform)
    assert response.status_code == 200
    assert "max-age=3600" in response.headers["set-cookie"].lower()
    claims = jwt.decode(
        response.json()["access_token"],
        settings.jwt_secret.get_secret_value(),
        algorithms=["HS256"],
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )
    assert claims["exp"] - claims["iat"] == 3600
    # A legitimately signed one-hour session remains valid after the old 15-minute limit.
    issued = datetime.now(timezone.utc) - timedelta(minutes=16)
    claims.update(iat=issued, exp=issued + timedelta(hours=1))
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    client.cookies.set(SESSION_COOKIE, token, path=SESSION_PATH)
    restored = client.get(SESSION_PATH)
    assert restored.status_code == 200 and restored.json()["access_token"] == token
    assert "set-cookie" not in restored.headers


def test_logout_clears_cookie_and_reload_cannot_restore(platform):
    login(platform)
    assert platform[0].post(SESSION_PATH + "/logout").status_code == 200
    response = platform[0].get(SESSION_PATH)
    assert response.status_code == 401 and "max-age=0" in response.headers["set-cookie"].lower()


@pytest.mark.parametrize("mode", ["expired", "forged", "inactive"])
def test_untrusted_expired_and_revoked_sessions_are_denied(platform, mode):
    client, engine, settings, _ = platform
    token = login(platform).json()["access_token"]
    if mode == "inactive":
        with Session(engine) as session, session.begin():
            user = session.scalar(select(User).where(User.username == "admin"))
            user.active = False
    else:
        claims = jwt.decode(token, options={"verify_signature": False})
        claims["iat"] = datetime.now(timezone.utc) - timedelta(minutes=20)
        claims["exp"] = (
            datetime.now(timezone.utc) - timedelta(minutes=1)
            if mode == "expired"
            else datetime.now(timezone.utc) + timedelta(minutes=1)
        )
        token = jwt.encode(
            claims,
            "wrong-signing-key-" + "x" * 40
            if mode == "forged"
            else settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )
        client.cookies.set(SESSION_COOKIE, token, path=SESSION_PATH)
    response = client.get(SESSION_PATH)
    assert response.status_code == 401 and "access_token" not in response.json()
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_restore_reads_current_role_instead_of_cached_browser_role(platform):
    login(platform)
    with Session(platform[1]) as session, session.begin():
        session.scalar(select(User).where(User.username == "admin")).role = "analyst"
    assert platform[0].get(SESSION_PATH).json()["user"]["role"] == "analyst"


@pytest.mark.parametrize(
    "method,path",
    [("post", SESSION_PATH), ("get", SESSION_PATH), ("post", SESSION_PATH + "/logout")],
)
def test_cross_site_session_actions_are_denied(platform, method, path):
    login(platform)
    kwargs = dict(headers={"Origin": "https://untrusted.example", "Sec-Fetch-Site": "cross-site"})
    if path == SESSION_PATH and method == "post":
        kwargs["json"] = {"username": "admin", "password": platform[3]}
    response = getattr(platform[0], method)(path, **kwargs)
    assert response.status_code == 403 and "set-cookie" not in response.headers


def test_trusted_same_origin_browser_session_is_allowed(platform):
    response = login(
        platform, headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}
    )
    assert response.status_code == 200


def test_nonlocal_session_cookie_requires_secure_transport(platform):
    platform[2].app_env = "production"
    response = login(platform)
    assert "secure" in response.headers["set-cookie"].lower()
