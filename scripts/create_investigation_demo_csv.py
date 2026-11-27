"""Create an importable three-case synthetic investigation demo, without database writes."""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.alerts import FEATURE_CONTRACT_VERSION  # noqa: E402
from app.schemas.csv_uploads import COLUMNS  # noqa: E402
from app.services.ingestion import digest  # noqa: E402
from app.services.synthetic_demo_cases import SPECS, demo_bundle, demo_source_id  # noqa: E402
from app.services.synthetic_evidence import bundle_manifest  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for the synthetic demo")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    manifest = []
    with (args.output / "investigation-demo.csv").open("x", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for key in SPECS:
            bundle = demo_bundle(key)
            source_id = demo_source_id(bundle)
            writer.writerow(
                {
                    "source_id": source_id,
                    "data_classification": "synthetic",
                    "feature_contract_version": FEATURE_CONTRACT_VERSION,
                    **bundle.declarations,
                }
            )
            manifest.append(
                {
                    "scenario": key,
                    "source_id": source_id,
                    "scenario_id": str(bundle.scenario_id),
                    "bundle_sha256": digest(bundle_manifest(bundle)),
                }
            )
    with (args.output / "manifest.json").open("x", encoding="utf-8") as target:
        json.dump(
            {
                "classification": "synthetic",
                "scenarios": manifest,
                "notice": "Transactions and alert inputs are separately generated synthetic declarations; input features are not derived from the transaction records.",
            },
            target,
            indent=2,
        )
        target.write("\n")


if __name__ == "__main__":
    main()
