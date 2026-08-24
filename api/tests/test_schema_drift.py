"""The Alembic chain and the models must describe the same schema.

The suite's database is built by the real migration chain, so any drift
between the chain and `SQLModel.metadata` shows up as confusing failures in
unrelated tests. This asserts on the drift directly instead.

It exists because two columns had drifted unnoticed for a long time:
`deployment.hostname` and `deployment.subscription_id` were NOT NULL in the
chain and nullable in the models. Nothing caught it while the test schema came
from `create_all` -- the models were, by construction, always right about a
schema they themselves had built.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers every table on SQLModel.metadata)

API_ROOT = Path(__file__).resolve().parents[1]


def _alembic_autogenerate():
    """Import from the installed `alembic`, not the repo's `alembic/` package.

    `api/alembic/__init__.py` shadows the distribution whenever `api/` is on
    `sys.path`, which it always is under pytest. Drop those entries for the
    duration of the import and put them straight back.
    """
    shadowed = [p for p in sys.path if p and Path(p).resolve() == API_ROOT]
    for entry in shadowed:
        sys.path.remove(entry)
    try:
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext
    finally:
        sys.path[0:0] = shadowed
    return compare_metadata, MigrationContext


def test_migrated_schema_matches_the_models(test_database):
    """No drift anywhere -- not filtered to the tables a change touched."""
    compare_metadata, MigrationContext = _alembic_autogenerate()

    with test_database.engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), SQLModel.metadata)

    assert [str(d) for d in diff] == []
