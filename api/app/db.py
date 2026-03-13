from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Iterator, Generator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
_url = _settings.database_url
is_sqlite = _url.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
poolclass = StaticPool if is_sqlite else None

engine = create_engine(
    _url,
    echo=False,
    connect_args=connect_args,
    poolclass=poolclass,
)


def init_db(engine) -> None:
    # Ensure models are imported before creating tables.
    logger.info("Initializing database schema")
    SQLModel.metadata.create_all(engine)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(engine) as session:
        try:
            yield session
        except Exception:
            logger.exception("Session scope failed; rolling back")
            session.rollback()
            raise
