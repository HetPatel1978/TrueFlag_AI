"""Container-side acceptance entry point. Configuration exists in memory only."""

import json
import os
import secrets
import sys


class BatchRecoveryEvidence:
    """Measure complete fault scenarios; not an isolated failover/MTTR metric."""

    NAMES = {
        "test_real_linux_process_death_and_restart",
        "test_dispatcher_process_crash_recovers_without_duplicate_jobs",
        "test_dispatch_database_disconnect_rolls_back_jobs_and_links",
        "test_database_disconnect_preserves_prior_chunks_and_resumes",
        "test_actual_child_dies_when_supervisor_is_killed",
        "test_real_worker_crash_then_restart_produces_one_assessment",
        "test_actual_batch_result_cannot_publish_after_bulk_permission_revocation",
        "test_expired_ml_lease_recovery_is_reflected_in_batch_counts",
        "test_chunk_database_failure_rolls_back_all_writes",
        "test_real_scientific_stage_kill_recovers_without_partial_result",
    }

    def __init__(self):
        self.scenarios = []

    def pytest_runtest_logreport(self, report):
        name = report.nodeid.split("::")[-1].split("[")[0]
        if report.when == "call" and name in self.NAMES:
            self.scenarios.append(
                {
                    "test": report.nodeid,
                    "outcome": report.outcome,
                    "scenario_seconds": round(report.duration, 4),
                }
            )

    def pytest_sessionfinish(self, session, exitstatus):
        if self.scenarios:
            print(
                "\nTRUEFLAG_BATCH_RECOVERY:"
                + json.dumps(
                    {
                        "status": "PASS"
                        if exitstatus == 0 and all(s["outcome"] == "passed" for s in self.scenarios)
                        else "FAIL",
                        "measurement": "Complete test-call wall time, including fault injection, recovery and assertions; not production MTTR.",
                        "scenarios": self.scenarios,
                    },
                    sort_keys=True,
                )
            )


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
            "backend/tests/test_assessment_api.py",
            "backend/tests/test_assessment_api_real_ml.py",
        ]
    )
    if settings.get("jobs_only"):
        paths = ["backend/tests/test_assessment_jobs.py", "backend/tests/test_assessment_worker.py"]
    if settings.get("batch_only"):
        paths = [
            "backend/tests/test_batch_assessments.py",
            "backend/tests/test_batch_export.py",
            "backend/tests/test_batch_acceptance.py",
        ]
    if settings.get("evidence_only"):
        paths = [
            "backend/tests/test_synthetic_evidence.py",
            "backend/tests/test_evidence_foundation.py",
        ]
    return pytest.main(
        [*paths, "-q", "--tb=short", "-p", "no:cacheprovider", "--basetemp", "/tmp/pytest"],
        plugins=[BatchRecoveryEvidence()] if settings["full_backend"] else [],
    )


if __name__ == "__main__":
    raise SystemExit(main())
