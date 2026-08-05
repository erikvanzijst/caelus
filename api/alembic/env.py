from __future__ import annotations

import logging
import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool, text
from sqlmodel import SQLModel

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT))

from app import models  # noqa: E402,F401
from app.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().database_url)


target_metadata = SQLModel.metadata

logger = logging.getLogger("alembic.env")

# Serializes concurrent `alembic upgrade head` runs against one database.
#
# Both the caelus-api and caelus-worker Deployments run a `migrate` init
# container, so a rollout starts two upgrades at the same moment. Whichever
# one is second must wait for the first rather than replay the same DDL:
# `ALTER TABLE` merely blocks the loser on an ACCESS EXCLUSIVE lock (which
# then fails with "column already exists"), while catalog-level DDL such as
# `CREATE TYPE` takes no table lock at all and both runners collide on
# pg_type's unique index instead.
#
# The value is an arbitrary fixed 64-bit key -- the ASCII bytes of
# "caelus_m" -- and is deliberately *not* derived from a hash at runtime:
# every deployed revision must compute the same number, or a rollout would
# stop serializing against the runner it is replacing. Never change it.
MIGRATION_ADVISORY_LOCK_KEY = 7161116398997167981


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

        with context.begin_transaction():
            # `transaction_per_migration` is not configured, so Alembic's
            # default applies and the whole upgrade runs in this one
            # transaction -- which is what lets a single transaction-scoped
            # lock cover every revision. Enabling `transaction_per_migration`
            # would silently narrow the lock to one migration at a time and
            # reopen the race between revisions.
            if connection.dialect.name == "postgresql":
                logger.info(
                    "Acquiring migration advisory lock %s (waits for any "
                    "concurrent migration runner to finish)",
                    MIGRATION_ADVISORY_LOCK_KEY,
                )
                # Transaction-scoped: released on commit *or* rollback, so a
                # failed upgrade cannot strand the lock. pg_advisory_lock()
                # would need an explicit unlock and leaks on failure.
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:key)"),
                    {"key": MIGRATION_ADVISORY_LOCK_KEY},
                )
                logger.info("Migration advisory lock acquired")

            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
