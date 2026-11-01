"""Explicitly stage only the three approved explanation references into ignored local storage."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from trueflag_ml.explanation_contract import ExplanationVerificationError  # noqa: E402
from trueflag_ml.explanation_reference import REFERENCE_ROOT, reference_snapshots  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private", type=Path, default=ROOT.parent / "private_handoff")
    args = parser.parse_args()
    try:
        if REFERENCE_ROOT.exists():
            reference_snapshots()
            print(
                json.dumps({"status": "PASS", "approved_references": 3, "existing_unchanged": True})
            )
            return 0
        snapshots = reference_snapshots(args.private, handoff=True)
        REFERENCE_ROOT.mkdir(parents=True)
        for name, content in snapshots.items():
            with (REFERENCE_ROOT / name).open("xb") as stream:
                stream.write(content)
        print(
            json.dumps({"status": "PASS", "approved_references": 3, "private_assets_ignored": True})
        )
        return 0
    except (ExplanationVerificationError, OSError):
        print(json.dumps({"status": "FAIL", "reason": "explanation_reference_staging_failed"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
