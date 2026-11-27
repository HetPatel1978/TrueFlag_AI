"""Read-only trusted RF replay; no training, threshold search or SHAP generation."""

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / "assets/local/baseline"


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def main():
    sys.path.insert(0, str(ROOT / "backend"))
    from trueflag_ml.loader import load_approved_pipeline

    approved = load_approved_pipeline(LOCAL)
    manifest = json.loads((LOCAL / "baseline.manifest.json").read_text())
    for record in manifest["records"]:
        path = (LOCAL / record["local"]).resolve()
        if (
            not path.is_relative_to(LOCAL)
            or hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]
        ):
            raise ValueError("Staged baseline identity mismatch")
    import numpy as np
    import pandas as pd
    from threadpoolctl import threadpool_limits

    fields = list(approved.fields)
    predictions = read_rows(LOCAL / "validation/final_evaluation_predictions.csv")
    ids = [row["technical_row_id"] for row in predictions]
    allowed = set(ids)
    raw = {
        row["technical_row_id"]: {k: row[k] for k in fields}
        for row in read_rows(LOCAL / "data/datarobot_cleaned_v1.csv")
        if row["technical_row_id"] in allowed
    }
    if len(allowed) != len(ids) or len(raw) != 4000:
        raise ValueError("Evaluation membership mismatch")
    frame = pd.DataFrame([raw[ident] for ident in ids], index=ids, columns=fields)
    for field in fields:
        if field != "state":
            frame[field] = pd.to_numeric(frame[field].replace("\\N", np.nan), errors="raise")
    pipeline = approved.pipeline
    with threadpool_limits(limits=1):
        scores = pipeline.predict_proba(frame)[:, list(pipeline.classes_).index(1)]
    saved = np.array([float(row["score"]) for row in predictions])
    delta = float(np.max(np.abs(scores - saved)))
    if not np.allclose(scores, saved, atol=1e-12, rtol=0):
        raise ValueError("Saved score mismatch")
    policies = json.loads((LOCAL / "contracts/selected_policy_settings.json").read_text())[
        "thresholds"
    ]
    scores_by_id = dict(zip(ids, scores))
    traces = read_rows(LOCAL / "validation/decision_traces.csv")
    for trace in traces:
        value = scores_by_id[trace["technical_row_id"]]
        retained = value >= policies[trace["mode"]] or (
            trace["mode"] == "Coverage" and int(trace["kycRiskScore"]) >= 3
        )
        if trace["final_route"] != ("Retain human review" if retained else "Dismiss"):
            raise ValueError("Saved route mismatch")
    if len(traces) != 12000:
        raise ValueError("Trace coverage mismatch")
    print(
        json.dumps(
            {
                "status": "PASS",
                "scores": len(scores),
                "maximum_difference": delta,
                "routes": len(traces),
                "fits": 0,
                "shap_generations": 0,
                "independent_evaluation": False,
            }
        )
    )


if __name__ == "__main__":
    main()
