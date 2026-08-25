"""Thin transport over the tenant PostgreSQL cluster's administrative surface.

Roles, databases, privileges and sessions; nothing about who they are for. The
per-deployment policy lives in ``relational_storage.py``.

Three things this module exists to encapsulate:

* `CREATE DATABASE` / `DROP DATABASE` are refused inside a transaction block.
* `SET ROLE` is session state, so owner-scoped statements need a session.
* Utility statements (`ALTER ROLE ... PASSWORD`, `ALTER ROLE ... SET`) accept no
  bound parameter, hence ``literals=`` alongside ``identifiers=``.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

import psycopg
from psycopg import sql

from app.config import CaelusSettings, get_settings
from app.services.errors import CaelusException

logger = logging.getLogger(__name__)

# Short enough that a reconcile fails inside its own budget, not the job lease.
CONNECT_TIMEOUT_SEC = 10


class PostgresAdminException(CaelusException):
    """A statement failed, or the tenant cluster is not configured."""


def _compose(
    statement: str,
    identifiers: Mapping[str, str] | None = None,
    literals: Mapping[str, Any] | None = None,
) -> sql.Composed | sql.SQL:
    """Fill `{name}` slots with quoted identifiers and literals; `%s` binds."""
    if not identifiers and not literals:
        return sql.SQL(statement)  # type: ignore[return-value]
    slots: dict[str, Any] = {
        key: sql.Identifier(value) for key, value in (identifiers or {}).items()
    }
    slots.update({key: sql.Literal(value) for key, value in (literals or {}).items()})
    return sql.SQL(statement).format(**slots)


class AdminSession:
    """One connection's worth of statements, in the order they were issued."""

    def __init__(self, connection: psycopg.Connection) -> None:
        self._connection = connection

    def execute(
        self,
        statement: str,
        params: Sequence[Any] | None = None,
        *,
        identifiers: Mapping[str, str] | None = None,
        literals: Mapping[str, Any] | None = None,
    ) -> None:
        self._connection.execute(_compose(statement, identifiers, literals), params)

    def fetchval(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        identifiers: Mapping[str, str] | None = None,
        literals: Mapping[str, Any] | None = None,
    ) -> Any:
        """The first column of the first row, or ``None`` when there is none."""
        row = self._connection.execute(_compose(query, identifiers, literals), params).fetchone()
        return None if row is None else row[0]

    def fetchcol(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        identifiers: Mapping[str, str] | None = None,
    ) -> list[Any]:
        """The first column of every row."""
        rows = self._connection.execute(_compose(query, identifiers), params).fetchall()
        return [row[0] for row in rows]

    @contextmanager
    def as_role(self, role: str) -> Iterator[AdminSession]:
        """Assume `role` for the statements inside the block."""
        self.execute("SET ROLE {role}", identifiers={"role": role})
        try:
            yield self
        finally:
            self.execute("RESET ROLE")


