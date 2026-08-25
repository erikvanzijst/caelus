"""Provisioning a deployment's database on the tenant cluster.

Run against a real PostgreSQL bootstrapped by `tests/tenant_cluster.py` with a
non-superuser admin role, which is what production uses -- a superuser would
pass several of these for reasons production does not have.
"""

from __future__ import annotations

from uuid import uuid4

import psycopg
import pytest
from cryptography.fernet import Fernet
from sqlmodel import Session, select

from app.config import CaelusSettings
from app.models import (
    BillingInterval,
    DeploymentDatabaseORM,
    PlanORM,
    PlanTemplateVersionORM,
    ProductORM,
    ProductTemplateVersionORM,
    SubscriptionORM,
    UserORM,
)
from app.models.core import _utcnow
from app.services import relational_storage as rs
from app.services import var_crypto
from app.services.errors import IntegrityException
from app.services.postgres_admin import PostgresAdminClient, PostgresAdminException
from tests import tenant_cluster
from tests.conftest import TEST_DATABASE_URL, make_deployment_with_release

KEY = Fernet.generate_key().decode()

MEGABYTE = 1024 * 1024


@pytest.fixture(scope="session", autouse=True)
def _bootstrapped_cluster(test_database):
    tenant_cluster.bootstrap(TEST_DATABASE_URL)


@pytest.fixture
def settings():
    return tenant_cluster.settings_for(TEST_DATABASE_URL)


@pytest.fixture
def client(settings):
    return PostgresAdminClient.from_settings(settings)


@pytest.fixture(autouse=True)
def _keyring(monkeypatch):
    """A keyring, since a stored password is encrypted before it is applied."""
    monkeypatch.setattr(
        "app.services.var_crypto.get_settings",
        lambda: CaelusSettings(var_encryption_keys=[KEY], _env_file=None),
    )
    var_crypto.get_keyring.cache_clear()
    yield
    var_crypto.get_keyring.cache_clear()


@pytest.fixture(autouse=True)
def _clean_cluster():
    """Every test starts and ends with no tenant objects on the cluster."""
    tenant_cluster.drop_tenant_objects(TEST_DATABASE_URL)
    yield
    tenant_cluster.drop_tenant_objects(TEST_DATABASE_URL)


@pytest.fixture
def session(test_database, db_session):
    with Session(test_database.engine) as session:
        yield session


def _deployment(session, *, database_bytes: int | None = 100 * MEGABYTE, enabled: bool = True):
    token = uuid4().hex[:8]
    user = UserORM(email=f"rs-{token}@example.com")
    product = ProductORM(name=f"rs-product-{token}", created_at=_utcnow())
    session.add(user)
    session.add(product)
    session.commit()

    template = ProductTemplateVersionORM(
        product_id=product.id,
        chart_ref="oci://example/chart",
        chart_version="1.0.0",
        system_values_json={"relationalStorage": {"enabled": enabled}},
    )
    session.add(template)
    session.commit()

    plan = PlanORM(name=f"plan-{token}", product_id=product.id, created_at=_utcnow())
    session.add(plan)
    session.flush()
    ptv = PlanTemplateVersionORM(
        plan_id=plan.id,
        price_cents=0,
        billing_interval=BillingInterval.MONTHLY,
        storage_bytes=0,
        database_bytes=database_bytes,
        created_at=_utcnow(),
    )
    session.add(ptv)
    session.flush()
    plan.template_id = ptv.id
    subscription = SubscriptionORM(
        plan_template_id=ptv.id, user_id=user.id, created_at=_utcnow()
    )
    session.add(subscription)
    session.commit()

    deployment = make_deployment_with_release(
        session,
        user_id=user.id,
        desired_template_id=template.id,
        subscription_id=subscription.id,
        hostname=f"{token}.example.test",
        name=f"app-{token}",
        namespace=f"ns-{token}",
    )
    session.commit()
    session.refresh(deployment)
    return deployment


