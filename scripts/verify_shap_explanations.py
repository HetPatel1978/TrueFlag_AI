"""Actual 4000-case explanation acceptance; aggregate output only, no raw values or payloads."""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trueflag_ml.explanation_contract import ExplanationLoadError, ExplanationVerificationError  # noqa: E402
from trueflag_ml.explanation_regression import run_explanation_regression  # noqa: E402
from trueflag_ml.loader import ModelLoadError  # noqa: E402
from trueflag_ml.regression import RegressionError  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    try:
        progress = (
            (lambda count: print(json.dumps({"attempted": count}), flush=True))
            if args.progress
            else None
        )
        report = run_explanation_regression(progress)
    except (
        ExplanationLoadError,
        ExplanationVerificationError,
        ModelLoadError,
        RegressionError,
    ) as error:
        print(json.dumps({"status": "FAIL", "reason": str(error)}))
        return 1
    except Exception:
        print(json.dumps({"status": "FAIL", "reason": "explanation_verification_failed"}))
        return 1
    print(json.dumps({"status": "PASS" if report.passed else "FAIL", **asdict(report)}))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
