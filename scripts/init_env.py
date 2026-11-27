"""Create local secrets without displaying them or overwriting existing configuration."""

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    destination = ROOT / ".env"
    database_password = secrets.token_urlsafe(32)
    content = (ROOT / ".env.example").read_text(encoding="utf-8")
    content = content.replace("JWT_SECRET=\n", f"JWT_SECRET={secrets.token_urlsafe(48)}\n")
    content = content.replace("POSTGRES_PASSWORD=\n", f"POSTGRES_PASSWORD={database_password}\n")
    content = content.replace("CHANGE_LOCALLY", database_password)
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)
    print("Created ignored .env with generated local secrets; no values displayed.")