def _connect_as_tenant(
    credentials: rs.DatabaseCredentials,
    *,
    database: str | None = None,
    autocommit: bool = False,
):
    """Connect as the tenant's pod would, minus the pooler.

    `autocommit` matters: psycopg opens a transaction per statement, and both
    `CREATE DATABASE` and `ALTER DATABASE` on a read-only database fail on that
    before reaching what is under test.
    """
    from sqlalchemy.engine import make_url

    url = make_url(TEST_DATABASE_URL)
    return psycopg.connect(
        host=url.host,
        port=url.port or 5432,
        user=credentials.user,
        password=credentials.password,
        dbname=database or credentials.database,
        connect_timeout=5,
        autocommit=autocommit,
    )


# ── Opt-in, naming and the allowance ──────────────────────────────────────


def test_only_a_products_system_values_can_enable_it(session):
    deployment = _deployment(session, enabled=True)
    assert rs.is_enabled(deployment) is True

    off = _deployment(session, enabled=False)
    assert rs.is_enabled(off) is False

    # A tenant controls user values, so this must change nothing.
    off.user_values_json = {"relationalStorage": {"enabled": True}}
    session.add(off)
    session.commit()
    assert rs.is_enabled(off) is False


def test_names_are_the_deployment_uuid_and_need_no_quoting(session, client):
    deployment = _deployment(session)
    name = rs.database_name(deployment)

    assert name == rs.role_name(deployment)
    assert name == "dpl_" + deployment.id.hex
    assert "-" not in name
    assert len(name.encode()) <= 63

    # Valid unquoted in a real statement, which is the property that matters.
    client.execute(f"CREATE ROLE {name} NOLOGIN")
    assert client.role_exists(name)


def test_a_plan_without_an_allowance_provisions_nothing(session, client, settings):
    for database_bytes in (None, 0, -1):
        deployment = _deployment(session, database_bytes=database_bytes)
        with pytest.raises(IntegrityException) as exc:
            rs.ensure_database(session, deployment, client=client, settings=settings)
        assert "allowance" in str(exc.value)
        # Fail-closed means fail *before* creating anything.
        assert not client.role_exists(rs.role_name(deployment))
        assert rs.get_record(session, deployment) is None


def test_an_unreachable_cluster_fails_closed(session, settings):
    deployment = _deployment(session)
    unreachable = PostgresAdminClient.from_settings(
        tenant_cluster.settings_for(TEST_DATABASE_URL, tenant_db_port=59999)
    )
    with pytest.raises(PostgresAdminException):
        rs.ensure_database(session, deployment, client=unreachable, settings=settings)


# ── Provisioning ──────────────────────────────────────────────────────────


def test_a_clean_provision_yields_a_working_credential(session, client, settings):
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)

    assert credentials.database == rs.database_name(deployment)
    assert credentials.user == rs.role_name(deployment)
    # The credential addresses the pooler, never the server.
    assert credentials.host == settings.tenant_db_pooler_host
    assert credentials.port == settings.tenant_db_pooler_port
    assert credentials.url.startswith(f"postgresql://{credentials.user}:")

    with _connect_as_tenant(credentials) as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == credentials.database
        conn.execute("CREATE TABLE t (id int)")

    record = rs.get_record(session, deployment)
    assert record is not None
    assert var_crypto.decrypt(record.password_encrypted, record.key_id) == credentials.password
    assert record.quota_state == rs.QUOTA_OK


def test_the_role_owns_its_database_and_holds_nothing_else(session, client, settings):
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)

    attributes = client.fetchval(
        "SELECT (rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls)::text "
        "FROM pg_roles WHERE rolname = %s",
        (credentials.user,),
    )
    assert attributes == "(f,f,f,f,f)"

    owner = client.fetchval(
        "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = %s",
        (credentials.database,),
    )
    assert owner == credentials.user

    with _connect_as_tenant(credentials, autocommit=True) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("CREATE DATABASE sneaky")


