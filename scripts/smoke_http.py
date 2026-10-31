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
from app.models import Alert, AlertIngestion, AuditEvent, Case, User
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.security.auth import password_hash
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def request(base, path, payload=None, token=None, key=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    if key:
        headers["Idempotency-Key"] = key
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
    key = str(uuid4())
    features = {name: 0 for name in AlertFeatures.model_fields}
    features.update(state="ZZ", kycRiskScore=3, income=None)
    payload = {
        "source_id": "smoke-" + uuid4().hex,
        "data_classification": "synthetic",
        "feature_contract_version": FEATURE_CONTRACT_VERSION,
        "features": features,
    }
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
            code, receipt = request(base, "/api/v1/alerts", payload, token, key)
            if code != (201 if role == "admin" else 403):
                raise RuntimeError("Ingestion role enforcement or creation failed")
            checks += 1
            if role == "admin":
                if (
                    receipt["scoring_status"] != "not_requested"
                    or receipt["routing_status"] != "not_evaluated"
                ):
                    raise RuntimeError("Ingestion unexpectedly scored or routed an alert")
                code, replay = request(base, "/api/v1/alerts", payload, token, key)
                if code != 200 or replay != receipt:
                    raise RuntimeError("Ingestion replay is not idempotent")
                checks += 1
                changed = {**payload, "features": {**features, "income": 0}}
                if request(base, "/api/v1/alerts", changed, token, key)[0] != 409:
                    raise RuntimeError("Conflicting ingestion was accepted")
                checks += 1
        if request(base, "/api/v1/auth/me")[0] != 401:
            raise RuntimeError("Unauthenticated identity access allowed")
        checks += 1
        if request(base, "/api/v1/alerts", payload, key=key)[0] != 401:
            raise RuntimeError("Unauthenticated ingestion was accepted")
        checks += 1
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(AuditEvent).where(AuditEvent.actor_id.in_(ids)))
            alert_id = session.scalar(
                select(Alert.id).where(Alert.source_id == payload["source_id"])
            )
            if alert_id is not None:
                session.execute(delete(AlertIngestion).where(AlertIngestion.alert_id == alert_id))
                session.execute(delete(Case).where(Case.alert_id == alert_id))
                session.execute(delete(Alert).where(Alert.id == alert_id))
            session.execute(delete(User).where(User.id.in_(ids)))
        engine.dispose()
    print(
        json.dumps(
            {
                "status": "PASS",
                "http_checks": checks,
                "temporary_users_removed": True,
                "temporary_ingestion_removed": True,
            }
        )
    )


if __name__ == "__main__":
    main()
