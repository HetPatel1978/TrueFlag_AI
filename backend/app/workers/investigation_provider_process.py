"""Secret-free, fixed simulation entrypoint; never accepts tools or imports from input."""

import resource
import sys

from app.schemas.investigation_drafts import ProviderConfig, ProviderInput
from app.services.investigation_provider import DeterministicFakeProvider, strict_json


def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
    resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
    resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    raw = sys.stdin.buffer.read(131073)
    value = strict_json(raw.decode(), 131072)
    config = ProviderConfig.model_validate(value["config"])
    packet = ProviderInput.model_validate(value["packet"])
    if len(packet.model_dump_json().encode()) > config.max_input_tokens:
        return 1
    reply = DeterministicFakeProvider().propose(packet, config)
    sys.stdout.write(reply.model_dump_json(warnings="error"))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1) from None
