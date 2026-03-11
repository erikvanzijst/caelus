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
from app.models import UserORM


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
    monkeypatch.setenv("CAELUS_USER_EMAIL", "cli-test@example.com")

    import app.db as db

    importlib.reload(db)
    init_db(db.engine)

    import app.cli as cli

    importlib.reload(cli)

    return CliRunner(), cli.app


ADMIN_EMAIL = "test@example.com"
AUTH_HEADER = {"X-Auth-Request-Email": ADMIN_EMAIL}

USER_EMAIL = "regular@example.com"
USER_AUTH_HEADER = {"X-Auth-Request-Email": USER_EMAIL}

OTHER_EMAIL = "other@example.com"
OTHER_AUTH_HEADER = {"X-Auth-Request-Email": OTHER_EMAIL}


@pytest.fixture
def client(db_session):
    """Test client authenticated as an admin user."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_session] = override_get_db

    # Pre-create the default test user as admin so existing tests pass
    admin_user = UserORM(email=ADMIN_EMAIL, is_admin=True)
    db_session.add(admin_user)
    db_session.commit()

    with TestClient(app, headers=AUTH_HEADER) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def user_client(db_session):
    """Test client authenticated as a regular (non-admin) user."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_session] = override_get_db

    # Pre-create admin user (some tests need resources created by admin)
    admin_user = UserORM(email=ADMIN_EMAIL, is_admin=True)
    db_session.add(admin_user)
    db_session.commit()
    db_session.refresh(admin_user)

    with TestClient(app, headers=USER_AUTH_HEADER) as c:
        yield c, admin_user

    app.dependency_overrides.clear()
