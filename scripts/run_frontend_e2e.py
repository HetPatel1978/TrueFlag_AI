"""Launch bounded real Linux/PG worker fixture and Chromium. No private artifacts in images/reports."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.core.config import Settings  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def main():
    url = make_url(Settings().database_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("Local PostgreSQL required")
    runtime = ROOT / "runtime" / ("frontend-e2e-" + uuid4().hex)
    runtime.mkdir(parents=True)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "trueflag-ai_default",
        "-p",
        "127.0.0.1:18010:8000",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--memory",
        "3g",
        "--cpus",
        "2",
        "--pids-limit",
        "128",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,size=512m",
        "-v",
        f"{runtime.as_posix()}:/test-control:rw",
    ]
    for relative in [
        "backend",
        "scripts",
        "assets/local/baseline",
        "assets/local/explanation_reference",
    ]:
        path = (ROOT / relative).resolve(strict=True)
        assert path.is_relative_to(ROOT)
        command += ["-v", f"{path.as_posix()}:/workspace/{relative}:ro"]
    for name in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]:
        command += ["-e", name + "=1"]
    command += [
        "trueflag-assessment-verify:phase2-5",
        "python",
        "-B",
        "scripts/serve_frontend_acceptance.py",
    ]
    process = None
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=ROOT,
        )
        process.stdin.write(
            json.dumps(
                {
                    "database_url": url.set(host="db", port=5432).render_as_string(
                        hide_password=False
                    )
                }
            )
            + "\n"
        )
        process.stdin.flush()
        ready = json.loads(process.stdout.readline())
        if not ready.get("ready"):
            raise RuntimeError("fixture_unavailable")
        fixture = runtime / "fixture.json"
        fixture.write_text(json.dumps(ready), encoding="utf-8")
        env = {
            **os.environ,
            "TRUEFLAG_E2E_FIXTURE": str(fixture),
            "TRUEFLAG_API_PROXY": "http://127.0.0.1:18010",
        }
        npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
        return subprocess.run(
            [npm, "run", "test:e2e"], cwd=ROOT / "frontend", env=env, timeout=480
        ).returncode
    finally:
        if process:
            process.stdin.close()
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=10)
        # Only exact files created in this generated workspace directory; no recursive deletion.
        for path in runtime.iterdir():
            if path.name == "fixture.json" or re.fullmatch(
                r"(?:command|ack)\.\d+\.(?:json|tmp)", path.name
            ):
                path.unlink(missing_ok=True)
        runtime.rmdir()


if __name__ == "__main__":
    raise SystemExit(main())
