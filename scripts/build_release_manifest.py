"""Create matching deployment-owned identities from public source; no secret/config reads."""

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.release_metadata import identity_digest, unknown_identity, validate_identity  # noqa: E402


def write_metadata(path, data):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def build(root=ROOT):
    def git(*args):
        return (
            subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)
            .decode()
            .strip()
        )

    identity = unknown_identity()
    try:
        identity["git_commit"] = git("rev-parse", "HEAD")
        identity["source_state"] = "dirty" if git("status", "--porcelain") else "clean"
    except (OSError, subprocess.SubprocessError):
        pass
    paths = []
    for directory in ["backend/app", "backend/trueflag_ml", "frontend/src"]:
        paths.extend(
            p for p in (root / directory).rglob("*") if p.suffix in {".py", ".ts", ".tsx", ".css"}
        )
    for name in [
        "backend/pyproject.toml",
        "backend/requirements.lock",
        "backend/ml-requirements.txt",
        "backend/Dockerfile",
        "backend/Dockerfile.ml-worker",
        "frontend/Dockerfile",
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/vite.config.ts",
        "frontend/index.html",
        "scripts/build_release_manifest.py",
    ]:
        if (root / name).is_file():
            paths.append(root / name)
    digest = hashlib.sha256()
    for path in sorted(set(paths), key=lambda p: p.relative_to(root).as_posix()):
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("Invalid public source location")
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    identity["source_sha256"] = digest.hexdigest()
    identity["build_id"] = identity_digest(identity)
    validate_identity(identity)
    data = json.dumps(identity, indent=2) + "\n"
    write_metadata(root / "backend/app/_release.json", data)
    public = {k: identity[k] for k in ["build_id", "frontend_version", "source_state"]}
    write_metadata(root / "frontend/release-build.json", json.dumps(public, indent=2) + "\n")
    return identity


if __name__ == "__main__":
    print(json.dumps(build(), sort_keys=True))
