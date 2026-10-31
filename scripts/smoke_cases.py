"""Loopback case-access/assignment checks using only generated, temporary synthetic records."""

import argparse
import json
import secrets
from urllib.parse import urlparse
from uuid import uuid4

from app.core.config import Settings
from app.core.database import make_engine
from app.models import Alert, AlertIngestion, AuditEvent, Case, User
from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.security.auth import password_hash
from smoke_http import request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8088")
    base = parser.parse_args().base_url.rstrip("/")
    if urlparse(base).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("Loopback checks only")
    if request(base, "/ready")[0] != 200:
        raise RuntimeError("Project API is not ready")
    engine = make_engine(Settings().database_url)
    ids = []
    tokens = {}
    source = "case-smoke-" + uuid4().hex
    checks = 0
    try:
        for name, role in [
            ("a", "analyst"),
            ("b", "analyst"),
            ("supervisor", "supervisor"),
            ("admin", "admin"),
        ]:
            username, password = "casecheck" + uuid4().hex, secrets.token_urlsafe(24)
            with Session(engine) as session, session.begin():
                user = User(
                    username=username, role=role, password_hash=password_hash.hash(password)
                )
                session.add(user)
                session.flush()
                ident = str(user.id)
                ids.append(user.id)
            code, body = request(
                base, "/api/v1/auth/token", {"username": username, "password": password}
            )
            if code != 200:
                raise RuntimeError("Temporary authentication failed")
            tokens[name] = (body["access_token"], ident)
            checks += 1
        features = {name: 0 for name in AlertFeatures.model_fields}
        features.update(state="ZZ", income=None, kycRiskScore=3)
        payload = {
            "source_id": source,
            "data_classification": "synthetic",
            "feature_contract_version": FEATURE_CONTRACT_VERSION,
            "features": features,
        }
        code, body = request(base, "/api/v1/alerts", payload, tokens["admin"][0], str(uuid4()))
        if code != 201:
            raise RuntimeError("Synthetic case creation failed")
        path = "/api/v1/cases/" + body["case_id"]
        checks += 1

        def expect(role, status, suffix=""):
            nonlocal checks
            code, result = request(base, path + suffix, token=tokens[role][0])
            if code != status:
                raise RuntimeError("Case visibility check failed")
            checks += 1
            return result

        expect("a", 404)
        expect("supervisor", 200)
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        def assign(target, version, expected):
            nonlocal checks
            payload = {
                "assigned_to": tokens[target][1] if target else None,
                "expected_version": version,
            }
            req = Request(
                base + path + "/assignment",
                method="PUT",
                data=json.dumps(payload).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + tokens["supervisor"][0],
                },
            )
            try:
                with urlopen(req, timeout=10) as response:
                    code = response.status
            except HTTPError as error:
                code = error.code
            if code != expected:
                raise RuntimeError("Assignment check failed")
            checks += 1

        assign("a", 1, 200)
        expect("a", 200)
        expect("b", 404)
        assign("b", 2, 200)
        expect("a", 404)
        expect("b", 200)
        assign("a", 2, 409)
        assign(None, 3, 200)
        expect("b", 404)
        code, page = request(base, "/api/v1/cases", token=tokens["a"][0])
        if code != 200 or page["total"] != 0:
            raise RuntimeError("Analyst list isolation failed")
        checks += 1
    finally:
        with Session(engine) as session, session.begin():
            session.execute(delete(AuditEvent).where(AuditEvent.actor_id.in_(ids)))
            alert_id = session.scalar(select(Alert.id).where(Alert.source_id == source))
            if alert_id:
                session.execute(delete(AlertIngestion).where(AlertIngestion.alert_id == alert_id))
                session.execute(delete(Case).where(Case.alert_id == alert_id))
                session.execute(delete(Alert).where(Alert.id == alert_id))
            session.execute(delete(User).where(User.id.in_(ids)))
        engine.dispose()
    print(
        json.dumps(
            {"status": "PASS", "case_http_checks": checks, "temporary_records_removed": True}
        )
    )


if __name__ == "__main__":
    main()
