"""Owner approval gate for the one-command academic research workflow (pure, offline)."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "academic_research_run_windows.py"
spec = importlib.util.spec_from_file_location("academic_research_run_windows", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)

PACKAGE = {"approval_id": "academic-claude-research-review-2026-11-23-v10",
           "request_sha256": "a" * 64, "expires_second": 10_000}


def gate(**overrides):
    values = dict(approved_sha256="a" * 64, approval_id=PACKAGE["approval_id"],
                  now_second=10_000 - 900, latest_id=PACKAGE["approval_id"], job=("pending", 0))
    values.update(overrides)
    return workflow.decide(PACKAGE, **values)


def test_current_exact_request_executes():
    assert gate() == "execute"


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"approved_sha256": "b" * 64}, "hash_mismatch"),  # a refreshed hash needs new approval
        ({"latest_id": "academic-claude-research-review-2026-11-23-v11"}, "superseded"),
        ({"approval_id": "academic-claude-research-review-2026-11-23-v9"}, "superseded"),
        ({"job": ("failed", 1)}, "not_pending"),  # one request; never re-sent
        ({"job": ("pending", 1)}, "not_pending"),
        ({"now_second": 10_000 - 180}, "expired"),  # inside the worker's 150 s floor + margin
        ({"now_second": 10_000}, "expired"),
    ],
)
def test_stale_or_mismatched_approval_never_executes(overrides, reason):
    assert gate(**overrides) == reason


def test_window_boundary_matches_worker_floor_plus_margin():
    floor = workflow.DISPATCH_FLOOR_SECONDS + workflow.SUBMIT_MARGIN_SECONDS
    assert workflow.DISPATCH_FLOOR_SECONDS == 150
    assert gate(now_second=10_000 - floor) == "expired"
    assert gate(now_second=10_000 - floor - 1) == "execute"


@pytest.mark.parametrize(
    "answer, approved",
    [
        ("a" * 64, True),
        ("  " + "A" * 64 + "\n", True),  # surrounding whitespace / case from copy-paste
        ("a" * 63, False),  # a prefix is not the exact request
        ("b" * 64, False),  # another request's hash
        ("yes", False),
        ("", False),
        ("show", False),
    ],
)
def test_only_the_complete_displayed_hash_approves(answer, approved):
    assert workflow.owner_confirms(answer, "a" * 64) is approved


def test_review_refuses_non_interactive_input_before_any_snapshot(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("no snapshot, request or approval without an owner terminal")

    monkeypatch.setattr(workflow, "prepare", forbidden)
    monkeypatch.setattr(workflow, "execute", forbidden)
    monkeypatch.setattr(workflow.sys.stdin, "isatty", lambda: False, raising=False)
    with pytest.raises(SystemExit, match="interactive_owner_terminal_required"):
        workflow.review(None, None)


def test_next_version_and_latest_package(tmp_path):
    for n in (8, 10, 9):
        folder = tmp_path / f"academic-claude-research-review-2026-11-23-v{n}"
        folder.mkdir()
        (folder / "approval-package.json").write_text(f'{{"approval_id": "{folder.name}"}}')
    (tmp_path / "academic-claude-research-review-2026-11-23-v11").mkdir()  # no package file
    assert workflow.latest_package(tmp_path)["approval_id"].endswith("-v10")
    assert workflow.next_approval_id(tmp_path).endswith("-v12")
