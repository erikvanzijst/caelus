from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Generator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine


def _database_url() -> str:
    return os.getenv("DATABASE_URL", "sqlite:///./caelus.db")


DATABASE_URL = _database_url()
is_sqlite = DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
poolclass = StaticPool if is_sqlite else None

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    poolclass=poolclass,
)


def init_db(engine) -> None:
    # Ensure models are imported before creating tables.
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    return get_session()
