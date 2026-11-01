"""Read-only Phase 2.2 acceptance on pinned evaluation files; print aggregate metrics only."""

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trueflag_ml.loader import ModelLoadError  # noqa: E402
from trueflag_ml.regression import RegressionError, run_regression  # noqa: E402
from trueflag_ml.scoring import ScoringInputError  # noqa: E402


def main():
    try:
        report = run_regression()
    except (ModelLoadError, RegressionError, ScoringInputError) as error:
        print(json.dumps({"status": "FAIL", "reason": str(error)}))
        return 1
    print(json.dumps({"status": "PASS" if report.passed else "FAIL", **asdict(report)}))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
