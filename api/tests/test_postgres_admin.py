"""The tenant cluster's transport: sessions, quoting, and autocommit.

Run against a real PostgreSQL: every property here is one psycopg and the
server decide between them.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest

from app.config import CaelusSettings
from app.services.postgres_admin import PostgresAdminClient, PostgresAdminException
from tests import tenant_cluster
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture(scope="session", autouse=True)
def _bootstrapped_cluster(test_database):
    tenant_cluster.bootstrap(TEST_DATABASE_URL)


@pytest.fixture
def client():
    return PostgresAdminClient.from_settings(tenant_cluster.settings_for(TEST_DATABASE_URL))


@pytest.fixture(autouse=True)
def _clean_cluster():
    tenant_cluster.drop_tenant_objects(TEST_DATABASE_URL)
    yield
    tenant_cluster.drop_tenant_objects(TEST_DATABASE_URL)


@pytest.fixture
def name():
    return f"dpl_{uuid4().hex}"


# ── Configuration ─────────────────────────────────────────────────────────


def test_an_unconfigured_cluster_is_refused_by_name():
    """An unconfigured cluster names the missing settings."""
    with pytest.raises(PostgresAdminException) as exc:
        PostgresAdminClient.from_settings(CaelusSettings(_env_file=None))
    assert "tenant_db_host" in str(exc.value)
    assert "tenant_db_admin_password" in str(exc.value)


def test_an_unreachable_cluster_names_where_it_tried():
    client = PostgresAdminClient.from_settings(
        tenant_cluster.settings_for(TEST_DATABASE_URL, tenant_db_port=59999)
    )
    with pytest.raises(PostgresAdminException) as exc:
        client.role_exists("anything")
    assert "59999" in str(exc.value)


# ── Non-transactional statements ──────────────────────────────────────────


def test_create_database_is_refused_inside_a_transaction(client, name):
    """The reason this module has two execution paths."""
    client.execute("CREATE ROLE {role} LOGIN", identifiers={"role": name})
    # Without this the statement fails on `must be able to SET ROLE` first:
    # CREATEROLE confers admin_option but not set_option, so an admin cannot
    # create a database owned by a role it cannot assume.
    client.execute(
        "GRANT {role} TO {admin} WITH SET TRUE, INHERIT FALSE",
        identifiers={"role": name, "admin": tenant_cluster.ADMIN_ROLE},
    )

    with pytest.raises(PostgresAdminException) as exc:
        client.execute(
            "CREATE DATABASE {db} OWNER {role}", identifiers={"db": name, "role": name}
        )
    assert "cannot run inside a transaction block" in str(exc.value)

    client.execute_autocommit(
        "CREATE DATABASE {db} OWNER {role}", identifiers={"db": name, "role": name}
    )
    assert client.database_exists(name)


def test_drop_database_runs_under_an_assumed_role_in_one_session(client, name):
    """A drop needs autocommit and `SET ROLE` on the same connection."""
    client.execute("CREATE ROLE {role} LOGIN", identifiers={"role": name})
    client.execute(
        "GRANT {role} TO {admin} WITH SET TRUE, INHERIT FALSE",
        identifiers={"role": name, "admin": tenant_cluster.ADMIN_ROLE},
    )
    client.execute_autocommit(
        "CREATE DATABASE {db} OWNER {role}", identifiers={"db": name, "role": name}
    )

    with client.session(autocommit=True) as session:
        with session.as_role(name):
            session.execute("DROP DATABASE {db} WITH (FORCE)", identifiers={"db": name})
    assert not client.database_exists(name)


def test_dropping_a_database_the_admin_does_not_own_is_refused(client, name):
    """The same drop without the assumed role is refused."""
    client.execute("CREATE ROLE {role} LOGIN", identifiers={"role": name})
    client.execute(
        "GRANT {role} TO {admin} WITH SET TRUE, INHERIT FALSE",
        identifiers={"role": name, "admin": tenant_cluster.ADMIN_ROLE},
    )
    client.execute_autocommit(
        "CREATE DATABASE {db} OWNER {role}", identifiers={"db": name, "role": name}
    )

    with pytest.raises(PostgresAdminException) as exc:
        client.execute_autocommit("DROP DATABASE {db}", identifiers={"db": name})
    assert "must be owner" in str(exc.value)
    assert client.database_exists(name)


# ── Sessions and assumed roles ────────────────────────────────────────────


def test_as_role_resets_even_when_the_block_raises(client, name):
    client.execute("CREATE ROLE {role} LOGIN", identifiers={"role": name})
    client.execute(
        "GRANT {role} TO {admin} WITH SET TRUE, INHERIT FALSE",
        identifiers={"role": name, "admin": tenant_cluster.ADMIN_ROLE},
    )

    with client.session() as session:
        with pytest.raises(psycopg.Error):
            with session.as_role(name):
                assert session.fetchval("SELECT current_user") == name
                session.execute("SELECT no_such_function()")

    # A connection handed back still wearing a tenant's identity would make the
    # next statement on it run as that tenant.
    with client.session() as session:
        assert session.fetchval("SELECT current_user") == tenant_cluster.ADMIN_ROLE


def test_a_failed_session_commits_nothing(client, name):
    with pytest.raises(PostgresAdminException):
        with client.session() as session:
            session.execute("CREATE ROLE {role} LOGIN", identifiers={"role": name})
            session.execute("SELECT no_such_function()")
    assert not client.role_exists(name)


# ── Quoting ───────────────────────────────────────────────────────────────


def test_identifiers_are_quoted_rather_than_interpolated(client):
    """An identifier needing quotes survives a round trip."""
    awkward = f'dpl_{uuid4().hex[:8]}-needs "quoting"'
    client.execute("CREATE ROLE {role} NOLOGIN", identifiers={"role": awkward})
    try:
        assert client.role_exists(awkward)
    finally:
        client.execute("DROP ROLE {role}", identifiers={"role": awkward})


def test_literals_are_quoted_rather_than_interpolated(client, name):
    """A password with quotes in it travels safely inside the statement."""
    awkward = "pw' OR true --"
    client.execute("CREATE ROLE {role} LOGIN", identifiers={"role": name})
    client.execute(
        "ALTER ROLE {role} WITH PASSWORD {pw}",
        identifiers={"role": name},
        literals={"pw": awkward},
    )

    from sqlalchemy.engine import make_url

    url = make_url(TEST_DATABASE_URL)
    with psycopg.connect(
        host=url.host, port=url.port or 5432, user=name, password=awkward, dbname="postgres"
    ) as conn:
        assert conn.execute("SELECT current_user").fetchone()[0] == name


# ── Lookups ───────────────────────────────────────────────────────────────


def test_absence_is_an_answer_not_an_error(client, name):
    """Lookups answer rather than raise when nothing is there."""
    assert client.role_exists(name) is False
    assert client.database_exists(name) is False
    assert client.role_settings(name) == {}
    assert client.database_settings(name) == {}
    assert client.backend_pids(name) == []
    assert client.terminate_backends(name) == 0
