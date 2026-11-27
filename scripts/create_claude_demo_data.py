"""Create a small fictional CSV and matching scenario descriptions; no database writes."""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.alerts import FEATURE_CONTRACT_VERSION  # noqa: E402
from app.schemas.csv_uploads import COLUMNS  # noqa: E402
from app.services.connected_scenarios import expected_activity, scenario_bundle  # noqa: E402
from app.services.ingestion import digest  # noqa: E402
from app.services.synthetic_evidence import bundle_manifest  # noqa: E402

SCENARIOS = ("ordinary", "velocity", "concentration", "flow_change", "incomplete_history")


def demo_rows():
    rows, manifest = [], []
    for key in SCENARIOS:
        bundle = scenario_bundle(key)
        source_id = "claude-demo-" + bundle.scenario_id.hex
        rows.append(
            {
                "source_id": source_id,
                "data_classification": "synthetic",
                "feature_contract_version": FEATURE_CONTRACT_VERSION,
                **bundle.declarations,
            }
        )
        manifest.append(
            {
                "source_id": source_id,
                "scenario": key,
                "scenario_id": str(bundle.scenario_id),
                "source_revision": bundle.source_revision,
                "bundle_sha256": digest(bundle_manifest(bundle)),
                "expected_activity_usd": expected_activity(bundle),
            }
        )
    return rows, manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New, empty directory for synthetic files")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    rows, manifest = demo_rows()
    with (args.output / "alerts.csv").open("x", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "scenario_manifest.json").open("x", encoding="utf-8") as target:
        json.dump(
            {
                "classification": "synthetic",
                "evidence_linked_to_imported_cases": False,
                "note": "Scenario patterns are not SAR labels; input features are declarations.",
                "scenarios": manifest,
            },
            target,
            indent=2,
        )
        target.write("\n")


if __name__ == "__main__":
    main()
