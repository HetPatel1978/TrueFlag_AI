from collections.abc import Generator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session


def make_engine(url: str) -> Engine:
    options = {"check_same_thread": False} if url.startswith("sqlite") else {"connect_timeout": 3}
    return create_engine(url, pool_pre_ping=True, connect_args=options)


def get_session(request: Request) -> Generator[Session, None, None]:
    with Session(request.app.state.engine) as session:
        yield session