def test_re_running_repairs_rather_than_rotates(session, client, settings):
    deployment = _deployment(session)
    first = rs.ensure_database(session, deployment, client=client, settings=settings)
    second = rs.ensure_database(session, deployment, client=client, settings=settings)

    # A rotation on every reconcile would break every pod already holding the
    # credential until it happened to restart.
    assert second.password == first.password
    rows = session.exec(
        select(DeploymentDatabaseORM).where(
            DeploymentDatabaseORM.deployment_id == deployment.id
        )
    ).all()
    assert len(rows) == 1
    with _connect_as_tenant(second) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_a_role_without_a_database_is_completed_by_the_next_run(session, client, settings):
    """A run must not conclude from the role that the database exists."""
    deployment = _deployment(session)
    role = rs.role_name(deployment)
    client.execute(f"CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE")
    assert not client.database_exists(rs.database_name(deployment))

    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    assert client.database_exists(credentials.database)
    with _connect_as_tenant(credentials) as conn:
        assert conn.execute("SELECT current_user").fetchone()[0] == role


def test_a_database_without_a_row_is_adopted_by_the_next_run(session, client, settings):
    """Cluster objects without a row: the new password is re-asserted."""
    deployment = _deployment(session)
    role = rs.role_name(deployment)
    database = rs.database_name(deployment)
    client.execute(f"CREATE ROLE {role} LOGIN PASSWORD 'stale' NOSUPERUSER NOCREATEDB")
    client.execute(f"GRANT {role} TO {settings.tenant_db_admin_user} WITH SET TRUE, INHERIT FALSE")
    client.execute_autocommit(f"CREATE DATABASE {database} OWNER {role}")

    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    assert credentials.password != "stale"
    with _connect_as_tenant(credentials) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_an_interrupted_store_is_repaired_on_the_next_run(session, client, settings):
    """A crash after the store leaves a password the next run makes work."""
    deployment = _deployment(session)
    role = rs.role_name(deployment)
    client.execute(f"CREATE ROLE {role} LOGIN PASSWORD 'not-the-stored-one' NOSUPERUSER")

    # Exactly what the crashed run would have left behind: the row, and no
    # ALTER ROLE.
    record, password = rs._store_password(session, deployment, None)
    with pytest.raises(psycopg.OperationalError):
        _connect_as_tenant(
            rs.DatabaseCredentials(
                host="", port=0, database="postgres", user=role, password=password
            ),
            database="postgres",
        )

    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    assert credentials.password == password
    with _connect_as_tenant(credentials) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


# ── Isolation ─────────────────────────────────────────────────────────────


def test_one_tenant_cannot_connect_to_another_tenants_database(session, client, settings):
    first = rs.ensure_database(session, _deployment(session), client=client, settings=settings)
    second = rs.ensure_database(session, _deployment(session), client=client, settings=settings)

    with pytest.raises(psycopg.OperationalError) as exc:
        _connect_as_tenant(second, database=first.database)
    assert "permission denied" in str(exc.value).lower()

    # And the owner is unaffected by its own revocation.
    with _connect_as_tenant(first) as conn:
        assert conn.execute("SELECT 1").fetchone()[0] == 1


def test_provisioning_fails_when_the_revocation_did_not_take_effect(
    session, client, settings, monkeypatch
):
    """A revoke issued without `SET ROLE` warns and does nothing, and the
    post-condition turns that into a failed provision."""
    deployment = _deployment(session)

    def revoke_without_set_role(client_, *, database, role, deployment):
        client_.execute(
            "REVOKE ALL ON DATABASE {database} FROM PUBLIC",
            identifiers={"database": database},
        )
        if client_.public_can_connect(database):
            raise IntegrityException(
                f"Deployment {deployment.id}: PUBLIC still holds CONNECT on {database}"
            )

    monkeypatch.setattr(rs, "_revoke_public_access", revoke_without_set_role)
    with pytest.raises(IntegrityException) as exc:
        rs.ensure_database(session, deployment, client=client, settings=settings)
    assert "CONNECT" in str(exc.value)
    assert client.public_can_connect(rs.database_name(deployment)) is True


