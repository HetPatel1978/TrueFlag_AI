"""Select five labeled demo rows using the verified RF; read approved synthetic CSV on stdin.

Run only in the pinned ML runtime. The output is an importable CSV; the source target
is used solely for demonstration selection and is never passed into the model.
"""

import csv
import sys

from app.schemas.alerts import FEATURE_CONTRACT_VERSION, AlertFeatures
from app.schemas.csv_uploads import COLUMNS
from app.services.csv_validation import numeric_cell
from trueflag_ml.policy import RiskPolicyEngine
from trueflag_ml.scoring import RFScoringService, ScoringRecord


def main():
    features = []
    labels = []
    reader = csv.DictReader(sys.stdin)
    for index, row in enumerate(reader):
        if index >= 1000:
            break
        if row.get("SAR") not in {"0", "1"}:
            raise ValueError("synthetic_target_invalid")
        values = {
            name: row[name]
            if name == "state"
            else None
            if name == "income" and row[name] == ""
            else numeric_cell(row[name])
            for name in AlertFeatures.model_fields
        }
        features.append(AlertFeatures.model_validate(values).model_dump())
        labels.append(int(row["SAR"]))
    results = RFScoringService().score_batch(
        [ScoringRecord(f"candidate-{i}", item) for i, item in enumerate(features)]
    )
    policies = RiskPolicyEngine()
    if not policies.ready or any(result.processing_status != "processed" for result in results):
        raise ValueError("verified_scoring_unavailable")
    upper = policies.settings.thresholds["Efficiency"]
    lower = policies.settings.thresholds["Balanced"]
    positives = [i for i, result in enumerate(results) if labels[i] == 1 and result.score >= upper]
    negatives = [i for i, result in enumerate(results) if labels[i] == 0 and result.score < lower]
    if len(positives) < 3 or len(negatives) < 2:
        raise ValueError("insufficient_labeled_candidates")
    chosen = sorted(positives, key=lambda i: results[i].score, reverse=True)[:3]
    chosen += sorted(negatives, key=lambda i: results[i].score)[:2]
    writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    for number, index in enumerate(chosen, start=1):
        writer.writerow(
            {
                "source_id": f"synthetic-scored-demo-{number}",
                "data_classification": "synthetic",
                "feature_contract_version": FEATURE_CONTRACT_VERSION,
                **features[index],
            }
        )
        print(
            f"row {number}: synthetic target={labels[index]}, RF score={results[index].score:.6f}",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
