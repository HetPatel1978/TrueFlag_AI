"""Host-side e2e harness helpers: fixture lifetime, per-spec runs, health check, summary."""

import http.server
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import run_investigation_e2e as harness  # noqa: E402


def test_fixture_lifetime_defaults_to_600_and_is_bounded():
    assert harness.fixture_lifetime({}) == 600
    assert harness.fixture_lifetime({harness.LIFETIME_ENV: " 1200 "}) == 1200
    for bad in ["59", "3601", "abc", "-5", "600.5"]:
        with pytest.raises(ValueError):
            harness.fixture_lifetime({harness.LIFETIME_ENV: bad})


def test_all_suite_runs_every_spec_file_separately():
    specs = harness.spec_files("all")
    assert len(specs) >= 9 and specs == sorted(specs)
    assert all(s.endswith(".spec.ts") for s in specs)
    assert harness.spec_files("batch") == ["batch.spec.ts"]
    assert harness.spec_files("provider") == ["drafts.spec.ts"]


def test_summary_counts_playwright_totals():
    output = "Running 6 tests\n  x 1 e2e\\a.spec.ts\n\n  2 failed\n  3 passed (1.2m)\n  1 skipped\n"
    assert harness.summarize(output) == {"failed": 2, "passed": 3, "skipped": 1}
    assert harness.summarize("no summary here") == {}


def test_health_check_fails_fast_when_fixture_is_down():
    # Nothing listens on this port: the check returns False instead of hanging.
    assert not harness.fixture_healthy(attempts=2, delay=0, url="http://127.0.0.1:9/health")


def test_health_check_requires_ok_status():
    class Handler(http.server.BaseHTTPRequestHandler):
        body = {"status": "ok"}

        def do_GET(self):
            payload = json.dumps(self.body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/health"
    try:
        assert harness.fixture_healthy(attempts=1, delay=0, url=url)
        Handler.body = {"status": "starting"}
        assert not harness.fixture_healthy(attempts=1, delay=0, url=url)
    finally:
        server.shutdown()


def test_stream_stops_a_spec_that_outlives_the_fixture():
    lines = []
    code, output = harness.stream(
        [sys.executable, "-c", "import time; print('secret-pw', flush=True); time.sleep(30)"],
        cwd=Path(__file__).parent,
        env=None,
        timeout=3,
        redact="secret-pw",
        sink=lines.append,
    )
    assert code == 124
    assert "secret-pw" not in output and "[redacted fixture credential]" in output
    assert harness.LIFETIME_ENV in output
