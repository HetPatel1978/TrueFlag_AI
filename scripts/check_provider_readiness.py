"""Local, read-only provider configuration preflight. Never authenticates to Luminal."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.config import Settings  # noqa: E402
from app.services.provider_readiness import provider_configuration_report  # noqa: E402


def main():
    try:
        result = provider_configuration_report(Settings())
    except Exception:
        # Pydantic error strings may contain inputs: never print the exception or traceback.
        print(json.dumps({"status": "configuration_unavailable", "live_requests_executed": 0}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
