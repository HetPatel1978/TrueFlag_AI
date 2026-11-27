"""Database-backed fixed-window login protection shared across API workers."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, or_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import LoginThrottle


def utcnow():
    return datetime.now(timezone.utc)


def consume_login_attempt(session: Session, client: str, settings: Settings) -> bool:
    key = hmac.new(
        settings.jwt_secret.get_secret_value().encode(),
        b"trueflag.login-throttle.v1\0" + client.encode(),
        hashlib.sha256,
    ).hexdigest()
    now = utcnow()
    table = LoginThrottle.__table__
    expired = table.c.window_start <= now - timedelta(seconds=settings.login_window_seconds)
    insert = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = insert(table).values(key_sha256=key, window_start=now, attempt_count=1)
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.key_sha256],
        set_={
            "window_start": case((expired, now), else_=table.c.window_start),
            "attempt_count": case((expired, 1), else_=table.c.attempt_count + 1),
        },
        where=or_(expired, table.c.attempt_count < settings.login_attempt_limit),
    ).returning(table.c.attempt_count)
    try:
        accepted = session.scalar(statement) is not None
        session.commit()
        return accepted
    except BaseException:
        session.rollback()
        raise
