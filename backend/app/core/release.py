"""Value-free compatibility gate shared by API and durable worker boundaries."""

import re
import sys
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.release_metadata import ReleaseCompatibilityError, load_identity, unknown_identity
from app.core.schema import EXPECTED_SCHEMA_REVISION
from trueflag_ml.policy import POLICY_SHA256
from trueflag_ml.trust import APPROVED_SHA256, CONTRACT_PATH, MODEL_PATH, MODEL_VERSION


def schema_state(connection, *, lock=False):
    try:
        bind = connection.get_bind() if hasattr(connection, "get_bind") else connection
        suffix = " FOR SHARE" if lock and bind.dialect.name == "postgresql" else ""
        revisions = list(
            connection.execute(text("SELECT version_num FROM alembic_version" + suffix)).scalars()
        )
    except SQLAlchemyError as error:
        original = getattr(error, "orig", None)
        missing = (
            getattr(original, "sqlstate", None) == "42P01"
            or str(original) == "no such table: alembic_version"
        )
        if getattr(original, "sqlstate", None) in {"55P03", "57014"}:
            return {"database": "available", "actual": "unknown", "code": "schema_unavailable"}
        return {
            "database": "available" if missing else "unavailable",
            "actual": "unknown",
            "code": "schema_missing" if missing else "database_unavailable",
        }
    actual = revisions[0] if len(revisions) == 1 else "unknown"
    if type(actual) is not str or re.fullmatch(r"[0-9]{4}_[a-z0-9_]{1,56}", actual) is None:
        actual = "unknown"
    return {
        "database": "available",
        "actual": actual,
        "code": "compatible" if revisions == [EXPECTED_SCHEMA_REVISION] else "schema_incompatible",
    }


def require_session_compatible(session):
    load_identity()
    if sys.version_info[:2] != (3, 11):
        raise ReleaseCompatibilityError("python_incompatible")
    # Hold the revision row through the caller's short transaction; do not fence
    # long RF/SHAP computation, which is rechecked separately before publication.
    state = schema_state(session, lock=True)
    if state["code"] != "compatible":
        raise ReleaseCompatibilityError(state["code"])


@contextmanager
def _probe(engine):
    with engine.connect() as connection:
        if engine.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL lock_timeout='1s'"))
            connection.execute(text("SET LOCAL statement_timeout='2s'"))
        yield connection


def require_compatible(engine):
    try:
        with _probe(engine) as connection:
            require_session_compatible(connection)
    except ReleaseCompatibilityError:
        raise
    except SQLAlchemyError:
        raise ReleaseCompatibilityError("database_unavailable") from None


def verify_worker_artifacts():
    # Original verification functions; no pickle load, fit, score, SHAP or uploaded paths.
    from trueflag_ml.explainability import verify_explanation_runtime
    from trueflag_ml.loader import DEFAULT_ROOT, _verified_bundle, verify_runtime
    from trueflag_ml.policy import load_approved_policy

    try:
        _verified_bundle(DEFAULT_ROOT)
        verify_runtime()
        verify_explanation_runtime()
        load_approved_policy()
    except Exception:
        raise ReleaseCompatibilityError("ml_incompatible") from None
    return "sha256_and_dependencies_verified_not_deserialized"


def worker_identity(ml_verification="not_required"):
    identity = load_identity()
    return {
        key: identity[key]
        for key in (
            "contract",
            "git_commit",
            "build_id",
            "source_sha256",
            "worker_version",
            "metadata_status",
            "image_digest",
        )
    } | {"ml_verification": ml_verification}


def release_report(engine):
    try:
        identity = load_identity()
        code = "compatible" if sys.version_info[:2] == (3, 11) else "python_incompatible"
    except ReleaseCompatibilityError as error:
        identity = {**unknown_identity(), "metadata_status": "invalid"}
        code = error.code
    try:
        with _probe(engine) as connection:
            state = schema_state(connection)
    except SQLAlchemyError:
        state = {"database": "unavailable", "actual": "unknown", "code": "database_unavailable"}
    if code == "compatible":
        code = state["code"]
    clock = "not_checked"
    if code == "compatible" and engine.dialect.name == "postgresql":
        # Retain a detected regression even if the caller only checks readiness.
        from app.services.snapshot_clock import ClockUnavailable, SnapshotTime

        try:
            SnapshotTime(engine).observe()
            clock = "available"
        except ClockUnavailable:
            clock = "unavailable"
            code = "snapshot_clock_unavailable"
    return {
        "status": "ready" if code == "compatible" else "not_ready",
        "process": "healthy",
        "compatibility": code,
        "release": identity,
        "schema": {"expected": EXPECTED_SCHEMA_REVISION, "actual": state["actual"]},
        "dependencies": {
            "database": state["database"],
            "snapshot_clock": clock,
            "workers": "asynchronous_not_required_for_api_readiness",
        },
        "ml": {
            "model_version": MODEL_VERSION,
            "model_sha256": APPROVED_SHA256[MODEL_PATH],
            "contract_sha256": APPROVED_SHA256[CONTRACT_PATH],
            "policy_sha256": POLICY_SHA256,
            "verification": "not_checked_in_api_process",
        },
    }
