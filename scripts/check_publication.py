"""Check tracked and unignored source candidates; report paths, never credential values."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SUFFIXES = {
    ".csv",
    ".jsonl",
    ".joblib",
    ".pkl",
    ".pickle",
    ".zip",
    ".pem",
    ".key",
    ".db",
}
PATTERNS = [
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{24,})\b"),
    re.compile(r"(?m)^JWT_SECRET=\S+"),
    re.compile(r"(?m)^POSTGRES_PASSWORD=\S+"),
]


def main() -> None:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    candidates = sorted(set(p for p in result.stdout.decode().split("\0") if p))
    problems = []
    for name in candidates:
        path = ROOT / name
        if (
            (
                name.startswith(("assets/local/", ".venv/", ".venv-ml/", "runtime/"))
                and name != "assets/local/.gitkeep"
            )
            or (path.name.startswith(".env") and path.name != ".env.example")
            or path.suffix in PRIVATE_SUFFIXES
            or ".sqlite" in path.name
        ):
            problems.append("Private path: " + name)
            continue
        if path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                problems.append("Unexpected binary: " + name)
                continue
            if any(pattern.search(content) for pattern in PATTERNS):
                problems.append("Credential-shaped content: " + name)
    for local in [
        ".env",
        "assets/local/baseline/model/selected_pipeline.joblib",
        ".venv/pyvenv.cfg",
    ]:
        if subprocess.run(["git", "check-ignore", "--quiet", local], cwd=ROOT).returncode:
            problems.append("Missing ignore boundary: " + local)
    if problems:
        raise SystemExit("\n".join(problems))
    print(f"PASS: {len(candidates)} source candidates; private/secret ignore boundaries verified")


if __name__ == "__main__":
    main()
