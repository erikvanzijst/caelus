"""Migration coverage for `deployment_var` and `release_var`.

Each run migrates a throwaway schema (via ``PGOPTIONS=-csearch_path=...``) so
it never touches a local dev database.

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
from tests.conftest import TEST_DATABASE_URL


API_ROOT = Path(__file__).resolve().parents[1]
BEFORE_VARS = "e1f2a3b4c5d6"
VARS = "a3b4c5d6e7f8"


def _alembic(*args: str, schema: str) -> None:
    result = subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), *args],
        cwd=API_ROOT,
        env={
            **os.environ,
            "CAELUS_DATABASE_URL": TEST_DATABASE_URL,
            "PGOPTIONS": f"-csearch_path={schema}",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


@pytest.fixture
def migrated_schema():
    """A throwaway schema migrated to the revision *before* the var tables."""
    schema = f"mig_vars_{uuid4().hex[:8]}"
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        _alembic("upgrade", BEFORE_VARS, schema=schema)
        yield schema, create_engine(
            TEST_DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _tables(engine, schema):
    with engine.begin() as conn:
        return {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :schema"
                ),
                {"schema": schema},
            ).all()
        }


def test_migration_creates_both_tables_with_their_indexes(migrated_schema):
    schema, engine = migrated_schema
    _alembic("upgrade", VARS, schema=schema)

    assert {"deployment_var", "release_var"} <= _tables(engine, schema)
    with engine.begin() as conn:
        indexes = {
            r[0]
            for r in conn.execute(
                text("SELECT indexname FROM pg_indexes WHERE schemaname = :schema"),
                {"schema": schema},
            ).all()
        }
    assert {
        "ix_deployment_var_head",
        "ix_deployment_var_key_id",
        "ix_release_var_var",
    } <= indexes


def test_migration_leaves_the_existing_schema_alone(migrated_schema):
    """Purely additive: nothing migrates off `user_values_json`."""
    schema, engine = migrated_schema
    before = _tables(engine, schema)
    with engine.begin() as conn:
        columns_before = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = :schema"
            ),
            {"schema": schema},
        ).all()

    _alembic("upgrade", VARS, schema=schema)

    with engine.begin() as conn:
        columns_after = conn.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = :schema AND table_name = ANY(:existing)"
            ),
            {"schema": schema, "existing": list(before)},
        ).all()
    assert sorted(columns_after) == sorted(columns_before)


def test_migrated_schema_matches_the_models(migrated_schema):
    """The migration and `create_all` must not describe different tables."""
    schema, engine = migrated_schema
    _alembic("upgrade", VARS, schema=schema)

    import app.models  # noqa: F401
    from sqlmodel import SQLModel

    # Imported with the project root off `sys.path`, and only for as long as
    # that takes: otherwise the repo's own `alembic/` package shadows the
    # installed distribution (see the module docstring).
    shadowed = [p for p in sys.path if p and Path(p).resolve() == API_ROOT]
    for entry in shadowed:
        sys.path.remove(entry)
    try:
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
    finally:
        sys.path[0:0] = shadowed

    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), SQLModel.metadata)
    drift = [
        str(d) for d in diff if "deployment_var" in str(d) or "release_var" in str(d)
    ]
    assert drift == []


def test_downgrade_removes_both_tables(migrated_schema):
    schema, engine = migrated_schema
    _alembic("upgrade", VARS, schema=schema)
    _alembic("downgrade", BEFORE_VARS, schema=schema)

    assert not {"deployment_var", "release_var"} & _tables(engine, schema)
