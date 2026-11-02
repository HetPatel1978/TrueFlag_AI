"""Check the configured PostgreSQL schema and rollback without retaining test records."""

import json
from uuid import uuid4

from app.core.config import Settings
from app.core.database import make_engine
from app.core.schema import EXPECTED_SCHEMA_REVISION
from app.models import AuditEvent
from sqlalchemy import inspect, select, text
from sqlalchemy.orm import Session


def main() -> None:
    engine = make_engine(Settings().database_url)
    try:
        if engine.dialect.name != "postgresql":
            raise RuntimeError("This check requires real PostgreSQL, not SQLite")
        with engine.connect() as connection:
            revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
            if revision != EXPECTED_SCHEMA_REVISION:
                raise RuntimeError("Apply the current service migration first")
        tables = set(inspect(engine).get_table_names())
        expected = {
            "users",
            "alerts",
            "cases",
            "evidence",
            "model_scores",
            "decisions",
            "audit_events",
            "alert_ingestions",
            "login_throttles",
            "assessments",
            "assessment_explanations",
            "assessment_jobs",
            "assessment_workers",
            "assessment_api_throttles",
            "operational_metrics",
            "csv_uploads",
            "csv_validations",
            "csv_validation_issues",
        }
        if not expected <= tables:
            raise RuntimeError("Missing domain tables")
        probe = str(uuid4())
        with Session(engine) as session:
            session.add(AuditEvent(action="verification.rollback", resource_id=probe))
            session.flush()
            session.rollback()
            if (
                session.scalar(select(AuditEvent).where(AuditEvent.resource_id == probe))
                is not None
            ):
                raise RuntimeError("Rollback did not remove probe")
        print(
            json.dumps(
                {
                    "status": "PASS",
                    "database": "PostgreSQL",
                    "revision": revision,
                    "domain_tables": len(expected),
                    "rollback": "PASS",
                    "retained_test_records": 0,
                }
            )
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
