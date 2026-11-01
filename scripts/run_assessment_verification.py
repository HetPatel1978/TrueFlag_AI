"""Local Linux/PG acceptance. Pass credentials over stdin, never Docker argv or mounted .env."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

IMAGE = "trueflag-assessment-verify:phase2-5"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--full-backend", action="store_true")
    parser.add_argument("--jobs-only", action="store_true")
    args = parser.parse_args()
    if args.build:
        result = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                "backend/Dockerfile.assessment-verify",
                "-t",
                IMAGE,
                "backend",
            ],
            cwd=ROOT,
        )
        if result.returncode:
            return result.returncode
    url = make_url(Settings().database_url)
    if url.get_backend_name() != "postgresql" or url.host not in {"127.0.0.1", "localhost"}:
        print(json.dumps({"status": "FAIL", "reason": "local_postgres_required"}))
        return 1
    database_url = url.set(host="db", port=5432).render_as_string(hide_password=False)
    command = [
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "trueflag-ai_default",
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
    ]
    for name in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]:
        command.extend(["-e", name + "=1"])
    for relative in [
        "backend",
        "scripts",
        "assets/local/baseline",
        "assets/local/explanation_reference",
    ]:
        path = (ROOT / relative).resolve(strict=True)
        if not path.is_relative_to(ROOT) or not path.is_dir():
            raise RuntimeError("invalid_verification_mount")
        command.extend(["-v", f"{path.as_posix()}:/workspace/{relative}:ro"])
    command.extend([IMAGE, "python", "-B", "scripts/verify_assessment_persistence.py"])
    # No environment/command-line persistence of DB credentials in Docker inspect.
    return subprocess.run(
        command,
        input=json.dumps(
            {
                "database_url": database_url,
                "full_backend": args.full_backend,
                "jobs_only": args.jobs_only,
            }
        ),
        text=True,
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
