"""A stand-in tenant cluster for the relational-storage tests.

The suite's own PostgreSQL server, bootstrapped the way
`tf/app/caelus/tenant-bootstrap.sql` bootstraps the real one -- non-superuser
admin role included, since several behaviors under test only appear that way.
"""

from __future__ import annotations

import psycopg
from sqlalchemy.engine import make_url

from app.config import CaelusSettings

ADMIN_ROLE = "caelus_test_admin"
ADMIN_PASSWORD = "test-admin-password"


def _superuser_dsn(database_url: str) -> str:
    url = make_url(database_url).set(database="postgres")
    return (
        f"host={url.host} port={url.port or 5432} user={url.username} "
        f"password={url.password} dbname=postgres"
    )


def bootstrap(database_url: str) -> None:
    """Create the admin role and its grants; safe to run repeatedly."""
    with psycopg.connect(_superuser_dsn(database_url), autocommit=True) as conn:
        conn.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ADMIN_ROLE}') THEN
                    CREATE ROLE {ADMIN_ROLE};
                END IF;
            END
            $$;
            """
        )
        conn.execute(
            f"ALTER ROLE {ADMIN_ROLE} WITH LOGIN CREATEDB CREATEROLE "
            f"NOSUPERUSER NOREPLICATION NOBYPASSRLS PASSWORD '{ADMIN_PASSWORD}'"
        )
        conn.execute(f"GRANT pg_read_all_stats TO {ADMIN_ROLE}")
        conn.execute(f"GRANT pg_signal_backend TO {ADMIN_ROLE}")
        # temp_file_limit is superuser-only to set without this grant.
        conn.execute(f"GRANT SET ON PARAMETER temp_file_limit TO {ADMIN_ROLE}")


def settings_for(database_url: str, **overrides) -> CaelusSettings:
    url = make_url(database_url)
    fields = {
        "tenant_db_host": url.host,
        "tenant_db_port": url.port or 5432,
        "tenant_db_admin_user": ADMIN_ROLE,
        "tenant_db_admin_password": ADMIN_PASSWORD,
        "tenant_db_maintenance_db": "postgres",
        "tenant_db_pooler_host": "caelus-tenant-pooler.caelus-test.svc.cluster.local",
        "tenant_db_pooler_port": 6432,
        **overrides,
    }
    return CaelusSettings(_env_file=None, **fields)


def drop_tenant_objects(database_url: str, prefix: str = "dpl_") -> None:
    """Remove every database and role a test left behind."""
    with psycopg.connect(_superuser_dsn(database_url), autocommit=True) as conn:
        databases = [
            row[0]
            for row in conn.execute(
                "SELECT datname FROM pg_database WHERE datname LIKE %s", (prefix + "%",)
            ).fetchall()
        ]
        for name in databases:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        roles = [
            row[0]
            for row in conn.execute(
                "SELECT rolname FROM pg_roles WHERE rolname LIKE %s", (prefix + "%",)
            ).fetchall()
        ]
        for name in roles:
            conn.execute(f'DROP ROLE IF EXISTS "{name}"')
