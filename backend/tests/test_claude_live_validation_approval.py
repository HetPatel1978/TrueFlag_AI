"""Exact paid-payload admission, without credentials, database or external requests."""

import json
import runpy
from pathlib import Path

import pytest

CHECK = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "scripts/validate_claude_live.py")
)["approved_request"]


@pytest.mark.parametrize(
    "change",
    [
        {"decision": "pending"},
        {"provider": "luminal"},
        {"model": "another-model"},
        {"endpoint": "https://untrusted.example/messages"},
        {"request_limit": True},
        {"request_limit": 2},
        {"reservation_usd": "2.16"},
        {"request_sha256": "c" * 64},
        {"wire_schema_sha256": "d" * 64},
    ],
)
def test_changed_scope_is_not_owner_approval(tmp_path, change):
    record = dict(
        decision="approved",
        provider="anthropic",
        model="claude-sonnet-5-5",
        endpoint="https://api.anthropic.com/v1/messages",
        request_limit=1,
        reservation_usd="2.15",
        request_sha256="a" * 64,
        wire_schema_sha256="b" * 64,
    )
    (tmp_path / "live_validation_preflight.json").write_text(
        json.dumps({"request_sha256": "a" * 64})
    )
    path = tmp_path / "live_validation_owner_approval.json"
    path.write_text(json.dumps(record))
    assert CHECK(tmp_path, "b" * 64) == "a" * 64
    path.write_text(json.dumps({**record, **change}))
    with pytest.raises(RuntimeError, match="exact_owner_approval_required"):
        CHECK(tmp_path, "b" * 64)


def test_missing_record_is_not_approval(tmp_path):
    with pytest.raises(FileNotFoundError):
        CHECK(tmp_path, "b" * 64)
