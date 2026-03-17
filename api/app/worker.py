from __future__ import annotations

import logging
import multiprocessing
import os
import signal
import time

from app.db import session_scope
from app.services import (
    reconcile as reconcile_service,
    jobs as jobs_service,
)
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_ERROR,
    JOB_STATUS_DONE,
    JOB_STATUS_FAILED,
)

logger = logging.getLogger(__name__)


def process_one_job(base_worker_id: str) -> dict | None:
    """Claim and process a single job.

    Each call opens its own database session so it is safe to run in a
    subprocess.  Returns a result dict on success/failure, or ``None`` when
    no job was available.
    """
    effective_worker_id = f"{base_worker_id}-{os.getpid()}"
    with session_scope() as session:
        jobs = jobs_service.JobService(session)
        claimed = jobs.claim_next_job(worker_id=effective_worker_id)
        if claimed is None:
            return None

        # Capture claim metadata before mark_done/mark_failed clears it
        job_id = claimed.id
        deployment_id = claimed.deployment_id
        reason = claimed.reason
        locked_by = claimed.locked_by
        locked_at = claimed.locked_at

        reconciler = reconcile_service.DeploymentReconciler(session=session)
        result = reconciler.reconcile(deployment_id)

        status: str
        last_error: str | None = result.last_error
        if result.status == DEPLOYMENT_STATUS_ERROR:
            jobs.mark_job_failed(job_id=job_id, error=result.last_error or "unknown error")
            status = JOB_STATUS_FAILED
        else:
            jobs.mark_job_done(job_id=job_id)
            status = JOB_STATUS_DONE

        return {
            "id": job_id,
            "deployment_id": deployment_id,
            "reason": reason,
            "status": status,
            "locked_by": locked_by,
            "locked_at": locked_at,
            "last_error": last_error,
        }


def _worker_loop(
    base_worker_id: str, result_queue: multiprocessing.Queue, poll_seconds: float
) -> None:
    """Run in a worker process. Claims and processes jobs until signaled."""
    shutdown = False

    def _handle_signal(signum: int, frame: object) -> None:
        nonlocal shutdown
        shutdown = True
        logger.info(f"Caught signal {signum}, shutting down worker process {os.getpid()}")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not shutdown:
        payload = process_one_job(base_worker_id)
        if payload is None:
            time.sleep(poll_seconds)
        else:
            result_queue.put(payload)

    # Sentinel: tell the master this worker is done
    result_queue.put(None)


def run_worker(
    *, base_worker_id: str, concurrency: int, poll_seconds: float, emit: callable
) -> None:
    """Spawn worker processes and collect results.

    ``emit`` is called with each completed job result dict (used by the CLI
    to print YAML output).
    """
    result_queue: multiprocessing.Queue = multiprocessing.Queue()
    workers = []
    for _ in range(concurrency):
        p = multiprocessing.Process(
            target=_worker_loop,
            args=(base_worker_id, result_queue, poll_seconds),
        )
        p.start()
        workers.append(p)

    def _handle_signal(signum: int, frame: object) -> None:
        logger.info(f"Master caught signal {signum} in master process {os.getpid()} -- waiting for workers to exit")

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # Master: read results until all workers have exited
    exited = 0
    while exited < concurrency:
        result = result_queue.get()
        if result is None:
            exited += 1
        else:
            emit(result)
    logger.info(f"All workers exited, shutting down master process {os.getpid()}")

    for p in workers:
        p.join()
