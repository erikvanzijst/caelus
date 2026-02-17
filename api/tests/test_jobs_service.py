from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from app.models import DeploymentReconcileJobORM
from app.services import deployments, jobs, products, templates, users
from app.services.errors import DeploymentInProgressException, NotFoundException


def _seed_deployment(db_session):
    user = users.create_user(db_session, payload=users.UserCreate(email="jobs-user@example.com"))
    product = products.create_product(
        db_session,
        payload=products.ProductCreate(name="jobs-product", description="jobs desc"),
    )
    template = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="oci://example/chart",
            chart_version="1.0.0",
        ),
    )
    deployment = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,
            desired_template_id=template.id,
            domainname="jobs.example.test",
        ),
    )
    return deployment.id


def _first_open_job_id(db_session, deployment_id: int) -> int:
    job = db_session.exec(
        select(DeploymentReconcileJobORM)
        .where(
            DeploymentReconcileJobORM.deployment_id == deployment_id,
            DeploymentReconcileJobORM.status.in_(("queued", "running")),
        )
        .order_by(DeploymentReconcileJobORM.id)
    ).first()
    assert job is not None
    return job.id


def test_enqueue_and_list_jobs_with_filters(db_session):
    deployment_id = _seed_deployment(db_session)
    jobs.mark_job_done(db_session, job_id=_first_open_job_id(db_session, deployment_id))

    first = jobs.enqueue_job(db_session, deployment_id=deployment_id, reason="update")
    jobs.mark_job_done(db_session, job_id=first.id)
    second = jobs.enqueue_job(
        db_session,
        deployment_id=deployment_id,
        reason="retry",
        run_after=datetime.utcnow() + timedelta(seconds=60),
    )

    listed_all = jobs.list_jobs(db_session, deployment_id=deployment_id, limit=20)
    assert len(listed_all) >= 3
    assert any(job.id == first.id for job in listed_all)
    assert any(job.id == second.id for job in listed_all)

    queued_only = jobs.list_jobs(db_session, deployment_id=deployment_id, status="queued", limit=20)
    assert all(job.status == "queued" for job in queued_only)


def test_claim_next_job_uses_sqlite_fallback_and_handles_empty_queue(db_session):
    deployment_id = _seed_deployment(db_session)
    claimed = jobs.claim_next_job(db_session, worker_id="worker-a")
    assert claimed is not None
    assert claimed.deployment_id == deployment_id
    assert claimed.status == "running"
    assert claimed.locked_by == "worker-a"
    assert claimed.locked_at is not None

    jobs.mark_job_done(db_session, job_id=claimed.id)
    while True:
        next_job = jobs.claim_next_job(db_session, worker_id="worker-b")
        if next_job is None:
            break
        jobs.mark_job_done(db_session, job_id=next_job.id)

    assert jobs.claim_next_job(db_session, worker_id="worker-c") is None


def test_mark_job_done_requeue_and_fail_paths(db_session):
    deployment_id = _seed_deployment(db_session)
    claimed_seed = jobs.claim_next_job(db_session, worker_id="seed-worker")
    assert claimed_seed is not None
    jobs.mark_job_done(db_session, job_id=claimed_seed.id)

    job = jobs.enqueue_job(db_session, deployment_id=deployment_id, reason="update")
    claimed = jobs.claim_next_job(db_session, worker_id="worker-1")
    assert claimed is not None
    assert claimed.id == job.id

    requeued = jobs.requeue_job(db_session, job_id=claimed.id, error="temporary", delay_seconds=0)
    assert requeued.status == "queued"
    assert requeued.attempt == 1
    assert requeued.last_error == "temporary"
    assert requeued.run_after <= datetime.utcnow()
    assert requeued.locked_by is None

    claimed_again = jobs.claim_next_job(db_session, worker_id="worker-2")
    assert claimed_again is not None
    failed = jobs.mark_job_failed(db_session, job_id=claimed_again.id, error="fatal")
    assert failed.status == "failed"
    assert failed.last_error == "fatal"
    assert failed.locked_by is None

    another = jobs.enqueue_job(db_session, deployment_id=deployment_id, reason="update")
    done = jobs.mark_job_done(db_session, job_id=another.id)
    assert done.status == "done"
    assert done.last_error is None


def test_not_found_paths_raise(db_session):
    with pytest.raises(NotFoundException):
        jobs.mark_job_done(db_session, job_id=999999)
    with pytest.raises(NotFoundException):
        jobs.requeue_job(db_session, job_id=999999, error="x", delay_seconds=1)
    with pytest.raises(NotFoundException):
        jobs.mark_job_failed(db_session, job_id=999999, error="x")


def test_dedupe_open_jobs_removes_duplicates(db_session):
    deployment_id = _seed_deployment(db_session)
    with pytest.raises(DeploymentInProgressException):
        jobs.enqueue_job(db_session, deployment_id=deployment_id, reason="update")
    db_session.rollback()
    removed = jobs.dedupe_open_jobs(db_session, deployment_id=deployment_id)
    assert removed == 0
    remaining_open = jobs.list_jobs(db_session, deployment_id=deployment_id, status="queued", limit=20)
    assert len(remaining_open) == 1