class PostgresAdminClient:
    """Administrative access to the tenant cluster, as a non-superuser role.

    Lookups answer ``None``/``False`` for "not there" rather than raising.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        maintenance_db: str,
        connect_timeout: int = CONNECT_TIMEOUT_SEC,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._maintenance_db = maintenance_db
        self._connect_timeout = connect_timeout

    @classmethod
    def from_settings(cls, settings: CaelusSettings | None = None) -> PostgresAdminClient:
        settings = settings or get_settings()
        missing = [
            name
            for name in ("tenant_db_host", "tenant_db_admin_user", "tenant_db_admin_password")
            if not getattr(settings, name)
        ]
        if missing:
            raise PostgresAdminException(
                "tenant PostgreSQL cluster is not configured: missing "
                + ", ".join(sorted(missing))
            )
        return cls(
            host=settings.tenant_db_host,
            port=settings.tenant_db_port,
            user=settings.tenant_db_admin_user,
            password=settings.tenant_db_admin_password,
            maintenance_db=settings.tenant_db_maintenance_db,
        )

    # --- transport ---------------------------------------------------------

    @contextmanager
    def _connect(self, *, dbname: str | None = None, autocommit: bool = False):
        """One connection, closed on the way out, failures wrapped."""
        try:
            connection = psycopg.connect(
                host=self._host,
                port=self._port,
                user=self._user,
                password=self._password,
                dbname=dbname or self._maintenance_db,
                connect_timeout=self._connect_timeout,
                autocommit=autocommit,
            )
        except psycopg.Error as exc:
            raise PostgresAdminException(
                f"cannot reach the tenant PostgreSQL cluster at {self._host}:{self._port}: {exc}"
            ) from exc
        try:
            with connection:
                yield connection
        except psycopg.Error as exc:
            raise PostgresAdminException(str(exc)) from exc
        finally:
            connection.close()

    @contextmanager
    def session(
        self, *, dbname: str | None = None, autocommit: bool = False
    ) -> Iterator[AdminSession]:
        """A session's worth of statements on one connection.

        Transactional by default. ``autocommit=True`` for sequences containing
        `CREATE DATABASE` / `DROP DATABASE`; `SET ROLE` holds across either.
        """
        with self._connect(dbname=dbname, autocommit=autocommit) as connection:
            yield AdminSession(connection)

    def execute(
        self,
        statement: str,
        params: Sequence[Any] | None = None,
        *,
        identifiers: Mapping[str, str] | None = None,
        literals: Mapping[str, Any] | None = None,
        dbname: str | None = None,
    ) -> None:
        with self.session(dbname=dbname) as session:
            session.execute(statement, params, identifiers=identifiers, literals=literals)

    def fetchval(
        self,
        query: str,
        params: Sequence[Any] | None = None,
        *,
        identifiers: Mapping[str, str] | None = None,
        dbname: str | None = None,
    ) -> Any:
        with self.session(dbname=dbname) as session:
            return session.fetchval(query, params, identifiers=identifiers)

    def execute_autocommit(
        self,
        statement: str,
        *,
        identifiers: Mapping[str, str] | None = None,
    ) -> None:
        """Run a statement PostgreSQL refuses inside a transaction block.

        An owner-scoped drop needs `session(autocommit=True)` + `as_role`.
        """
        with self.session(autocommit=True) as session:
            session.execute(statement, identifiers=identifiers)

    # --- catalog lookups ---------------------------------------------------

    def role_exists(self, name: str) -> bool:
        return bool(self.fetchval("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)))

    def database_exists(self, name: str) -> bool:
        return bool(self.fetchval("SELECT 1 FROM pg_database WHERE datname = %s", (name,)))

    def public_can_connect(self, name: str) -> bool:
        """Whether `PUBLIC` still holds CONNECT; readable without CONNECT."""
        return bool(
            self.fetchval("SELECT has_database_privilege('public', %s, 'CONNECT')", (name,))
        )

    def database_size_bytes(self, name: str) -> int:
        """Logical size; needs `pg_read_all_stats`, not CONNECT."""
        return int(self.fetchval("SELECT pg_database_size(%s)", (name,)) or 0)

    def role_settings(self, name: str) -> dict[str, str]:
        """The role's `ALTER ROLE ... SET` values, as a mapping."""
        raw = self.fetchval(
            "SELECT setconfig FROM pg_db_role_setting s "
            "JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname = %s AND s.setdatabase = 0",
            (name,),
        )
        return dict(item.split("=", 1) for item in (raw or []))

    def database_settings(self, name: str) -> dict[str, str]:
        """The database's `ALTER DATABASE ... SET` values, as a mapping."""
        raw = self.fetchval(
            "SELECT setconfig FROM pg_db_role_setting s "
            "JOIN pg_database d ON d.oid = s.setdatabase WHERE d.datname = %s AND s.setrole = 0",
            (name,),
        )
        return dict(item.split("=", 1) for item in (raw or []))

    def backend_pids(self, role: str) -> list[int]:
        with self.session() as session:
            return session.fetchcol(
                "SELECT pid FROM pg_stat_activity "
                "WHERE usename = %s AND pid <> pg_backend_pid()",
                (role,),
            )

    def terminate_backends(self, role: str) -> int:
        """Close a role's server connections; needs `pg_signal_backend`."""
        terminated = self.fetchval(
            "SELECT count(*) FROM ("
            "  SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
            "   WHERE usename = %s AND pid <> pg_backend_pid()"
            ") t",
            (role,),
        )
        return int(terminated or 0)
