"""Per-deployment relational storage: policy on top of the tenant cluster.

Naming, allowances, provisioning order, teardown and quota state; the transport
it sits on is ``postgres_admin.py``.

Mirrors ``object_storage.py`` and diverges in one place: PostgreSQL keeps only a
SCRAM verifier, so the platform holds the password itself -- encrypted under the
var keyring, and written down before it is applied.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.config import CaelusSettings, get_settings
from app.models import DeploymentDatabaseORM, DeploymentORM
from app.services import var_crypto
from app.services.errors import IntegrityException
from app.services.postgres_admin import PostgresAdminClient

logger = logging.getLogger(__name__)

NAME_PREFIX = "dpl_"

# Re-applied on every provision, so a tenant's `RESET` does not survive one.
ROLE_SETTINGS: dict[str, str] = {
    "temp_file_limit": "64MB",
    "statement_timeout": "30s",
    "idle_in_transaction_session_timeout": "60s",
}

# Percentages of the plan's allowance (design D8).
WARN_THRESHOLDS: tuple[int, ...] = (80, 90)
READONLY_THRESHOLD = 100
BLOCK_THRESHOLD = 150

QUOTA_OK = "ok"
QUOTA_WARNED = "warned"
QUOTA_READONLY = "readonly"
QUOTA_BLOCKED = "blocked"

PASSWORD_BYTES = 24


@dataclass(frozen=True)
class DatabaseCredentials:
    """What a provisioned deployment needs to reach its database.

    Host and port are the pooler's, never the server's.
    """

    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def url(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
        )


def is_enabled(deployment: DeploymentORM) -> bool:
    """Whether this deployment's product opts into relational storage.

    Read from the template's system values, never from tenant-controlled user
    values and never from merged values.
    """
    template = deployment.desired_template
    if template is None:
        return False
    storage = (template.system_values_json or {}).get("relationalStorage")
    return bool(isinstance(storage, dict) and storage.get("enabled"))


def database_name(deployment: DeploymentORM) -> str:
    return f"{NAME_PREFIX}{deployment.id.hex}"


def role_name(deployment: DeploymentORM) -> str:
    """The same string as the database's."""
    return database_name(deployment)


def resolve_quota_bytes(deployment: DeploymentORM) -> int:
    """The deployment's database allowance, from its plan. Fail-closed."""
    subscription = deployment.subscription
    if subscription is None or subscription.plan_template is None:
        raise IntegrityException(
            f"Deployment {deployment.id} has relational storage enabled but no subscription, "
            "so no database allowance can be resolved"
        )
    database_bytes = subscription.plan_template.database_bytes
    if not database_bytes or database_bytes <= 0:
        raise IntegrityException(
            f"Deployment {deployment.id} has relational storage enabled but its plan declares "
            "no database allowance; refusing to provision an unbounded database"
        )
    return int(database_bytes)


def get_record(session: Session, deployment: DeploymentORM) -> DeploymentDatabaseORM | None:
    """This deployment's row, or ``None`` -- which is the unprovisioned state."""
    return session.exec(
        select(DeploymentDatabaseORM).where(
            DeploymentDatabaseORM.deployment_id == deployment.id
        )
    ).one_or_none()


def _tenant_db_client(
    tenant_db: PostgresAdminClient | None, settings: CaelusSettings | None
) -> tuple[PostgresAdminClient, CaelusSettings]:
    settings = settings or get_settings()
    return tenant_db or PostgresAdminClient.from_settings(settings), settings


