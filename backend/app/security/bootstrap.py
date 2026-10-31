"""Explicit local account creation; no default accounts or HTTP registration."""

import argparse
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import make_engine
from app.models import AuditEvent, User
from app.security.auth import password_hash


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--role", choices=["analyst", "admin"], default="analyst")
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not 3 <= len(username) <= 100 or not username.isascii() or not username.isalnum():
        parser.error("Use an ASCII alphanumeric username of 3-100 characters")
    password = getpass("New password (at least 12 characters): ")
    if len(password) < 12 or password != getpass("Confirm password: "):
        parser.error("Password must match and contain at least 12 characters")
    engine = make_engine(Settings().database_url)
    try:
        with Session(engine) as session, session.begin():
            if session.scalar(select(User).where(User.username == username)):
                parser.error("Account exists; refusing overwrite")
            user = User(
                username=username, password_hash=password_hash.hash(password), role=args.role
            )
            session.add(user)
            session.flush()
            session.add(
                AuditEvent(actor_id=user.id, action="user.bootstrap", resource_id=str(user.id))
            )
        print("Account created; password was not stored in plaintext")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
