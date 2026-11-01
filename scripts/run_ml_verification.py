"""Local read-only Linux acceptance runtime; no service deployment or credential mounts."""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "trueflag-ml-verify:phase2-4"
CHECKS = {
    "tests": ["-m", "unittest", "discover", "-s", "backend/ml_tests", "-q"],
    "shap": ["scripts/verify_shap_explanations.py", "--progress"],
    "scoring": ["scripts/verify_rf_scoring.py"],
    "policy": ["scripts/verify_risk_policy.py"],
    "loader": ["scripts/verify_model_loader.py"],
    "dependencies": ["-m", "pip", "--no-cache-dir", "check"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", choices=CHECKS, default="tests")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        built = subprocess.run(
            ["docker", "build", "-f", "backend/Dockerfile.ml-verify", "-t", IMAGE, "backend"],
            cwd=ROOT,
        )
        if built.returncode:
            return built.returncode
    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
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
        "/tmp:rw,nosuid,nodev,size=256m",
    ]
    for name in ["OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"]:
        command.extend(["-e", name + "=1"])
    for relative in [
        "backend",
        "scripts",
        "assets/local/baseline",
        "assets/local/explanation_reference",
    ]:
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT) or not path.is_dir():
            print(json.dumps({"status": "FAIL", "reason": "verification_mount_missing_or_invalid"}))
            return 1
        command.extend(["-v", f"{path.as_posix()}:/workspace/{relative}:ro"])
    command.extend([IMAGE, "python", "-B", *CHECKS[args.check]])
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