def _store_password(
    session: Session,
    deployment: DeploymentORM,
    record: DeploymentDatabaseORM | None,
) -> tuple[DeploymentDatabaseORM, str]:
    """Persist the row and its encrypted password, returning the plaintext.

    Committed here, applied to the role by the caller, in that order (D4). An
    existing row's password is reused rather than rotated.
    """
    if record is not None:
        return record, var_crypto.decrypt(record.password_encrypted, record.key_id)

    password = secrets.token_hex(PASSWORD_BYTES)
    ciphertext, key_id = var_crypto.encrypt(password)
    record = DeploymentDatabaseORM(
        deployment_id=deployment.id,
        db_name=database_name(deployment),
        role_name=role_name(deployment),
        password_encrypted=ciphertext,
        key_id=key_id,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record, password


def ensure_database(
    session: Session,
    deployment: DeploymentORM,
    *,
    tenant_db: PostgresAdminClient | None = None,
    settings: CaelusSettings | None = None,
) -> DatabaseCredentials:
    """Provision (or repair) this deployment's role, database and limits.

    Each step reads before it writes and is verified independently, so an
    interrupted run is finished by the next one (design D6).
    """
    tenant_db, settings = _tenant_db_client(tenant_db, settings)

    # Before anything is created, so a bad plan leaves nothing behind.
    quota_bytes = resolve_quota_bytes(deployment)
    role = role_name(deployment)
    database = database_name(deployment)

    record, password = _store_password(session, deployment, get_record(session, deployment))

    if not tenant_db.role_exists(role):
        tenant_db.execute(
            "CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOREPLICATION NOBYPASSRLS",
            identifiers={"role": role},
        )
        logger.info("Created database role deployment_id=%s role=%s", deployment.id, role)

    # CREATEROLE confers admin_option but not set_option, and without SET the
    # admin can neither create a database owned by this role nor act on one.
    tenant_db.execute(
        "GRANT {role} TO {admin} WITH SET TRUE, INHERIT FALSE",
        identifiers={"role": role, "admin": settings.tenant_db_admin_user},
    )

    tenant_db.execute(
        "ALTER ROLE {role} WITH PASSWORD {password}",
        identifiers={"role": role},
        literals={"password": password},
    )

    # Checked on its own rather than inferred from the role's existence.
    if not tenant_db.database_exists(database):
        tenant_db.execute_autocommit(
            "CREATE DATABASE {database} OWNER {role}",
            identifiers={"database": database, "role": role},
        )
        logger.info(
            "Created tenant database deployment_id=%s database=%s", deployment.id, database
        )

    _revoke_public_access(tenant_db, database=database, role=role, deployment=deployment)

    for name, value in ROLE_SETTINGS.items():
        tenant_db.execute(
            f"ALTER ROLE {{role}} SET {name} = {{value}}",
            identifiers={"role": role},
            literals={"value": value},
        )

    # A reconcile must not mail anyone; the housekeeping worker does that.
    evaluate_quota_state(
        session, deployment, tenant_db=tenant_db, settings=settings, notify=False, record=record
    )

    logger.info(
        "Ensured tenant database deployment_id=%s database=%s quota_bytes=%s",
        deployment.id,
        database,
        quota_bytes,
    )
    return DatabaseCredentials(
        host=settings.tenant_db_pooler_host,
        port=settings.tenant_db_pooler_port,
        database=database,
        user=role,
        password=password,
    )


def _revoke_public_access(
    tenant_db: PostgresAdminClient,
    *,
    database: str,
    role: str,
    deployment: DeploymentORM,
) -> None:
    """Take PUBLIC's access away from a tenant database, and prove it worked.

    Owner-scoped, so it runs under `SET ROLE`; read back afterwards because a
    revoke that is not owner-scoped warns rather than failing (design D6 5b).
    """
    with tenant_db.session() as tenant_session:
        with tenant_session.as_role(role):
            tenant_session.execute(
                "REVOKE ALL ON DATABASE {database} FROM PUBLIC",
                identifiers={"database": database},
            )

    if tenant_db.public_can_connect(database):
        raise IntegrityException(
            f"Deployment {deployment.id}: PUBLIC still holds CONNECT on {database} after "
            "the revocation; refusing to report a provisioned database that every other "
            "role can reach"
        )


def teardown_database(
    session: Session,
    deployment: DeploymentORM,
    *,
    tenant_db: PostgresAdminClient | None = None,
    settings: CaelusSettings | None = None,
) -> None:
    """Revoke the role's login and record when the data may be destroyed.

    Drops nothing. Idempotent, and a no-op for a deployment that never had a
    database.
    """
    tenant_db, settings = _tenant_db_client(tenant_db, settings)

    record = get_record(session, deployment)
    if record is None:
        return

    if tenant_db.role_exists(record.role_name):
        tenant_db.execute("ALTER ROLE {role} NOLOGIN", identifiers={"role": record.role_name})
        tenant_db.terminate_backends(record.role_name)

    if record.purge_after is None:
        record.purge_after = _utcnow() + timedelta(
            days=settings.deployment_database_purge_grace_days
        )
        session.add(record)
        session.commit()

    logger.info(
        "Revoked tenant database access deployment_id=%s database=%s purge_after=%s",
        deployment.id,
        record.db_name,
        record.purge_after,
    )


def _utcnow() -> datetime:
    """Naive UTC, matching the schema's timestamp columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def _state_for(percent: float) -> str:
    if percent >= BLOCK_THRESHOLD:
        return QUOTA_BLOCKED
    if percent >= READONLY_THRESHOLD:
        return QUOTA_READONLY
    if percent >= WARN_THRESHOLDS[0]:
        return QUOTA_WARNED
    return QUOTA_OK


def _crossed_threshold(percent: float) -> int | None:
    """The highest notifiable threshold this measurement is at or above."""
    for threshold in (READONLY_THRESHOLD, *reversed(WARN_THRESHOLDS)):
        if percent >= threshold:
            return threshold
    return None


def evaluate_quota_state(
    session: Session,
    deployment: DeploymentORM,
    *,
    tenant_db: PostgresAdminClient | None = None,
    settings: CaelusSettings | None = None,
    notify: bool = True,
    record: DeploymentDatabaseORM | None = None,
) -> str:
    """Measure this deployment's database and apply the state it lands in.

    Shared by the reconcile (`notify=False`) and the quota tick, so read-only is
    re-asserted rather than cleared.
    """
    tenant_db, settings = _tenant_db_client(tenant_db, settings)
    record = record or get_record(session, deployment)
    if record is None:
        raise IntegrityException(
            f"Deployment {deployment.id} has no provisioned database to evaluate"
        )

    if record.purge_after is not None:
        # The branch below re-asserts LOGIN, which would undo a teardown.
        return record.quota_state

    allowance = resolve_quota_bytes(deployment)
    size_bytes = tenant_db.database_size_bytes(record.db_name)
    percent = size_bytes * 100 / allowance
    state = _state_for(percent)
    previous = record.quota_state

    _apply_quota_state(tenant_db, record=record, state=state)

    now = _utcnow()
    record.size_bytes = size_bytes
    record.measured_at = now
    record.quota_state = state
    if state == QUOTA_READONLY and previous != QUOTA_READONLY:
        record.readonly_at = now
    if state == QUOTA_BLOCKED and previous != QUOTA_BLOCKED:
        record.blocked_at = now
    if state == QUOTA_OK:
        # Clear the suppression so the next climb is notified again.
        record.warned_threshold = None
        record.warned_at = None
    elif notify:
        threshold = _crossed_threshold(percent)
        if threshold is not None and threshold != record.warned_threshold:
            record.warned_threshold = threshold
            record.warned_at = now

    session.add(record)
    session.commit()

    if state != previous:
        logger.info(
            "Quota state changed deployment_id=%s database=%s %s -> %s size_bytes=%s "
            "allowance_bytes=%s",
            deployment.id,
            record.db_name,
            previous,
            state,
            size_bytes,
            allowance,
        )
    return state


def _apply_quota_state(
    tenant_db: PostgresAdminClient, *, record: DeploymentDatabaseORM, state: str
) -> None:
    """Make the cluster agree with the state just derived, on every call."""
    read_only = state in (QUOTA_READONLY, QUOTA_BLOCKED)

    with tenant_db.session() as tenant_session:
        with tenant_session.as_role(record.role_name):
            if read_only:
                tenant_session.execute(
                    "ALTER DATABASE {database} SET default_transaction_read_only = on",
                    identifiers={"database": record.db_name},
                )
            else:
                tenant_session.execute(
                    "ALTER DATABASE {database} RESET default_transaction_read_only",
                    identifiers={"database": record.db_name},
                )

    if state == QUOTA_BLOCKED:
        tenant_db.execute("ALTER ROLE {role} NOLOGIN", identifiers={"role": record.role_name})
        # NOLOGIN alone leaves already-authenticated pooler connections usable.
        tenant_db.terminate_backends(record.role_name)
    else:
        tenant_db.execute("ALTER ROLE {role} LOGIN", identifiers={"role": record.role_name})
