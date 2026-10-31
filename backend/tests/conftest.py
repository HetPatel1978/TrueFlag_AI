import secrets
from pathlib import Path

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from alembic import command
from app.core.config import Settings
from app.core.database import make_engine
from app.main import create_app
from app.models import User
from app.security.auth import password_hash

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture
def platform(tmp_path, monkeypatch):
    url = "sqlite+pysqlite:///" + (tmp_path / "test.db").as_posix()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    command.upgrade(Config(str(BACKEND / "alembic.ini")), "head")
    settings = Settings()
    engine = make_engine(url)
    password = secrets.token_urlsafe(24)
    with Session(engine) as session, session.begin():
        for name, role in [("admin", "admin"), ("analyst", "analyst")]:
            session.add(User(username=name, role=role, password_hash=password_hash.hash(password)))
    with TestClient(create_app(settings, engine)) as client:
        yield client, engine, settings, password
    engine.dispose()
