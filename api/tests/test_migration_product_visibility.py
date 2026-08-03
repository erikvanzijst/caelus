"""Migration coverage for `product.visibility`.

The migration chain uses constructs SQLite cannot ALTER, so it only runs on
PostgreSQL — hence the same ``POSTGRES_TEST_DATABASE_URL`` gate the other
Postgres-only tests use. Each run migrates a throwaway schema (via
``PGOPTIONS=-csearch_path=...``) so it never touches the tables the rest of the
suite or a local dev database relies on.

Alembic is driven as a subprocess: the repo's own ``alembic/`` package shadows
the installed ``alembic`` distribution whenever the project root is on
``sys.path``, which it always is under pytest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

PG_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is not set",
)

API_ROOT = Path(__file__).resolve().parents[1]
BEFORE_VISIBILITY = "a7b8c9d0e1f2"
VISIBILITY = "b1c2d3e4f5a6"


def _alembic(*args: str, schema: str) -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), *args],
        cwd=API_ROOT,
        env={
            **os.environ,
            "CAELUS_DATABASE_URL": PG_TEST_DATABASE_URL,
            "PGOPTIONS": f"-csearch_path={schema}",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


@pytest.fixture
def migrated_schema():
    """A throwaway schema migrated to the revision *before* visibility."""
    schema = f"mig_visibility_{uuid4().hex[:8]}"
    engine = create_engine(PG_TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        _alembic("upgrade", BEFORE_VISIBILITY, schema=schema)
        yield schema, create_engine(
            PG_TEST_DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def test_migration_backfills_existing_products_to_public(migrated_schema):
    """Existing products keep today's behavior: offered to every end user."""
    schema, engine = migrated_schema
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO product (name, created_at) VALUES ('legacy', now())")
        )

    _alembic("upgrade", VISIBILITY, schema=schema)

    with engine.begin() as conn:
        rows = conn.execute(text("SELECT name, visibility FROM product")).all()
    assert rows == [("legacy", "public")]


def test_rows_created_after_the_migration_default_to_admin(migrated_schema):
    """The column's server default keeps new products hidden."""
    schema, engine = migrated_schema
    _alembic("upgrade", VISIBILITY, schema=schema)

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO product (name, created_at) VALUES ('fresh', now())"))
        visibility = conn.execute(
            text("SELECT visibility FROM product WHERE name = 'fresh'")
        ).scalar_one()
    assert visibility == "admin"


def test_visibility_is_not_nullable(migrated_schema):
    schema, engine = migrated_schema
    _alembic("upgrade", VISIBILITY, schema=schema)

    with engine.begin() as conn:
        nullable = conn.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'product' "
                "AND column_name = 'visibility'"
            ),
            {"schema": schema},
        ).scalar_one()
    assert nullable == "NO"


def test_downgrade_removes_the_column(migrated_schema):
    schema, engine = migrated_schema
    _alembic("upgrade", VISIBILITY, schema=schema)
    _alembic("downgrade", BEFORE_VISIBILITY, schema=schema)

    with engine.begin() as conn:
        columns = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = 'product'"
            ),
            {"schema": schema},
        ).scalars().all()
    assert "visibility" not in columns
