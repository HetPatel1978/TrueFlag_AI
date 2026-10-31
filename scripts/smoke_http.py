"""Loopback HTTP/RBAC check with generated, temporary users in the project database."""

import argparse
import json
import secrets
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

from app.core.config import Settings
from app.core.database import make_engine
from app.models import AuditEvent, User
from app.security.auth import password_hash
from sqlalchemy import delete
from sqlalchemy.orm import Session


def request(base, path, payload=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    body = json.dumps(payload).encode() if payload is not None else None
    try:
        with urlopen(Request(base + path, data=body, headers=headers), timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    if urlparse(base).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Smoke checks are restricted to the local project service")
    status, health = request(base, "/health")
    if status != 200 or health.get("service") != "trueflag-ai":
        raise RuntimeError("Unexpected local service")
    engine = make_engine(Settings().database_url)
    ids = []
    checks = 0
    try:
        for role in ["analyst", "admin"]:
            password = secrets.token_urlsafe(24)
            username = "setupcheck" + uuid4().hex
            with Session(engine) as session, session.begin():
                user = User(
                    username=username, role=role, password_hash=password_hash.hash(password)
                )
                session.add(user)
                session.flush()
                ids.append(user.id)
            code, response = request(
                base, "/api/v1/auth/token", {"username": username, "password": password}
            )
            if code != 200:
                raise RuntimeError("Local authentication failed")
            checks += 1
            token = response["access_token"]
            code, response = request(base, "/api/v1/auth/me", token=token)
            if code != 200 or response["role"] != role:
                raise RuntimeError("Server identity mismatch")
            checks += 1
            code, _ = request(base, "/api/v1/admin/audit-events", token=token)
            if code != (200 if role == "admin" else 403):
                raise RuntimeError("Server role enforcement failed")
            checks += 1
        if request(base, "/api/v1/auth/me")[0] != 401:
            raise RuntimeError("Unauthenticated identity access allowed")
        checks += 1
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(AuditEvent).where(AuditEvent.actor_id.in_(ids)))
            session.execute(delete(User).where(User.id.in_(ids)))
        engine.dispose()
    print(json.dumps({"status": "PASS", "http_checks": checks, "temporary_users_removed": True}))


if __name__ == "__main__":
    main()
