"""Container-side acceptance entry point. Configuration exists in memory only."""

import json
import os
import secrets
import sys


def main():
    import pytest
    from sqlalchemy.engine import make_url

    settings = json.loads(sys.stdin.read(65537))
    url = settings["database_url"]
    if sys.platform != "linux" or make_url(url).get_backend_name() != "postgresql":
        raise RuntimeError("linux_postgres_required")
    os.environ["DATABASE_URL"] = url
    os.environ["TRUEFLAG_TEST_POSTGRES_URL"] = url
    os.environ["JWT_SECRET"] = secrets.token_urlsafe(48)
    os.environ["TRUEFLAG_TEST_REAL_ASSESSMENT"] = "1"
    paths = (
        ["backend/tests"]
        if settings["full_backend"]
        else [
            "backend/tests/test_assessments.py",
            "backend/tests/test_assessments_postgres.py",
            "backend/tests/test_assessments_real_ml.py",
            "backend/tests/test_assessment_jobs.py",
            "backend/tests/test_assessment_worker.py",
        ]
    )
    if settings.get("jobs_only"):
        paths = ["backend/tests/test_assessment_jobs.py", "backend/tests/test_assessment_worker.py"]
    return pytest.main(
        [*paths, "-q", "--tb=short", "-p", "no:cacheprovider", "--basetemp", "/tmp/pytest"]
    )


if __name__ == "__main__":
    raise SystemExit(main())
