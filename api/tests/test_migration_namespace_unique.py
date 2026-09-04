"""Migration coverage for the unconditional unique index on `deployment.namespace`.

Each run migrates a throwaway schema (via ``PGOPTIONS=-csearch_path=...``) so it
never touches the tables the rest of the suite or a local dev database relies
on.

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
BEFORE_UNIQUE = "e7f8a9b0c1d2"
UNIQUE = "a9b0c1d2e3f4"


def _alembic(*args: str, schema: str) -> subprocess.CompletedProcess:
    return subprocess.run(
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


def _upgrade(*args: str, schema: str) -> None:
    result = _alembic(*args, schema=schema)
    assert result.returncode == 0, f"alembic {' '.join(args)} failed:\n{result.stderr}"


@pytest.fixture
def migrated_schema():
    """A throwaway schema migrated to the revision *before* the unique index."""
    schema = f"mig_nsunique_{uuid4().hex[:8]}"
    engine = create_engine(TEST_DATABASE_URL)
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        _upgrade("upgrade", BEFORE_UNIQUE, schema=schema)
        yield schema, create_engine(
            TEST_DATABASE_URL, connect_args={"options": f"-csearch_path={schema}"}
        )
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))


def _seed_deployment(conn, *, namespace: str, name: str, status: str = "ready") -> None:
    """One deployment and its release, enough to satisfy the NOT NULL FKs."""
    user_id = conn.execute(
        text(
            "INSERT INTO \"user\" (email, is_admin, created_at) "
            "VALUES (:email, false, now()) RETURNING id"
        ),
        {"email": f"{uuid4().hex[:8]}@example.com"},
    ).scalar_one()
    product_id = conn.execute(
        text("INSERT INTO product (name, created_at) VALUES (:n, now()) RETURNING id"),
        {"n": f"prod-{uuid4().hex[:8]}"},
    ).scalar_one()
    template_id = conn.execute(
        text(
            "INSERT INTO product_template_version "
            "(product_id, chart_ref, chart_version, values_schema_json, created_at) "
            "VALUES (:p, 'oci://example/chart', '1.0.0', '{}', now()) RETURNING id"
        ),
        {"p": product_id},
    ).scalar_one()
    plan_id = conn.execute(
        text("INSERT INTO plan (name, product_id, created_at) VALUES ('Free', :p, now()) RETURNING id"),
        {"p": product_id},
    ).scalar_one()
    ptv_id = conn.execute(
        text(
            "INSERT INTO plan_template_version "
            "(plan_id, price_cents, billing_interval, created_at) "
            "VALUES (:pl, 0, 'monthly', now()) RETURNING id"
        ),
        {"pl": plan_id},
    ).scalar_one()
    sub_id = conn.execute(
        text(
            "INSERT INTO subscription "
            "(plan_template_id, user_id, status, payment_status, created_at) "
            "VALUES (:t, :u, 'active', 'current', now()) RETURNING id"
        ),
        {"t": ptv_id, "u": user_id},
    ).scalar_one()

    deployment_id, release_id = uuid4(), uuid4()
    conn.execute(text("SET CONSTRAINTS ALL DEFERRED"))
    conn.execute(
        text(
            "INSERT INTO deployment (id, user_id, desired_template_id, name, namespace, "
            "status, generation, created_at, subscription_id, desired_release_id) "
            "VALUES (:id, :u, :t, :name, :ns, :status, 1, now(), :sub, :rel)"
        ),
        {
            "id": deployment_id,
            "u": user_id,
            "t": template_id,
            "name": name,
            "ns": namespace,
            "status": status,
            "sub": sub_id,
            "rel": release_id,
        },
    )
    conn.execute(
        text(
            "INSERT INTO deployment_release (id, number, deployment_id, template_id, created_at) "
            "VALUES (:id, 1, :dep, :t, now())"
        ),
        {"id": release_id, "dep": deployment_id, "t": template_id},
    )


def test_the_index_is_unconditional(migrated_schema):
    """No status predicate: a deleted row's namespace is still taken."""
    schema, engine = migrated_schema
    _upgrade("upgrade", UNIQUE, schema=schema)

    with engine.begin() as conn:
        predicate = conn.execute(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = :schema AND indexname = 'uq_deployment_namespace'"
            ),
            {"schema": schema},
        ).scalar_one()
    assert "UNIQUE" in predicate
    assert "WHERE" not in predicate


def test_the_subsumed_partial_index_is_dropped(migrated_schema):
    schema, engine = migrated_schema
    _upgrade("upgrade", UNIQUE, schema=schema)

    with engine.begin() as conn:
        names = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = 'deployment'"
            ),
            {"schema": schema},
        ).scalars().all()
    assert "uq_deployment_ns_name_active" not in names


def test_duplicates_fail_the_migration_by_name(migrated_schema):
    """The operator has to know which live namespaces to go and look at."""
    schema, engine = migrated_schema
    with engine.begin() as conn:
        _seed_deployment(conn, namespace="dup-ns", name="a-000001")
        _seed_deployment(conn, namespace="dup-ns", name="b-000002")

    result = _alembic("upgrade", UNIQUE, schema=schema)

    assert result.returncode != 0
    assert "dup-ns (2 rows)" in result.stderr


def test_downgrade_restores_the_partial_index(migrated_schema):
    schema, engine = migrated_schema
    _upgrade("upgrade", UNIQUE, schema=schema)
    _upgrade("downgrade", BEFORE_UNIQUE, schema=schema)

    with engine.begin() as conn:
        names = conn.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = 'deployment'"
            ),
            {"schema": schema},
        ).scalars().all()
    assert "uq_deployment_ns_name_active" in names
    assert "uq_deployment_namespace" not in names
