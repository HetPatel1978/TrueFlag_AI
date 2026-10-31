import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import JSONResponse

from app.main import create_app
from app.models import LoginThrottle
from app.security import throttle
from app.security.logging import SecurityFormatter
from app.security.request_guard import RequestGuardMiddleware


def test_login_limit_is_persistent_and_does_not_trust_forwarded_header(platform):
    client, engine, settings, password = platform
    settings.login_attempt_limit = 2
    body = {"username": "admin", "password": password}
    assert client.post("/api/v1/auth/token", json=body).status_code == 200
    assert (
        client.post("/api/v1/auth/token", json={**body, "password": "incorrect"}).status_code == 401
    )
    response = client.post(
        "/api/v1/auth/token", json=body, headers={"X-Forwarded-For": "192.0.2.50"}
    )
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0
    with TestClient(create_app(settings, engine)) as restarted:
        assert restarted.post("/api/v1/auth/token", json=body).status_code == 429
    with Session(engine) as session:
        row = session.scalar(select(LoginThrottle))
        assert row.attempt_count == 2 and len(row.key_sha256) == 64
        assert "testclient" not in row.key_sha256


def test_login_window_resets_and_active_sessions_keep_working(platform, monkeypatch):
    client, _, settings, password = platform
    settings.login_attempt_limit = 1
    fixed = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(throttle, "utcnow", lambda: fixed)
    body = {"username": "admin", "password": password}
    first = client.post("/api/v1/auth/token", json=body)
    assert first.status_code == 200
    assert client.post("/api/v1/auth/token", json=body).status_code == 429
    assert (
        client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer " + first.json()["access_token"]}
        ).status_code
        == 200
    )
    monkeypatch.setattr(throttle, "utcnow", lambda: fixed + timedelta(seconds=61))
    assert client.post("/api/v1/auth/token", json=body).status_code == 200


def test_request_ids_are_server_generated_and_logs_do_not_include_sensitive_values(
    platform, caplog
):
    client = platform[0]
    with caplog.at_level(logging.INFO, logger="trueflag.security"):
        response = client.post(
            "/api/v1/auth/token?private-query-marker=1",
            json={"username": "unknown", "password": "private-password-marker"},
            headers={"X-Request-ID": "private-request-marker"},
        )
    assert response.status_code == 401
    ident = response.headers["x-request-id"]
    assert len(ident) == 32 and ident != "private-request-marker"
    records = [row for row in caplog.records if row.name == "trueflag.security"]
    assert any(row.request_id == ident and row.status_code == 401 for row in records)
    assert "private-" not in " ".join(str(row.__dict__) for row in records)


def test_large_login_body_rejected_before_authentication(platform):
    client, engine, settings, _ = platform
    response = client.post("/api/v1/auth/token", content=b"x" * (settings.max_request_bytes + 1))
    assert response.status_code == 413
    assert response.headers["x-request-id"] and response.headers["cache-control"] == "no-store"
    with Session(engine) as session:
        assert session.scalar(select(LoginThrottle)) is None


@pytest.mark.parametrize("declared", [None, b"2", b"50"])
def test_streaming_and_misdeclared_body_limits(declared):
    sent = []
    calls = []
    chunks = iter(
        [
            {"type": "http.request", "body": b"12345", "more_body": True},
            {"type": "http.request", "body": b"67890", "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        calls.append(True)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/",
        "headers": [] if declared is None else [(b"content-length", declared)],
    }
    asyncio.run(RequestGuardMiddleware(downstream, 8)(scope, receive, send))
    assert sent[0]["status"] == 413 and not calls


def test_unexpected_errors_are_neutral_and_logs_omit_exception_values(caplog):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        raise RuntimeError("private-exception-marker")

    with caplog.at_level(logging.ERROR, logger="trueflag.security"):
        asyncio.run(
            RequestGuardMiddleware(downstream, 8)(
                {"type": "http", "method": "GET", "path": "/", "headers": []}, receive, send
            )
        )
    assert sent[0]["status"] == 500
    assert "private-exception-marker" not in str(sent) + caplog.text


def test_small_stream_is_replayed_exactly():
    sent = []
    chunks = iter(
        [
            {"type": "http.request", "body": b"abc", "more_body": True},
            {"type": "http.request", "body": b"def", "more_body": False},
        ]
    )

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    async def downstream(scope, receive, send):
        assert (await receive())["body"] == b"abcdef"
        await JSONResponse({"ok": True})(scope, receive, send)

    asyncio.run(
        RequestGuardMiddleware(downstream, 8)(
            {"type": "http", "method": "POST", "path": "/", "headers": []}, receive, send
        )
    )
    assert sent[0]["status"] == 200


def test_security_formatter_does_not_render_unknown_message_or_exception_values():
    record = logging.LogRecord(
        "trueflag.security", logging.ERROR, "test", 1, "private-message-marker", (), None
    )
    record.exc_text = "private-exception-marker"
    rendered = SecurityFormatter().format(record)
    assert "private-" not in rendered and "security.event" in rendered
