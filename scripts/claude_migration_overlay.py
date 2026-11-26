"""Build an isolated Alembic version directory for the unreleased Claude candidate."""

import shutil
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def create_overlay(*, regulatory=False, development=False, orchestration=False):
    runtime = (ROOT / "runtime").resolve(strict=True)
    output = runtime / ("claude-migration-overlay-" + uuid4().hex)
    output.mkdir(exist_ok=False)
    if not output.resolve(strict=True).is_relative_to(runtime):
        raise ValueError("invalid_overlay")
    for path in (ROOT / "backend/alembic/versions").glob("*.py"):
        shutil.copy2(path, output / path.name)
    candidate = ROOT / "backend/alembic/candidates/0020_claude_provider.py"
    shutil.copy2(candidate, output / candidate.name)
    if regulatory or development or orchestration:
        candidate = ROOT / "backend/alembic/candidates/0021_regulatory_draft_bindings.py"
        shutil.copy2(candidate, output / candidate.name)
    if development or orchestration:
        candidate = ROOT / "backend/alembic/candidates/0022_claude_development_scope.py"
        shutil.copy2(candidate, output / candidate.name)
    if orchestration:
        candidate = ROOT / "backend/alembic/candidates/0023_durable_regulatory_start.py"
        shutil.copy2(candidate, output / candidate.name)
    return output
