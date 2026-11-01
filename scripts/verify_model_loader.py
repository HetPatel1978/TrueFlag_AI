"""Read-only Phase 2.1 acceptance: approved model load and synthetic preprocessing; no scoring."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trueflag_ml.loader import ModelLoadError, load_approved_pipeline  # noqa: E402


def main():
    try:
        loaded = load_approved_pipeline()
    except ModelLoadError as error:
        print(json.dumps({"status": "FAIL", "reason": error.code}))
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "model_version": loaded.model_version,
                "predictors": len(loaded.fields),
                "encoded_features": loaded.pipeline.named_steps["estimator"].n_features_in_,
                "trees": len(loaded.pipeline.named_steps["estimator"].estimators_),
                "fits": 0,
                "predictions": 0,
                "private_rows_read": 0,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
