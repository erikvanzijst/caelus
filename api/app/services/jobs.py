from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from uuid import UUID

from sqlalchemy import DateTime, and_, bindparam, or_, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import Session, select

from app.config import get_settings
from app.models import DeploymentReconcileJobORM
from app.services.errors import DeploymentInProgressException, NotFoundException
from app.services.reconcile_constants import (
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)

logger = logging.getLogger(__name__)

# Claimable-job predicate for the raw SQLite path, kept as a single string so
# the pre-read and the claiming UPDATE below cannot drift apart. Mirrors
# ``JobService._claimable_clause()``.
_SQLITE_CLAIMABLE_PREDICATE = """
                     (status = :queued_status AND run_after <= :now_ts)
                  OR (
                        status = :running_status
                        AND (locked_at IS NULL OR locked_at < :lease_cutoff_ts)
                     )
"""


class JobService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue_job(
        self,
        *,
        deployment_id: UUID,
        reason: str,
        run_after: datetime | None = None,
    ) -> DeploymentReconcileJobORM:
        """Create a queued reconcile job for a deployment in the current transaction."""
        job = DeploymentReconcileJobORM(
            deployment_id=deployment_id,
            reason=reason,
            run_after=run_after or datetime.now(UTC),
            status=JOB_STATUS_QUEUED,
        )
        try:
            self._session.add(job)
            self._session.flush()
            logger.info(
                "Enqueued reconcile job id=%s deployment_id=%s reason=%s run_after=%s",
                job.id,
                deployment_id,
                reason,
                job.run_after,
            )
        except IntegrityError as exc:
            logger.warning(
                "Duplicate in-progress job for deployment_id=%s; rejecting enqueue",
                deployment_id,
            )
            raise DeploymentInProgressException(
                "A deployment job is already queued or running"
            ) from exc
        return job

    def list_jobs(
        self,
        *,
        statuses: list[str] | None = None,
        deployment_id: UUID | None = None,
        limit: int = 100,
    ) -> list[DeploymentReconcileJobORM]:
        """List reconcile jobs with optional status/deployment filters."""
        stmt = select(DeploymentReconcileJobORM)
        if statuses:
            stmt = stmt.where(DeploymentReconcileJobORM.status.in_(statuses))
        if deployment_id is not None:
            stmt = stmt.where(DeploymentReconcileJobORM.deployment_id == deployment_id)
        stmt = stmt.order_by(DeploymentReconcileJobORM.run_after, DeploymentReconcileJobORM.id).limit(limit)
        return list(self._session.exec(stmt).all())

    @staticmethod
    def lease_interval() -> timedelta:
        """Return how long a worker may hold a claimed job before it is stealable."""
        return timedelta(seconds=get_settings().reconcile_job_lease_seconds)

    @classmethod
    def _claimable_clause(cls, *, now: datetime, lease_cutoff: datetime) -> ColumnElement[bool]:
        """Build the predicate selecting jobs a worker may claim right now.

        A job is claimable when it is queued and due, or when it is still marked
        running but its lease has expired — the latter is how work stranded by a
        worker that died mid-reconcile (pod restart, OOM kill, eviction) gets
        picked back up instead of pinning its deployment in provisioning/deleting
        forever. A running job with no ``locked_at`` at all can only come from a
        corrupted write, and is likewise treated as expired rather than stranded.
        """
        return or_(
            and_(
                DeploymentReconcileJobORM.status == JOB_STATUS_QUEUED,
                DeploymentReconcileJobORM.run_after <= now,
            ),
            and_(
                DeploymentReconcileJobORM.status == JOB_STATUS_RUNNING,
                or_(
                    DeploymentReconcileJobORM.locked_at.is_(None),
                    DeploymentReconcileJobORM.locked_at < lease_cutoff,
                ),
            ),
        )

    def _log_claim(
        self,
        job: DeploymentReconcileJobORM,
        *,
        worker_id: str,
        dialect: str,
        reclaimed: bool,
        previous_locked_by: str | None = None,
        previous_locked_at: datetime | None = None,
    ) -> None:
        """Log a claim, distinguishing a normal claim from an expired-lease steal."""
        if reclaimed:
            logger.warning(
                "Reclaimed expired reconcile job lease id=%s deployment_id=%s worker_id=%s "
                "attempt=%s previous_locked_by=%s previous_locked_at=%s lease_seconds=%s (%s)",
                job.id,
                job.deployment_id,
                worker_id,
                job.attempt,
                previous_locked_by,
                previous_locked_at,
                int(self.lease_interval().total_seconds()),
                dialect,
            )
        else:
            logger.info(
                "Claimed reconcile job id=%s deployment_id=%s worker_id=%s (%s)",
                job.id,
                job.deployment_id,
                worker_id,
                dialect,
            )

    def _claim_next_job_postgres(self, *, worker_id: str) -> DeploymentReconcileJobORM | None:
        """Claim the next runnable job using Postgres row locking with SKIP LOCKED."""
        now = datetime.now(UTC)
        lease_cutoff = now - self.lease_interval()
        # TODO: Write a more sophisticated query that groups by deployment_id, selects the deployment that has the
        #  oldest open job and then selects all live jobs for that deployment ordered by run_after, immediately marks
        #  all but the newest jobs as done, and then returns that newest job. This automatically eliminates redundant
        #  pending jobs that have already been superseded by a newer job.
        stmt = (
            select(DeploymentReconcileJobORM)
            .where(self._claimable_clause(now=now, lease_cutoff=lease_cutoff))
            .order_by(DeploymentReconcileJobORM.run_after, DeploymentReconcileJobORM.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = self._session.exec(stmt).first()
        if job is None:
            # logger.debug("No runnable reconcile job available for worker_id=%s", worker_id)
            return None
        # The row is held under FOR UPDATE until the commit below, so reading the
        # outgoing lock here and overwriting it is still a single atomic claim.
        reclaimed = job.status == JOB_STATUS_RUNNING
        previous_locked_by = job.locked_by
        previous_locked_at = job.locked_at
        job.status = JOB_STATUS_RUNNING
        job.locked_by = worker_id
        job.locked_at = now
        job.updated_at = now
        if reclaimed:
            job.attempt += 1
        self._session.add(job)
        self._session.commit()
        self._session.refresh(job)
        self._log_claim(
            job,
            worker_id=worker_id,
            dialect="postgres",
            reclaimed=reclaimed,
            previous_locked_by=previous_locked_by,
            previous_locked_at=previous_locked_at,
        )
        return job

    def _claim_next_job_sqlite(self, *, worker_id: str) -> DeploymentReconcileJobORM | None:
        """Claim the next runnable job atomically using SQLite UPDATE ... RETURNING fallback."""
        now = datetime.now(UTC)
        lease_cutoff = now - self.lease_interval()
        params = {
            "running_status": JOB_STATUS_RUNNING,
            "queued_status": JOB_STATUS_QUEUED,
            "worker_id": worker_id,
            "now_ts": now,
            "lease_cutoff_ts": lease_cutoff,
        }
        # Advisory pre-read: SQLite's RETURNING reports post-update values, so the
        # lock we are about to overwrite has to be read before the UPDATE runs if
        # the reclaim log line is to name the dead worker. This read never decides
        # anything — the UPDATE below re-evaluates the same predicate in its own
        # subquery and remains the sole, atomic claim — its result is only trusted
        # for logging when it agrees with the row the UPDATE actually took.
        previous = self._session.execute(
            text(
                f"""
                SELECT id, status, locked_by, locked_at
                FROM deployment_reconcile_job
                WHERE {_SQLITE_CLAIMABLE_PREDICATE}
                ORDER BY run_after, id
                LIMIT 1
                """
            ).bindparams(
                bindparam("now_ts", type_=DateTime),
                bindparam("lease_cutoff_ts", type_=DateTime),
            ),
            params,
        ).first()
        stmt = text(
            f"""
            UPDATE deployment_reconcile_job
            SET status = :running_status,
                locked_by = :worker_id,
                locked_at = :now_ts,
                updated_at = :now_ts,
                attempt = attempt + CASE WHEN status = :running_status THEN 1 ELSE 0 END
            WHERE id = (
                SELECT id
                FROM deployment_reconcile_job
                WHERE {_SQLITE_CLAIMABLE_PREDICATE}
                ORDER BY run_after, id
                LIMIT 1
            )
            RETURNING id
            """
        ).bindparams(
            bindparam("now_ts", type_=DateTime),
            bindparam("lease_cutoff_ts", type_=DateTime),
        )
        row = self._session.execute(stmt, params).first()
        if row is None:
            self._session.commit()
            # logger.debug("No runnable reconcile job available for worker_id=%s", worker_id)
            return None
        job_id = int(row[0])
        self._session.commit()
        job = self._session.get(DeploymentReconcileJobORM, job_id)
        if job is not None:
            matched = previous is not None and int(previous[0]) == job_id
            reclaimed = matched and previous[1] == JOB_STATUS_RUNNING
            self._log_claim(
                job,
                worker_id=worker_id,
                dialect="sqlite",
                reclaimed=reclaimed,
                previous_locked_by=previous[2] if matched else None,
                previous_locked_at=previous[3] if matched else None,
            )
        return job

    def claim_next_job(self, *, worker_id: str) -> DeploymentReconcileJobORM | None:
        """Claim one runnable job for a worker, using a dialect-appropriate strategy."""
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "sqlite":
            return self._claim_next_job_sqlite(worker_id=worker_id)
        return self._claim_next_job_postgres(worker_id=worker_id)

    def _complete_job(
        self,
        *,
        job_id: int,
        status: str,
        error: str | None,
        worker_id: str | None,
    ) -> DeploymentReconcileJobORM:
        """Move a claimed job to a terminal state, optionally only if still owned.

        When ``worker_id`` is given the write is conditional on the job still
        being leased to that worker. A worker that was merely wedged rather than
        dead (paused process, network partition) can wake up after its lease has
        been reclaimed and try to report a result for a job somebody else now
        owns; the ``locked_by`` predicate is carried in the UPDATE itself, so the
        stale worker either wins the row or writes nothing at all. Callers that
        pass no ``worker_id`` (tests, CLI/admin paths) keep the unconditional
        behavior.
        """
        job = self._session.get(DeploymentReconcileJobORM, job_id)
        if job is None:
            raise NotFoundException("Job not found")
        now = datetime.now(UTC)
        stmt = (
            update(DeploymentReconcileJobORM)
            .where(DeploymentReconcileJobORM.id == job_id)
            .values(
                status=status,
                last_error=error,
                locked_by=None,
                locked_at=None,
                updated_at=now,
            )
        )
        if worker_id is not None:
            stmt = stmt.where(DeploymentReconcileJobORM.locked_by == worker_id)
        result = self._session.execute(stmt, execution_options={"synchronize_session": False})
        applied = result.rowcount == 1
        self._session.commit()
        self._session.refresh(job)
        if not applied:
            logger.warning(
                "Refusing to mark reconcile job id=%s as %s for worker_id=%s: lease is no "
                "longer held by this worker (locked_by=%s locked_at=%s status=%s)",
                job_id,
                status,
                worker_id,
                job.locked_by,
                job.locked_at,
                job.status,
            )
        elif status == JOB_STATUS_FAILED:
            logger.warning("Marked reconcile job id=%s as failed: %s", job_id, error)
        else:
            logger.info("Marked reconcile job id=%s as done", job_id)
        return job

    def mark_job_done(
        self, *, job_id: int, worker_id: str | None = None
    ) -> DeploymentReconcileJobORM:
        """Mark a claimed job as done and clear lock/error state."""
        return self._complete_job(
            job_id=job_id, status=JOB_STATUS_DONE, error=None, worker_id=worker_id
        )

    def mark_job_failed(
        self, *, job_id: int, error: str, worker_id: str | None = None
    ) -> DeploymentReconcileJobORM:
        """Mark a job as failed and persist the terminal error message."""
        return self._complete_job(
            job_id=job_id, status=JOB_STATUS_FAILED, error=error, worker_id=worker_id
        )

    def dedupe_open_jobs(self, *, deployment_id: UUID) -> int:
        """Remove duplicate open jobs for a deployment, keeping the earliest one."""
        jobs = list(
            self._session.exec(
                select(DeploymentReconcileJobORM)
                .where(
                    DeploymentReconcileJobORM.deployment_id == deployment_id,
                    DeploymentReconcileJobORM.status.in_((JOB_STATUS_QUEUED, JOB_STATUS_RUNNING)),
                )
                .order_by(DeploymentReconcileJobORM.id)
            ).all()
        )
        if len(jobs) <= 1:
            return 0
        for duplicate in jobs[1:]:
            self._session.delete(duplicate)
        self._session.commit()
        logger.info(
            "Removed duplicate open reconcile jobs for deployment_id=%s removed=%s",
            deployment_id,
            len(jobs) - 1,
        )
        return len(jobs) - 1
