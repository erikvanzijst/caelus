from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import DeploymentReconcileJobORM
from app.services.errors import DeploymentInProgressException, NotFoundException
from app.services.reconcile_constants import (
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)

logger = logging.getLogger(__name__)


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

    def _claim_next_job_postgres(self, *, worker_id: str) -> DeploymentReconcileJobORM | None:
        """Claim the next runnable job using Postgres row locking with SKIP LOCKED."""
        now = datetime.now(UTC)
        # TODO: Write a more sophisticated query that groups by deployment_id, selects the deployment that has the
        #  oldest open job and then selects all live jobs for that deployment ordered by run_after, immediately marks
        #  all but the newest jobs as done, and then returns that newest job. This automatically eliminates redundant
        #  pending jobs that have already been superseded by a newer job.
        stmt = (
            select(DeploymentReconcileJobORM)
            .where(
                DeploymentReconcileJobORM.status == JOB_STATUS_QUEUED,
                DeploymentReconcileJobORM.run_after <= now,
            )
            .order_by(DeploymentReconcileJobORM.run_after, DeploymentReconcileJobORM.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = self._session.exec(stmt).first()
        if job is None:
            logger.debug("No runnable reconcile job available for worker_id=%s", worker_id)
            return None
        job.status = JOB_STATUS_RUNNING
        job.locked_by = worker_id
        job.locked_at = now
        job.updated_at = now
        self._session.add(job)
        self._session.commit()
        self._session.refresh(job)
        logger.info(
            "Claimed reconcile job id=%s deployment_id=%s worker_id=%s (postgres)",
            job.id,
            job.deployment_id,
            worker_id,
        )
        return job

    def _claim_next_job_sqlite(self, *, worker_id: str) -> DeploymentReconcileJobORM | None:
        """Claim the next runnable job atomically using SQLite UPDATE ... RETURNING fallback."""
        now = datetime.now(UTC)
        stmt = text(
            """
            UPDATE deployment_reconcile_job
            SET status = :running_status,
                locked_by = :worker_id,
                locked_at = :now_ts,
                updated_at = :now_ts
            WHERE id = (
                SELECT id
                FROM deployment_reconcile_job
                WHERE status = :queued_status
                  AND run_after <= :now_ts
                ORDER BY run_after, id
                LIMIT 1
            )
            RETURNING id
            """
        )
        row = self._session.execute(
            stmt,
            {
                "running_status": JOB_STATUS_RUNNING,
                "queued_status": JOB_STATUS_QUEUED,
                "worker_id": worker_id,
                "now_ts": now,
            },
        ).first()
        if row is None:
            self._session.commit()
            logger.debug("No runnable reconcile job available for worker_id=%s", worker_id)
            return None
        job_id = int(row[0])
        self._session.commit()
        job = self._session.get(DeploymentReconcileJobORM, job_id)
        if job is not None:
            logger.info(
                "Claimed reconcile job id=%s deployment_id=%s worker_id=%s (sqlite)",
                job.id,
                job.deployment_id,
                worker_id,
            )
        return job

    def claim_next_job(self, *, worker_id: str) -> DeploymentReconcileJobORM | None:
        """Claim one runnable job for a worker, using a dialect-appropriate strategy."""
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "sqlite":
            return self._claim_next_job_sqlite(worker_id=worker_id)
        return self._claim_next_job_postgres(worker_id=worker_id)

    def mark_job_done(self, *, job_id: int) -> DeploymentReconcileJobORM:
        """Mark a claimed job as done and clear lock/error state."""
        job = self._session.get(DeploymentReconcileJobORM, job_id)
        if job is None:
            raise NotFoundException("Job not found")
        job.status = JOB_STATUS_DONE
        job.last_error = None
        job.locked_by = None
        job.locked_at = None
        job.updated_at = datetime.now(UTC)
        self._session.add(job)
        self._session.commit()
        self._session.refresh(job)
        logger.info("Marked reconcile job id=%s as done", job_id)
        return job

    def mark_job_failed(self, *, job_id: int, error: str) -> DeploymentReconcileJobORM:
        """Mark a job as failed and persist the terminal error message."""
        job = self._session.get(DeploymentReconcileJobORM, job_id)
        if job is None:
            raise NotFoundException("Job not found")
        now = datetime.now(UTC)
        job.status = JOB_STATUS_FAILED
        job.last_error = error
        job.locked_by = None
        job.locked_at = None
        job.updated_at = now
        self._session.add(job)
        self._session.commit()
        self._session.refresh(job)
        logger.warning("Marked reconcile job id=%s as failed: %s", job_id, error)
        return job

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
