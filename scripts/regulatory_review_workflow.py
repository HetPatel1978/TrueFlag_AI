"""Offline, owner-operated regulatory review intake; no source publication or DB access."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.harness import write_once  # noqa: E402
from app.evaluation.regulatory_review import (  # noqa: E402
    append_event,
    blank_packet,
    expert_metrics,
    replay,
)
from app.services.investigation_provider import strict_json  # noqa: E402


def read(path, limit=4194304):
    with path.open("rb") as stream:
        return strict_json(stream.read(limit + 1).decode("utf-8"), limit)


def history(directory):
    paths = sorted(directory.glob("*.json")) if directory.exists() else []
    if len(paths) > 500 or [p.name for p in paths] != [
        f"{i:06d}.json" for i in range(1, len(paths) + 1)
    ]:
        raise ValueError("regulatory_history_sequence_invalid")
    if sum(p.stat().st_size for p in paths) > 16777216:
        raise ValueError("regulatory_history_size_limit")
    return [read(p, 65536) for p in paths]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "record", "status", "evaluate"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--journal", type=Path)
    parser.add_argument("--submission", type=Path)
    parser.add_argument("--observations", type=Path)
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to((ROOT / "runtime").resolve()):
        raise ValueError("regulatory_review_private_runtime_required")
    if args.action == "prepare":
        result = blank_packet()
    else:
        if not args.registry or not args.journal:
            raise ValueError("regulatory_review_registry_and_journal_required")
        registry, events = read(args.registry), history(args.journal)
        if args.action == "record":
            if not args.submission or not args.journal.resolve().is_relative_to(
                (ROOT / "runtime").resolve()
            ):
                raise ValueError("regulatory_review_submission_required")
            event = append_event(events, read(args.submission), registry)
            # Shared next sequence name + exclusive create prevents concurrent history forks.
            write_once(args.journal / f"{len(events) + 1:06d}.json", event)
            events.append(event)
            result = replay(events, registry)
        elif args.action == "evaluate":
            result = expert_metrics(
                events, registry, read(args.observations) if args.observations else []
            )
        else:
            result = replay(events, registry)
    write_once(args.output, result)
    print(
        json.dumps(
            dict(
                status=result.get("status", "offline_review_artifact_written"),
                source_publication_authorized=False,
            )
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print(
            json.dumps(
                dict(
                    status="regulatory_review_not_accepted",
                    reason="Review identity, binding, transition, bounds or output invalid.",
                )
            )
        )
        raise SystemExit(1) from None
