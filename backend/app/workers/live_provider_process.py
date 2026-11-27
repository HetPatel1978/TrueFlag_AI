"""Fixed candidate endpoint only; no DB credentials, .env loading or arbitrary code/tools."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from pydantic import SecretStr

from app.schemas.investigation_drafts import ProviderInput
from app.schemas.provider_live import ClaudeProviderConfig, LiveProviderConfig, configuration
from app.schemas.regulatory_investigation import GroundedProviderInput
from app.schemas.research_demo import ResearchClaudeConfig, ResearchProviderInput
from app.services.claude_provider import ClaudeProvider
from app.services.investigation_provider import strict_json
from app.services.luminal_provider import LuminalProvider, ProviderRateLimited, ProviderRejected


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
    data = strict_json(sys.stdin.buffer.read(196609).decode(), 196608)
    auth = data["authorization"]
    claude = data["config"].get("provider") == "anthropic"
    key = "anthropic_api_key" if claude else "investigation_provider_api_key"
    auth[key] = SecretStr(auth[key])
    try:
        provider = ClaudeProvider if claude else LuminalProvider
        config = configuration(data["config"])
        if not isinstance(config, ClaudeProviderConfig if claude else LiveProviderConfig):
            raise ProviderRejected("provider_activation_unavailable")
        extra = {}
        if (
            claude
            and isinstance(config, ResearchClaudeConfig)
            and data.get("research_response_file")
        ):
            path = Path(data["research_response_file"]).resolve()
            if (
                path.name != "http-response.json"
                or not any(
                    p.name == "windows-native" and p.parent.name == "runtime" for p in path.parents
                )
                or not path.parent.is_dir()
            ):
                raise ProviderRejected("research_capture_path_invalid")

            def record_response(status, raw):
                clean = raw.decode("utf-8", errors="replace").replace(
                    auth[key].get_secret_value(), "[credential redacted]"
                )
                with path.open("x", encoding="utf-8") as stream:
                    json.dump({"http_status": status, "sanitized_body": clean}, stream)

            extra["response_recorder"] = record_response
        reply = provider(SimpleNamespace(**auth), **extra).propose(
            (
                ResearchProviderInput
                if claude and data["packet"].get("regulatory_context") == "research_unapproved"
                else GroundedProviderInput
                if claude
                and data["packet"].get("regulatory_context")
                == "approved_context_human_review_required"
                else ProviderInput
            ).model_validate(data["packet"]),
            config,
        )
        sys.stdout.write(reply.model_dump_json(warnings="error"))
    except ProviderRateLimited as error:
        sys.stdout.write(json.dumps({"error": "rate_limited", "retry_after": error.retry_after}))
    except ProviderRejected as error:
        if claude:
            sys.stdout.write(
                json.dumps(
                    {
                        "error": "provider_rejected",
                        "http_status": error.http_status,
                        "diagnostics": error.diagnostics,
                    }
                )
            )
        else:
            sys.stdout.write('{"error":"provider_unavailable"}')
    except Exception:
        sys.stdout.write('{"error":"provider_unavailable"}')


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit(1) from None
