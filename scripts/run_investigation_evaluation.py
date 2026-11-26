"""Offline synthetic fixture replay only. No credentials, providers, database or network calls."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.harness import run_offline, write_once  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "heldout"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Reports contain synthetic references; keep them in the existing ignored runtime tree.
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("evaluation_output_runtime_required")
    report, review = run_offline(args.fixtures.resolve(strict=True), split=args.split)
    write_once(output, report)
    write_once(output.with_suffix(".review.json"), review)
    print(
        json.dumps(
            dict(
                status=report["evaluation_status"],
                split=report["split"],
                planned_cases=report["planned_cases"],
                measured=report["metrics"],
                live_provider_requests=0,
            )
        )
    )
    return (
        0 if report["evaluation_status"] == "controlled_checks_passed_not_model_acceptance" else 1
    )


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(
            json.dumps(
                dict(
                    status="evaluation_unavailable",
                    detail="Invalid fixture, bounds or output; inspect trusted local artifacts.",
                )
            )
        )
        raise SystemExit(1) from None
