"""Coverage for the migration advisory lock in ``alembic/env.py``.

Both the ``caelus-api`` and ``caelus-worker`` Deployments run a ``migrate``
init container, so a rollout starts two ``alembic upgrade head`` processes
against the same database at the same moment. ``env.py`` takes a
transaction-scoped Postgres advisory lock so the second one waits instead of
replaying DDL the first is already applying.

Alembic is driven as a subprocess, like ``test_migration_product_visibility``:
the repo's own ``alembic/`` package shadows the installed ``alembic``
distribution whenever the project root is on ``sys.path``, which it always is
under pytest.
"""

from __future__ import annotations

import ast
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

API_ROOT = Path(__file__).resolve().parents[1]
ENV_PY = API_ROOT / "alembic" / "env.py"
ALEMBIC_BIN = str(Path(sys.executable).parent / "alembic")

# The number `env.py` must keep passing to pg_advisory_xact_lock(). Spelled
# out here rather than imported because importing `env.py` *runs* migrations:
# the module has no `if __name__` guard, it calls run_migrations_online() at
# import time by design.
EXPECTED_LOCK_KEY = 7161116398997167981

PG_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

# A logging config that echoes every statement SQLAlchemy emits, so a test can
# assert on the SQL the migration run actually sent to the database.
SQL_ECHO_INI = """
[alembic]
script_location = {script_location}
version_locations = {version_locations}
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = INFO
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
"""

# A single revision that SQLite can actually apply. The real migration chain
# cannot run on SQLite at all -- 10fb17efd947 calls op.create_foreign_key(),
# which SQLite has no ALTER for -- so pointing `version_locations` at a
# scratch revision is the only way to exercise the real `env.py` against a
# SQLite connection.
PROBE_REVISION = '''
from alembic import op
import sqlalchemy as sa

revision = "aaa000probe"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("advisory_lock_probe", sa.Column("id", sa.Integer(), primary_key=True))


def downgrade() -> None:
    op.drop_table("advisory_lock_probe")
'''


def _lock_key_from_env_py() -> int:
    """Read ``MIGRATION_ADVISORY_LOCK_KEY`` out of ``env.py`` without running it."""
    module = ast.parse(ENV_PY.read_text())
    for node in module.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "MIGRATION_ADVISORY_LOCK_KEY"
            for t in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("env.py no longer defines MIGRATION_ADVISORY_LOCK_KEY")


def test_lock_key_is_a_stable_integer():
    """The key is a compile-time constant and must never drift.

    A rollout serializes two runners only if both compute the same number, so
    changing this (or deriving it from a hash at runtime) would silently stop
    the lock from serializing against the runner it is replacing.
    """
    key = _lock_key_from_env_py()
    assert isinstance(key, int) and not isinstance(key, bool)
    assert key == EXPECTED_LOCK_KEY
    # pg_advisory_xact_lock() takes a signed 64-bit key.
    assert -(2**63) <= key < 2**63


def test_sqlite_migrations_run_without_attempting_the_advisory_lock(tmp_path):
    """The dialect guard keeps SQLite (which has no advisory locks) working."""
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "aaa000probe_probe.py").write_text(PROBE_REVISION)
    ini = tmp_path / "alembic.ini"
    ini.write_text(
        SQL_ECHO_INI.format(
            script_location=API_ROOT / "alembic",
            version_locations=versions,
        )
    )
    db_path = tmp_path / "probe.db"

    result = subprocess.run(
        [ALEMBIC_BIN, "-c", str(ini), "upgrade", "head"],
        cwd=API_ROOT,
        env={**os.environ, "CAELUS_DATABASE_URL": f"sqlite:///{db_path}"},
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, f"alembic upgrade failed:\n{result.stderr}"
    # The migration really ran, so the assertion below is not vacuous.
    with sqlite3.connect(db_path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert "advisory_lock_probe" in tables
    assert "CREATE TABLE advisory_lock_probe" in result.stderr
    # ...and it never reached for a Postgres-only function on the way.
    assert "pg_advisory" not in result.stderr


@pytest.mark.skipif(
    not PG_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is not set",
)
def test_concurrent_postgres_upgrades_serialize():
    """Two simultaneous ``upgrade head`` runs both succeed instead of colliding.

    This is the rollout the init containers actually perform. Without the
    lock the loser fails part-way -- observed in prod as a duplicate key on
    pg_type's unique index while both runners ran CREATE TYPE in parallel.
    Each run migrates a throwaway schema so it never touches the tables the
    rest of the suite or a dev database relies on.
    """
    schema = f"mig_lock_{uuid4().hex[:8]}"
    admin = create_engine(PG_TEST_DATABASE_URL)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        runners = [
            subprocess.Popen(
                [ALEMBIC_BIN, "upgrade", "head"],
                cwd=API_ROOT,
                env={
                    **os.environ,
                    "CAELUS_DATABASE_URL": PG_TEST_DATABASE_URL,
                    "PGOPTIONS": f"-csearch_path={schema}",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [runner.communicate() for runner in runners]

        for runner, (_, stderr) in zip(runners, outputs):
            assert runner.returncode == 0, f"concurrent upgrade failed:\n{stderr}"
            assert "Acquiring migration advisory lock" in stderr

        with admin.connect() as conn:
            conn.execute(text(f'SET search_path TO "{schema}"'))
            revisions = conn.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
        assert len(revisions) == 1
    finally:
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
