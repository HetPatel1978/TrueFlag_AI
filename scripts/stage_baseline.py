"""Verify both deliveries and stage a limited baseline under ignored local storage."""

import argparse
import csv
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELECTION = "research/Deliverables/TrueFlag_Model_Selection_20261018_183648/"
ASSETS = {
    SELECTION + "selected_pipeline.joblib": "model/selected_pipeline.joblib",
    SELECTION + "selected_policy_settings.json": "contracts/selected_policy_settings.json",
    SELECTION + "final_evaluation_predictions.csv": "validation/final_evaluation_predictions.csv",
    SELECTION + "decision_traces.csv": "validation/decision_traces.csv",
    "research/data/processed/datarobot_cleaned_v1.csv": "data/datarobot_cleaned_v1.csv",
    "research/data/data_dictionary.csv": "contracts/data_dictionary.csv",
    "research/data/splits/datarobot_provisional_v1/predictor_contract.json": "contracts/predictor_contract.json",
}


def sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def verify_package(root: Path) -> dict:
    manifest = json.loads((root / "DELIVERY_MANIFEST.json").read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        path = (root / entry["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Unsafe or missing delivery member")
        content = path.read_bytes()
        if len(content) != entry["bytes"] or sha(content) != entry["sha256"]:
            raise ValueError("Delivery integrity mismatch: " + entry["path"])
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT.parent / "github")
    parser.add_argument("--private", type=Path, default=ROOT.parent / "private_handoff")
    args = parser.parse_args()
    source, private = args.source.resolve(), args.private.resolve()
    a, b = verify_package(source), verify_package(private)
    if a["delivery_set_id"] != b["delivery_set_id"]:
        raise ValueError("Delivery sets differ")
    destination = ROOT / "assets/local/baseline"
    if destination.exists():
        raise FileExistsError("Baseline exists; refusing overwrite")
    with (source / "metadata/PRIVATE_ASSETS.csv").open(newline="", encoding="utf-8") as stream:
        inventory = list(csv.DictReader(stream))
    records = []
    with zipfile.ZipFile(private / "main/TRUEFLAG_PRIVATE_ASSETS.zip") as archive:
        if set(archive.namelist()) != {r["path"] for r in inventory}:
            raise ValueError("Private archive membership mismatch")
        # Complete verification before any staging writes. Do not load serialized models here.
        for row in inventory:
            data = archive.read(row["path"])
            if len(data) != int(row["bytes"]) or sha(data) != row["sha256"]:
                raise ValueError("Private asset identity mismatch: " + row["path"])
        destination.mkdir(parents=True)
        for original, target in ASSETS.items():
            data = archive.read(original)
            path = destination / target
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            records.append({"original": original, "local": target, "sha256": sha(data)})
    # No public license was supplied: keep teammate implementation references local and ignored.
    sources = list((source / "research/src/trueflag").glob("*.py"))
    sources += list((source / "extensions/src").glob("*.py"))
    sources += [
        source / "extensions/adapter/explanation_adapter.js",
        source / "extensions/requirements-explanations.txt",
    ]
    for original in sources:
        relative = original.relative_to(source)
        path = destination / "reference" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, path)
        records.append(
            {
                "original": relative.as_posix(),
                "local": path.relative_to(destination).as_posix(),
                "sha256": sha(path.read_bytes()),
            }
        )
    (destination / "baseline.manifest.json").write_text(
        json.dumps(
            {
                "delivery_set_id": a["delivery_set_id"],
                "private_assets_verified": len(inventory),
                "model_loaded": False,
                "rights_status": "No source license supplied; local reuse only",
                "records": records,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "STAGED_LOCAL_ONLY",
                "verified": len(inventory),
                "staged_files": len(records),
                "model_loaded": False,
            }
        )
    )


if __name__ == "__main__":
    main()
