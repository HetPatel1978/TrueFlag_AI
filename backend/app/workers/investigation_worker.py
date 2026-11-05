"""Bounded evidence-only Linux worker CLI; separate secret, no provider/model configuration."""

import argparse
import json
import secrets
import sys
from pathlib import Path

from app.core.config import Settings
from app.core.database import make_engine
from app.services.investigation_coordinator import InvestigationCoordinator


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", default="/run/secrets/investigation_worker_token")
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args()
    if sys.platform != "linux" or not 1 <= args.max_jobs <= 20:
        raise SystemExit("Bounded Linux worker required")
    engine = None
    try:
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        # Snapshot signatures stay inside this execution; never require the API JWT key.
        settings = Settings(jwt_secret=secrets.token_urlsafe(48))
        engine = make_engine(settings.database_url)
        service = InvestigationCoordinator(engine, settings)
        processed = 0
        for _ in range(args.max_jobs):
            result = service.run_once(token)
            if result is None:
                break
            processed += 1
            print(
                json.dumps(
                    {
                        "event": "investigation.worker.outcome",
                        "status": result["status"],
                        "attempts": result["attempts"],
                        "human_review_required": True,
                    }
                ),
                flush=True,
            )
        return processed
    except Exception:
        print(
            json.dumps(
                {"event": "investigation.worker.unavailable", "human_review_required": True}
            ),
            flush=True,
        )
        raise SystemExit(1) from None
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    main()
