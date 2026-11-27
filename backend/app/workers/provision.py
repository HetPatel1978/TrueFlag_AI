"""Operator CLI: authenticate an active administrator and provision/revoke a service token."""

import argparse
import getpass
import os
import secrets
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT, Settings
from app.core.database import make_engine
from app.models import User
from app.security.auth import password_hash
from app.services.assessment_jobs import AssessmentJobService, WorkerDenied


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-username", required=True)
    parser.add_argument("--name", default="local-worker")
    parser.add_argument("--token-file", default="runtime/assessment_worker_token")
    parser.add_argument("--revoke", type=UUID)
    args = parser.parse_args()
    engine = None
    created = None
    try:
        engine = make_engine(Settings().database_url)
        password = getpass.getpass("Administrator password: ")
        with Session(engine) as session:
            user = session.scalar(
                select(User).where(
                    User.username == args.admin_username.lower(),
                    User.active.is_(True),
                    User.role == "admin",
                )
            )
            if user is None or not password_hash.verify(password, user.password_hash):
                raise WorkerDenied("worker_provisioning_denied")
            admin_id = user.id
        queue = AssessmentJobService(engine)
        if args.revoke:
            queue.revoke_worker(admin_id=admin_id, worker_id=args.revoke)
            print("Worker revoked")
        else:
            target = (PROJECT_ROOT / args.token_file).resolve()
            runtime_root = (PROJECT_ROOT / "runtime").resolve()
            if not runtime_root.is_relative_to(PROJECT_ROOT.resolve()) or not target.is_relative_to(
                runtime_root
            ):
                raise ValueError
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            token = secrets.token_hex(32)
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = target
            with os.fdopen(descriptor, "w", encoding="ascii") as stream:
                stream.write(token)
            queue.register_worker(admin_id=admin_id, name=args.name, token=token)
            created = None
            print("Worker provisioned; token stored in the ignored runtime file")
        return 0
    except Exception:
        if created is not None:
            created.unlink(missing_ok=True)
        print("Worker provisioning unavailable; credentials were not displayed")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
