import pytest
import sys
import importlib
from pathlib import Path

from starlette.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session
from typer.testing import CliRunner

from app.db import get_session, init_db
from app.main import app


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        echo=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_db(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture()
def cli_runner(tmp_path, monkeypatch):
    project_root = Path(__file__).resolve().parents[1]
    sys.path.append(str(project_root))
    # Use a temporary file-based SQLite DB for isolation
    # TODO: Refactor this to use sqlite:///:memory:
    db_path = tmp_path / "test_cli.db"
    # Ensure a clean DB file
    if db_path.exists():
        db_path.unlink()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    import app.db as db

    importlib.reload(db)
    init_db(db.engine)

    import app.cli as cli

    importlib.reload(cli)

    return CliRunner(), cli.app


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_session] = override_get_db

    with TestClient(app) as client:
        yield client

    app.dependency_overrides.clear()
