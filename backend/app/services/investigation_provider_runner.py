"""Linux bounded subprocess for the registered simulation, without DB/provider credentials."""

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from app.schemas.investigation_drafts import ProviderReply
from app.services.investigation_provider import (
    ProviderFailure,
    ProviderLimit,
    ProviderTimeout,
    strict_json,
)


class IsolatedSimulationRunner:
    def invoke(self, packet, config):
        if sys.platform not in {"linux", "win32"} or config.provider != "deterministic_fake":
            raise ProviderFailure("simulation_runtime_unavailable")
        payload = json.dumps(
            dict(packet=packet.model_dump(mode="json"), config=config.model_dump(mode="json"))
        )
        environment = {
            "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        }
        if sys.platform == "win32":
            from app.workers.process_control import ProcessOutputLimit, ProcessTimeout, run_windows

            try:
                code, raw = run_windows(
                    [sys.executable, "-B", "-m", "app.workers.investigation_provider_process"],
                    payload.encode(),
                    environment=environment,
                    timeout=config.request_deadline_seconds,
                    max_output=65536,
                    memory_bytes=384 * 1024 * 1024,
                    cpu_seconds=12,
                )
            except ProcessTimeout:
                raise ProviderTimeout("provider_timeout") from None
            except ProcessOutputLimit:
                raise ProviderLimit("provider_response_limit") from None
            except OSError:
                raise ProviderFailure("provider_unavailable") from None
            if code:
                raise ProviderFailure("provider_unavailable")
        else:
            with tempfile.TemporaryFile() as output:
                process = subprocess.Popen(
                    [sys.executable, "-B", "-m", "app.workers.investigation_provider_process"],
                    stdin=subprocess.PIPE,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    env=environment,
                    start_new_session=True,
                )
                try:
                    process.communicate(payload.encode(), timeout=config.request_deadline_seconds)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
                    raise ProviderTimeout("provider_timeout") from None
                except Exception:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=5)
                    raise ProviderFailure("provider_unavailable") from None
                output.seek(0)
                raw = output.read(65537)
                if len(raw) > 65536:
                    raise ProviderLimit("provider_response_limit")
                if process.returncode:
                    raise ProviderFailure("provider_unavailable")
        try:
            return ProviderReply.model_validate(strict_json(raw.decode(), 65536))
        except Exception:
            raise ProviderFailure("provider_invalid_envelope") from None
