"""Fixed child producer: JSON IPC only, authorized reads/computation, no result publication."""

import ctypes
import json
import os
import signal
import sys


def main():
    # Arm before reading credentials/importing the scientific stack. Close the parent-death race.
    expected_parent = int(sys.argv[1])
    if sys.platform == "linux":
        import resource

        if ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            return 1
        if os.getppid() != expected_parent:
            return 1
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
        resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))
    elif sys.platform == "win32":
        from app.workers.process_control import require_windows_child_limits

        require_windows_child_limits(3 * 1024**3)
        # Windows venv adds a launcher parent. Exact job membership plus kill-on-close
        # fences the whole tree instead of relying on its immediate parent PID.
    else:
        return 1
    payload = json.loads(sys.stdin.buffer.read(16385))
    seconds = payload["timeout_seconds"]
    if type(seconds) is not int or not 1 <= seconds <= 300:
        return 1
    if sys.platform == "linux":
        resource.setrlimit(resource.RLIMIT_CPU, (seconds + 2, seconds + 2))
    from uuid import UUID

    from sqlalchemy.engine import make_url

    from app.core.database import make_engine
    from app.core.telemetry import capture_stages
    from app.services.assessment_jobs import AssessmentJobService, Claim
    from app.services.assessments import AssessmentConflict, AssessmentNotFound

    url = make_url(payload["database_url"])
    # Also bound the existing explanation ACL callbacks, which open their own short sessions.
    options = url.query.get("options", "")
    url = url.update_query_dict(
        {
            "options": options
            + " -cstatement_timeout=5000 -clock_timeout=2000 -cidle_in_transaction_session_timeout=5000"
        }
    )
    engine = make_engine(url.render_as_string(hide_password=False))
    timing_context = capture_stages()
    timings = timing_context.__enter__()
    try:
        queue = AssessmentJobService(engine, payload["artifact_root"])
        claim = Claim(*(UUID(payload[name]) for name in ("job_id", "lease_token", "worker_id")))
        data = queue.prepare(payload["worker_token"], claim)
        result = queue.assessments._compute(
            data["actor_id"],
            data["case_id"],
            data["features"],
            data["policy"],
        )
        queue.assessments._validate_result(
            result, data["case_id"], data["features"], data["policy"], data["snapshot"]
        )
        response = {"ok": True, "result": result}
    except AssessmentNotFound:
        response = {"ok": False, "reason": "authorization_changed"}
    except AssessmentConflict:
        response = {"ok": False, "reason": "stale_case"}
    except Exception:
        response = {"ok": False, "reason": "processing_unavailable"}
    finally:
        timing_context.__exit__(None, None, None)
        engine.dispose()
    response["timings"] = timings
    sys.stdout.write(json.dumps(response, allow_nan=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1) from None
