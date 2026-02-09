from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, StaticPool
from sqlmodel import Session
from typer.testing import CliRunner

from app.db import init_db


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
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")

    import app.db as db

    importlib.reload(db)
    init_db(db.engine)

    import app.cli as cli

    importlib.reload(cli)

    return CliRunner(), cli.app
