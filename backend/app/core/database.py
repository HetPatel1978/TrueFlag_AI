from collections.abc import Generator

from fastapi import HTTPException, Request
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from app.core.release import require_session_compatible
from app.core.release_metadata import ReleaseCompatibilityError


def make_engine(url: str) -> Engine:
    options = {"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 3}
    engine = create_engine(url, pool_pre_ping=True, connect_args=options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def sqlite_foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def get_session(request: Request) -> Generator[Session, None, None]:
    with Session(request.app.state.engine) as session:
        if request.url.path not in {
            "/api/v1/auth/token",
            "/api/v1/auth/me",
            "/api/v1/internal/release",
        }:
            try:
                require_session_compatible(session)
            except ReleaseCompatibilityError as error:
                raise HTTPException(
                    503,
                    "Service compatibility unavailable",
                    headers={"X-Readiness-Code": error.code},
                ) from None
        yield session
