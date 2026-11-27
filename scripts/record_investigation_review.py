"""Record an independently submitted review artifact; never approves corpus or model quality."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.harness import write_once  # noqa: E402
from app.evaluation.review import review_event  # noqa: E402
from app.services.ingestion import digest  # noqa: E402
from app.services.investigation_provider import strict_json  # noqa: E402


def read(path):
    with path.open("rb") as stream:
        return strict_json(stream.read(1048577).decode("utf-8"), 1048576)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["report", "review", "registry", "dossier", "output"]:
        parser.add_argument("--" + key, type=Path, required=True)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("evaluation_review_runtime_required")
    previous = None
    if args.previous:
        event = read(args.previous)
        previous = event.pop("event_sha256")
        if digest(event) != previous:
            raise ValueError("review_history_integrity_failed")
    report = read(args.report)
    dossier = read(args.dossier)
    if digest(dossier.get("dossier", [])) != report["review_dossier_sha256"] or dossier.get(
        "report_sha256"
    ) != digest(report):
        raise ValueError("review_dossier_mismatch")
    result = review_event(read(args.review), report, read(args.registry), previous)
    write_once(args.output, result)
    print(json.dumps(dict(status=result["status"], semantic_quality_approved=False)))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(
            json.dumps(
                dict(
                    status="review_not_accepted",
                    reason="Binding, reviewer approval, schema or output failed.",
                )
            )
        )
        raise SystemExit(1) from None
