"""The database housekeeping worker: periodic sweeps over the tenant cluster.

One process, several ticks, each on its own cadence. The quota tick lives here;
the purge and orphan ticks join it later.

**Ticks share a process but not a `try`.** Purge performs the only irreversible
operation in this subsystem and a bug there must not stop quota enforcement, or
the reverse, so a tick that raises is logged and its neighbors still run.

No keyring verification at startup, unlike the API and `caelus worker`: every
tick connects as the platform admin and none of them decrypts a tenant password
(design D10).
"""

from __future__ import annotations

import logging
import os
import signal
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlmodel import Session, select

from app.config import CaelusSettings, get_settings
from app.db import session_scope
from app.models import DeploymentDatabaseORM, DeploymentORM
from app.services import relational_storage
from app.services.postgres_admin import PostgresAdminClient

logger = logging.getLogger(__name__)


@dataclass
class TickResult:
    """What one sweep did, for the operator watching the log."""

    name: str
    swept: int = 0
    changed: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)


def quota_tick(
    session: Session,
    *,
    tenant_db: PostgresAdminClient | None = None,
    settings: CaelusSettings | None = None,
) -> TickResult:
    """Measure every provisioned database and apply the state it lands in.

    One deployment's failure is recorded and skipped rather than abandoning the
    rest of the fleet.
    """
    settings = settings or get_settings()
    tenant_db = tenant_db or PostgresAdminClient.from_settings(settings)
    result = TickResult(name="quota")

    # Rows awaiting purge are deleted deployments; evaluating one would
    # re-assert the LOGIN its teardown removed.
    records = session.exec(
        select(DeploymentDatabaseORM).where(DeploymentDatabaseORM.purge_after.is_(None))
    ).all()

    for record in records:
        deployment = session.get(DeploymentORM, record.deployment_id)
        if deployment is None:
            continue
        previous = record.quota_state
        try:
            state = relational_storage.evaluate_quota_state(
                session,
                deployment,
                tenant_db=tenant_db,
                settings=settings,
                record=record,
            )
        except Exception as exc:
            logger.exception("Quota evaluation failed deployment_id=%s", deployment.id)
            result.failed[str(deployment.id)] = str(exc)
            session.rollback()
            continue
        result.swept += 1
        if state != previous:
            result.changed[str(deployment.id)] = f"{previous} -> {state}"

    # Every sweep, including the ones that change nothing: on a small fleet
    # that is the only evidence the process is alive and reaching the cluster.
    logger.info(
        "Quota sweep complete: swept=%s changed=%s failed=%s",
        result.swept,
        len(result.changed),
        len(result.failed),
    )
    return result


def run_ticks(ticks: list[Callable[[], TickResult]], *, emit: Any = None) -> list[TickResult]:
    """Run each tick, letting a failure in one stop only that one."""
    results: list[TickResult] = []
    for tick in ticks:
        try:
            result = tick()
        except Exception:
            logger.exception("Tick failed; continuing with the rest")
            continue
        results.append(result)
        if emit is not None and (result.swept or result.changed or result.failed):
            emit(
                {
                    "tick": result.name,
                    "swept": result.swept,
                    "changed": result.changed,
                    "failed": result.failed,
                }
            )
    return results


def run_db_worker(
    *,
    settings: CaelusSettings | None = None,
    tenant_db: PostgresAdminClient | None = None,
    emit: Any = None,
    max_passes: int | None = None,
) -> None:
    """Repeat the ticks until signalled.

    ``max_passes`` bounds the loop for tests; production leaves it unset.
    """
    settings = settings or get_settings()
    shutdown = False

    def _handle_signal(signum: int, frame: object) -> None:
        nonlocal shutdown
        shutdown = True
        logger.info("Caught signal %s, finishing pass then exiting (pid=%s)", signum, os.getpid())

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    interval = settings.db_worker_quota_interval_seconds
    logger.info("Database worker started: quota interval=%ss", interval)

    passes = 0
    while not shutdown:
        with session_scope() as session:
            run_ticks(
                [lambda: quota_tick(session, tenant_db=tenant_db, settings=settings)],
                emit=emit,
            )
        passes += 1
        if max_passes is not None and passes >= max_passes:
            break
        deadline = time.monotonic() + interval
        while not shutdown and time.monotonic() < deadline:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))

    logger.info("Database worker stopped after %s pass(es)", passes)
