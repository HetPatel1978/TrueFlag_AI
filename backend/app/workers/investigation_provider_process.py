"""Secret-free, fixed simulation entrypoint; never accepts tools or imports from input."""

import sys

from app.schemas.investigation_drafts import ProviderConfig, ProviderInput
from app.schemas.provider_live import configuration
from app.schemas.regulatory_investigation import GroundedProviderInput
from app.services.investigation_provider import DeterministicFakeProvider, strict_json


def main():
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (65536, 65536))
        resource.setrlimit(resource.RLIMIT_CPU, (12, 12))
        resource.setrlimit(resource.RLIMIT_AS, (384 * 1024 * 1024, 384 * 1024 * 1024))
    elif sys.platform == "win32":
        from app.workers.process_control import require_windows_child_limits

        require_windows_child_limits(384 * 1024 * 1024)
    else:
        raise RuntimeError("unsupported_provider_runtime")
    raw = sys.stdin.buffer.read(131073)
    value = strict_json(raw.decode(), 131072)
    grounded = (
        "regulatory_binding_sha256" in value["config"] or "regulatory_query" in value["config"]
    )
    config = configuration(value["config"])
    if not isinstance(config, ProviderConfig):
        return 1
    packet = (GroundedProviderInput if grounded else ProviderInput).model_validate(value["packet"])
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
