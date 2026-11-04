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
    parser.add_argument("--batch-only", action="store_true")
    parser.add_argument("--evidence-only", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument(
        "--phase3-report", action="store_true", help="Keep Phase 2 recovery evidence unchanged"
    )
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--batch-benchmark", action="store_true")
    parser.add_argument(
        "--batch-smoke",
        action="store_true",
        help="Eight real-model cases; no recorded load baseline",
    )
    args = parser.parse_args()
    if args.batch_smoke and not args.batch_benchmark:
        parser.error("--batch-smoke requires --batch-benchmark")
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
    command.extend(
        [
            IMAGE,
            "python",
            "-B",
            "scripts/benchmark_batch.py"
            if args.batch_benchmark
            else "scripts/benchmark_operations.py"
            if args.benchmark
            else "scripts/verify_assessment_persistence.py",
        ]
    )
    # No environment/command-line persistence of DB credentials in Docker inspect.
    if args.batch_benchmark:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=ROOT,
        )
        process.stdin.write(json.dumps({"database_url": database_url, "smoke": args.batch_smoke}))
        process.stdin.close()
        report = None
        for line in process.stdout:
            try:
                value = json.loads(line)
            except ValueError:
                continue  # Scientific libraries/driver diagnostics never reach public output.
            if value.get("event") == "report":
                report = value
            elif value.get("event") in {"progress", "workload_complete"}:
                print(json.dumps(value), flush=True)
        process.stdout.close()
        code = process.wait(timeout=60)
        if report is None:
            print(json.dumps({"status": "FAIL", "reason": "batch_benchmark_output_invalid"}))
            return 1
        if code == 0 and report.get("status") == "PASS":
            (
                ROOT
                / (
                    "runtime/phase2-10-6-smoke.json"
                    if args.batch_smoke
                    else "docs/PHASE2_10_6_BENCHMARK.json"
                )
            ).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        return code
    if args.benchmark:
        completed = subprocess.run(
            command,
            input=json.dumps({"database_url": database_url}),
            text=True,
            cwd=ROOT,
            capture_output=True,
        )
        try:
            report = json.loads(completed.stdout)
        except ValueError:
            print(json.dumps({"status": "FAIL", "reason": "benchmark_output_invalid"}))
            return 1
        if completed.returncode == 0 and report.get("status") == "PASS":
            (ROOT / "docs/PHASE2_8_BENCHMARK.json").write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
        text_report = dict(report)
        text_report.pop("monitoring", None)
        print(json.dumps(text_report, sort_keys=True))
        return completed.returncode
    if args.full_backend:
        process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT
        )
        process.stdin.write(json.dumps({"database_url": database_url, "full_backend": True}))
        process.stdin.close()
        evidence = None
        for line in process.stdout:
            if line.startswith("TRUEFLAG_BATCH_RECOVERY:"):
                evidence = json.loads(line.split(":", 1)[1])
            else:
                print(line, end="", flush=True)
        process.stdout.close()
        code = process.wait(timeout=60)
        if code == 0 and evidence and evidence["status"] == "PASS":
            (
                ROOT
                / (
                    "runtime/phase3-3-recovery.json"
                    if args.phase3_report
                    else "docs/PHASE2_10_6_RECOVERY.json"
                )
            ).write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps({"recovery_scenarios": len(evidence["scenarios"]), "status": "PASS"}))
        return code
    return subprocess.run(
        command,
        input=json.dumps(
            {
                "database_url": database_url,
                "full_backend": args.full_backend,
                "jobs_only": args.jobs_only,
                "batch_only": args.batch_only,
                "evidence_only": args.evidence_only,
                "retrieval_only": args.retrieval_only,
            }
        ),
        text=True,
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