def test_session_limits_are_re_asserted_on_every_run(session, client, settings):
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    assert client.role_settings(credentials.user) == rs.ROLE_SETTINGS

    for name in rs.ROLE_SETTINGS:
        client.execute(f"ALTER ROLE {credentials.user} RESET {name}")
    assert client.role_settings(credentials.user) == {}

    rs.ensure_database(session, deployment, client=client, settings=settings)
    assert client.role_settings(credentials.user) == rs.ROLE_SETTINGS


def test_a_tenant_cannot_raise_its_own_temp_file_limit(session, client, settings):
    """temp_file_limit is enforcement, not advice."""
    credentials = rs.ensure_database(
        session, _deployment(session), client=client, settings=settings
    )
    with _connect_as_tenant(credentials) as conn:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("SET temp_file_limit = '10GB'")


# ── Teardown ──────────────────────────────────────────────────────────────


def test_teardown_revokes_access_and_destroys_nothing(session, client, settings):
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)

    rs.teardown_database(session, deployment, client=client, settings=settings)

    with pytest.raises(psycopg.OperationalError):
        _connect_as_tenant(credentials)
    # The data is still there, which is the entire point of the grace period.
    assert client.database_exists(credentials.database)
    record = rs.get_record(session, deployment)
    assert record.purge_after is not None


def test_teardown_is_idempotent_and_tolerates_no_database(session, client, settings):
    never_provisioned = _deployment(session)
    rs.teardown_database(session, never_provisioned, client=client, settings=settings)
    assert rs.get_record(session, never_provisioned) is None

    deployment = _deployment(session)
    rs.ensure_database(session, deployment, client=client, settings=settings)
    rs.teardown_database(session, deployment, client=client, settings=settings)
    first_deadline = rs.get_record(session, deployment).purge_after
    rs.teardown_database(session, deployment, client=client, settings=settings)
    # The deadline is not pushed out by a retried delete reconcile.
    assert rs.get_record(session, deployment).purge_after == first_deadline


def test_a_torn_down_deployment_is_not_resurrected_by_a_quota_sweep(
    session, client, settings
):
    """A sweep over a torn-down deployment's row must not restore LOGIN."""
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    rs.teardown_database(session, deployment, client=client, settings=settings)

    state = rs.evaluate_quota_state(session, deployment, client=client, settings=settings)

    assert state == rs.get_record(session, deployment).quota_state
    assert not client.fetchval(
        "SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (credentials.user,)
    )
    with pytest.raises(psycopg.OperationalError):
        _connect_as_tenant(credentials)


# ── The quota ladder ──────────────────────────────────────────────────────


def _evaluate_at(session, deployment, client, settings, *, percent: float, **kwargs) -> str:
    """Measure as though the database were `percent` of its allowance."""
    allowance = rs.resolve_quota_bytes(deployment)
    size = int(allowance * percent / 100)
    original = client.database_size_bytes
    client.database_size_bytes = lambda _name: size  # type: ignore[method-assign]
    try:
        return rs.evaluate_quota_state(
            session, deployment, client=client, settings=settings, **kwargs
        )
    finally:
        client.database_size_bytes = original  # type: ignore[method-assign]


def test_the_ladder_climbs_and_descends(session, client, settings):
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    db = credentials.database

    def read_only() -> bool:
        return "default_transaction_read_only=on" in "".join(
            f"{k}={v}" for k, v in client.database_settings(db).items()
        )

    def can_log_in() -> bool:
        return bool(client.fetchval(
            "SELECT rolcanlogin FROM pg_roles WHERE rolname = %s", (credentials.user,)
        ))

    assert _evaluate_at(session, deployment, client, settings, percent=10) == rs.QUOTA_OK
    assert not read_only() and can_log_in()

    assert _evaluate_at(session, deployment, client, settings, percent=85) == rs.QUOTA_WARNED
    assert not read_only() and can_log_in()

    assert _evaluate_at(session, deployment, client, settings, percent=95) == rs.QUOTA_WARNED

    assert _evaluate_at(session, deployment, client, settings, percent=100) == rs.QUOTA_READONLY
    assert read_only() and can_log_in()

    assert _evaluate_at(session, deployment, client, settings, percent=150) == rs.QUOTA_BLOCKED
    assert read_only() and not can_log_in()
    with pytest.raises(psycopg.OperationalError):
        _connect_as_tenant(credentials)

    # ... and back down, each step undoing exactly what it applied.
    assert _evaluate_at(session, deployment, client, settings, percent=120) == rs.QUOTA_READONLY
    assert read_only() and can_log_in()

    assert _evaluate_at(session, deployment, client, settings, percent=50) == rs.QUOTA_OK
    assert not read_only() and can_log_in()
    with _connect_as_tenant(credentials) as conn:
        conn.execute("CREATE TABLE writable_again (id int)")


