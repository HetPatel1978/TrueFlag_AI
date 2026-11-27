"""Read value-free attempt/receipt facts from the isolated Claude probe ledger."""

import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]


def inside():
    import rehearse_database_recovery as recovery
    from app.core.database import make_engine
    from app.models.investigation_drafts import DraftAttempt, DraftJob, DraftReceipt, DraftRun
    from app.services.provider_finance import reservation_totals
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    marker = json.loads(Path("/demo/claude_probe_attempt.json").read_text())
    schema = marker["schema"]
    if not re.fullmatch(r"tf_claude_demo_[a-f0-9]{32}", schema):
        raise ValueError("invalid_isolated_schema")
    state, base_url, control = recovery.inside_connection()
    control.dispose()
    url = base_url.set(database=state["database"]).update_query_dict(
        {"options": "-csearch_path=" + schema}
    )
    engine = make_engine(url.render_as_string(hide_password=False))
    with Session(engine) as session:
        attempts, reserved = reservation_totals(session, provider="anthropic")
        receipts = list(session.scalars(select(DraftReceipt)))
        jobs = list(session.scalars(select(DraftJob)))
        provider_runs = session.scalar(
            select(func.count())
            .select_from(DraftRun)
            .where(DraftRun.configuration["provider"].as_string() == "anthropic")
        )
        actual_attempts = session.scalar(select(func.count()).select_from(DraftAttempt))
        known_cost = sum(
            (
                Decimal(receipt.usage["cost_usd"])
                for receipt in receipts
                if receipt.usage
                and receipt.usage.get("basis")
                == "provider_reported_tokens_configured_rate_estimate"
            ),
            Decimal(0),
        )
        print(
            json.dumps(
                {
                    "provider_runs": provider_runs,
                    "attempts": attempts,
                    "all_attempts": actual_attempts,
                    "reserved_usd": str(reserved),
                    "receipt_count": len(receipts),
                    "receipt_statuses": [r.status for r in receipts],
                    "provider_usage_available": [r.usage is not None for r in receipts],
                    "known_estimated_usage_usd": str(known_cost),
                    "elapsed_ms": [r.elapsed_ms for r in receipts],
                    "job_statuses": [j.status for j in jobs],
                }
            )
        )
    engine.dispose()


def main():
    import rehearse_database_recovery as recovery

    state = recovery.load(ROOT / "runtime/g0-3/current.json")
    directory = (ROOT / state["directory"]).resolve(strict=True)
    demo = (ROOT / "runtime/claude-demo-20261120").resolve(strict=True)
    if not directory.is_relative_to((ROOT / "runtime/g0-3").resolve()):
        raise ValueError("invalid_isolated_directory")
    command = recovery.linux_args(state, directory)[:-4]
    image_index = command.index("trueflag-assessment-verify:phase2-5")
    command[image_index:image_index] = ["-v", f"{demo.as_posix()}:/demo:ro"]
    command += ["python", "-B", "/workspace/scripts/inspect_claude_probe.py", "--inside"]
    result = subprocess.run(command, input="", text=True, capture_output=True, timeout=60)
    for line in result.stdout.splitlines():
        if line.startswith('{"provider_runs"'):
            print(line)
    if result.returncode:
        print("Isolated probe ledger unavailable; details withheld.")
    return result.returncode


if __name__ == "__main__":
    try:
        if "--inside" in sys.argv:
            inside()
        else:
            raise SystemExit(main())
    except Exception:
        print("Isolated probe ledger unavailable; details withheld.")
        raise SystemExit(1) from None
