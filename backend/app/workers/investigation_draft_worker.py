"""Explicit bounded draft worker; candidate egress requires separate operator authorization."""

import argparse
import json
import secrets
import sys
from pathlib import Path

from app.core.config import Settings
from app.core.database import make_engine
from app.core.release import require_compatible, worker_identity
from app.core.release_metadata import ReleaseCompatibilityError
from app.services.investigation_drafts import InvestigationDraftService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-file", default="/run/secrets/investigation_worker_token")
    parser.add_argument("--max-jobs", type=int, default=1)
    args = parser.parse_args()
    engine = None
    mode = "unselected"
    try:
        if sys.platform not in {"linux", "win32"} or not 1 <= args.max_jobs <= 10:
            raise ValueError("bounded_linux_required")
        settings = Settings(jwt_secret=secrets.token_urlsafe(48))
        mode = "provider_candidate" if settings.investigation_external_enabled else "simulation"
        engine = make_engine(settings.database_url)
        require_compatible(engine)
        release = worker_identity()
        service = InvestigationDraftService(engine, settings)
        service._enabled()
        token = Path(args.token_file).read_text(encoding="utf-8").strip()
        for _ in range(args.max_jobs):
            service.coordinator.run_once(token)
            result = service.run_once(token)
            print(
                json.dumps(
                    dict(
                        event="investigation.draft.worker",
                        release=release,
                        status=result["status"] if result else "idle",
                        mode=mode,
                        human_review_required=True,
                    )
                ),
                flush=True,
            )
        return 0
    except ReleaseCompatibilityError as error:
        print(
            json.dumps(
                {
                    "event": "investigation.draft.unavailable",
                    "code": error.code,
                    "mode": mode,
                    "human_review_required": True,
                }
            ),
            flush=True,
        )
        return 1
    except Exception:
        print(
            json.dumps(
                dict(
                    event="investigation.draft.unavailable",
                    mode=mode,
                    human_review_required=True,
                )
            ),
            flush=True,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
