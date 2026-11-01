"""Linux supervisor: renewable leases, bounded JSON subprocess IPC and fenced publication."""

import argparse
import json
import logging
import math
import os
import selectors
import signal
import subprocess
import sys
import threading
import time
from uuid import uuid4

from app.core.telemetry import Registry
from app.services.assessment_jobs import (
    AssessmentJobService,
    JobError,
    JobUnavailable,
    LeaseLost,
    WorkerDenied,
)
from app.services.assessments import AssessmentConflict, AssessmentError, AssessmentNotFound


class ExecutionFailed(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _kill(process):
    try:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait(timeout=3)


class IsolatedRunner:
    def __init__(self, stop=None):
        if sys.platform != "linux":
            raise JobUnavailable("linux_worker_required")
        self.stop = threading.Event() if stop is None else stop
        self.last_timings = {}

    def _command(self):
        return [sys.executable, "-B", "-m", "app.workers.assessment_child", str(os.getpid())]

    def run(self, queue, token, claim):
        self.last_timings = {}
        config = {
            "database_url": queue.engine.url.render_as_string(hide_password=False),
            "worker_token": token,
            "job_id": str(claim.job_id),
            "lease_token": str(claim.lease_token),
            "worker_id": str(claim.worker_id),
            "artifact_root": str(queue.assessments.artifact_root)
            if queue.assessments.artifact_root
            else None,
            "timeout_seconds": queue.limits.timeout_seconds,
        }
        # Pass secrets over a private pipe. Child gets no inherited application credentials.
        env = {
            k: v
            for k, v in os.environ.items()
            if k
            in {
                "PATH",
                "PYTHONPATH",
                "PYTHONDONTWRITEBYTECODE",
                "NUMBA_CACHE_DIR",
                "MPLCONFIGDIR",
            }
        }
        for name in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]:
            env[name] = "1"
        process = subprocess.Popen(
            self._command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
        start = time.monotonic()
        next_heartbeat = start + queue.limits.heartbeat_seconds
        deadline = start + queue.limits.timeout_seconds
        output = bytearray()
        timed_out = threading.Event()

        def timeout():
            timed_out.set()
            _kill(process)

        watchdog = threading.Timer(queue.limits.timeout_seconds, timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            process.stdin.write(json.dumps(config).encode())
            process.stdin.close()
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while selector.get_map() or process.poll() is None:
                    now = time.monotonic()
                    if self.stop.is_set():
                        raise ExecutionFailed("processing_unavailable")
                    if now >= deadline:
                        raise ExecutionFailed("execution_timeout")
                    if now >= next_heartbeat:
                        queue.heartbeat(token, claim)
                        next_heartbeat = time.monotonic() + queue.limits.heartbeat_seconds
                    for key, _ in selector.select(
                        max(0, min(0.2, deadline - now, next_heartbeat - now))
                    ):
                        chunk = os.read(key.fd, 16384)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        output.extend(chunk)
                        if len(output) > 262144:
                            raise ExecutionFailed("invalid_child_output")
            if timed_out.is_set() or time.monotonic() >= deadline:
                raise ExecutionFailed("execution_timeout")
            if process.returncode != 0:
                raise ExecutionFailed("child_failed")
            try:
                response = json.loads(
                    output, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
                )
                if type(response) is not dict or type(response.get("ok")) is not bool:
                    raise ValueError
                timings = response.get("timings", {})
                if (
                    type(timings) is not dict
                    or len(timings) > 3
                    or any(
                        name not in {"model.initialization", "model.scoring", "model.shap"}
                        or type(value) not in (int, float)
                        or not math.isfinite(value)
                        or not 0 <= value <= 3600000
                        for name, value in timings.items()
                    )
                ):
                    raise ValueError
                self.last_timings = timings
                if not response["ok"]:
                    reason = response.get("reason")
                    raise ExecutionFailed(
                        reason
                        if reason
                        in {
                            "authorization_changed",
                            "stale_case",
                            "processing_unavailable",
                        }
                        else "child_failed"
                    )
                if (
                    set(response) - {"timings"} != {"ok", "result"}
                    or type(response["result"]) is not dict
                ):
                    raise ValueError
                return response["result"]
            except (ValueError, TypeError):
                raise ExecutionFailed("invalid_child_output") from None
        finally:
            watchdog.cancel()
            watchdog.join(timeout=3)
            _kill(process)
            process.stdout.close()


class AssessmentWorker:
    def __init__(self, queue, token, stop=None):
        self.queue = queue
        self.token = token
        self.runner = IsolatedRunner(stop)
        self.telemetry = Registry()

    def run_once(self):
        self.telemetry.observe("worker.recovery_scan")
        recovered = self.queue.recover_expired(self.token)
        if recovered:
            self.telemetry.observe("worker.recovered", count=recovered)
        claim = self.queue.claim(self.token)
        if claim is None:
            return None
        ident = uuid4().hex
        start = time.monotonic()
        outcome = "unavailable"
        try:
            result = self._execute(claim)
            outcome = result["status"]
            return result
        except LeaseLost:
            outcome = "lease_lost"
            raise
        except WorkerDenied:
            outcome = "worker_denied"
            raise
        finally:
            duration = (time.monotonic() - start) * 1000
            self.telemetry.observe("worker.execution", outcome, duration)
            for name, value in self.runner.last_timings.items():
                self.telemetry.observe(name, "observed", value)
            logging.getLogger("trueflag.security").info(
                "worker.completed",
                extra={
                    "correlation_id": ident,
                    "outcome": outcome,
                    "duration_ms": duration,
                },
            )

    def _execute(self, claim):
        try:
            result = self.runner.run(self.queue, self.token, claim)
            return self.queue.complete(self.token, claim, result)
        except (LeaseLost, WorkerDenied):
            # A stale/revoked worker has no authority to publish or mutate the job.
            raise
        except AssessmentNotFound:
            return self.queue.fail(self.token, claim, "authorization_changed", retryable=False)
        except AssessmentConflict:
            return self.queue.fail(self.token, claim, "stale_case", retryable=False)
        except ExecutionFailed as error:
            return self.queue.fail(
                self.token,
                claim,
                error.reason,
                retryable=error.reason not in {"authorization_changed", "stale_case"},
            )
        except JobUnavailable:
            return self.queue.fail(self.token, claim, "database_unavailable")
        except AssessmentError:
            return self.queue.fail(self.token, claim, "processing_unavailable")
        except Exception:
            return self.queue.fail(self.token, claim, "processing_unavailable")


def main():
    from pathlib import Path

    from app.core.database import make_engine
    from app.security.logging import configure_security_logging
    from app.services.monitoring import MetricFlusher

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--token-file", default="/run/secrets/assessment_worker_token")
    args = parser.parse_args()
    engine = None
    exporter = None
    configure_security_logging()
    stop = threading.Event()
    try:
        token = Path(args.token_file).read_text(encoding="ascii").strip()
        engine = make_engine(os.environ["DATABASE_URL"])
        worker = AssessmentWorker(AssessmentJobService(engine), token, stop)
        exporter = MetricFlusher(engine, worker.telemetry).start()
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stop.set())
        while not stop.is_set():
            try:
                result = worker.run_once()
                print(
                    json.dumps(
                        {
                            "event": "assessment.worker",
                            "correlation_id": uuid4().hex,
                            "status": result["status"] if result else "idle",
                        }
                    ),
                    flush=True,
                )
            except (WorkerDenied, LeaseLost):
                return 1
            except JobError:
                if args.once:
                    return 1
                stop.wait(5)
            if args.once:
                return 0
            stop.wait(2)
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "event": "assessment.worker",
                    "correlation_id": uuid4().hex,
                    "status": "unavailable",
                }
            ),
            flush=True,
        )
        return 1
    finally:
        if exporter is not None:
            exporter.close()
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