def test_read_only_is_re_asserted_after_a_tenant_clears_it(session, client, settings):
    """The owner can clear read-only; the next evaluation puts it back."""
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    _evaluate_at(session, deployment, client, settings, percent=100)

    # Exactly what a determined tenant does, and what makes read-only soft: the
    # database default is overridden for this session, and then cleared for
    # good. Both statements succeed -- the owner is allowed to do this.
    with _connect_as_tenant(credentials, autocommit=True) as conn:
        conn.execute("SET default_transaction_read_only = off")
        conn.execute(f"ALTER DATABASE {credentials.database} RESET default_transaction_read_only")
    assert client.database_settings(credentials.database) == {}

    _evaluate_at(session, deployment, client, settings, percent=100)
    assert client.database_settings(credentials.database) == {
        "default_transaction_read_only": "on"
    }


def test_a_reconcile_does_not_grant_an_over_quota_tenant_a_write_window(
    session, client, settings
):
    """Redeploying must not clear read-only for a deployment still over."""
    deployment = _deployment(session)
    credentials = rs.ensure_database(session, deployment, client=client, settings=settings)
    _evaluate_at(session, deployment, client, settings, percent=110)
    assert rs.get_record(session, deployment).quota_state == rs.QUOTA_READONLY

    original = client.database_size_bytes
    client.database_size_bytes = lambda _n: int(rs.resolve_quota_bytes(deployment) * 1.1)
    try:
        rs.ensure_database(session, deployment, client=client, settings=settings)
    finally:
        client.database_size_bytes = original

    assert client.database_settings(credentials.database) == {
        "default_transaction_read_only": "on"
    }
    assert rs.get_record(session, deployment).quota_state == rs.QUOTA_READONLY


def test_measurements_and_thresholds_are_recorded(session, client, settings):
    deployment = _deployment(session)
    rs.ensure_database(session, deployment, client=client, settings=settings)

    _evaluate_at(session, deployment, client, settings, percent=85)
    record = rs.get_record(session, deployment)
    assert record.size_bytes == int(rs.resolve_quota_bytes(deployment) * 0.85)
    assert record.measured_at is not None
    assert record.warned_threshold == 80

    # Still above 80 but not yet 90: the threshold marker does not move, which
    # is what stops a hovering deployment being mailed on every sweep.
    _evaluate_at(session, deployment, client, settings, percent=87)
    assert rs.get_record(session, deployment).warned_threshold == 80

    _evaluate_at(session, deployment, client, settings, percent=92)
    assert rs.get_record(session, deployment).warned_threshold == 90

    _evaluate_at(session, deployment, client, settings, percent=100)
    record = rs.get_record(session, deployment)
    assert record.warned_threshold == 100
    assert record.readonly_at is not None

    # Dropping back to ok clears the suppression so the next climb is notified.
    _evaluate_at(session, deployment, client, settings, percent=10)
    record = rs.get_record(session, deployment)
    assert record.warned_threshold is None and record.warned_at is None


def test_a_reconcile_evaluation_records_no_threshold(session, client, settings):
    """`notify=False` must not consume the threshold either."""
    deployment = _deployment(session)
    rs.ensure_database(session, deployment, client=client, settings=settings)

    _evaluate_at(session, deployment, client, settings, percent=85, notify=False)
    record = rs.get_record(session, deployment)
    assert record.quota_state == rs.QUOTA_WARNED
    assert record.warned_threshold is None

    _evaluate_at(session, deployment, client, settings, percent=85)
    assert rs.get_record(session, deployment).warned_threshold == 80
