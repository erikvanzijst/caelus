from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from sqlmodel import Session, create_engine

from app.db import init_db
from app.models import DeploymentReconcileJobORM, ProductORM
from app.services import deployments, products, templates, users
from app.services.jobs import JobService
from tests.conftest import create_free_plan_template, make_accepted_user


PG_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is not set",
)


def _seed_jobs(engine, *, job_count: int) -> None:
    token = uuid4().hex[:8]
    with Session(engine) as session:
        user = make_accepted_user(session, f"pg-jobs-user-{token}@example.com")
        product = products.create_product(
            session,
            payload=products.ProductCreate(name=f"pg-jobs-product-{token}", description="desc"),
        )
        template = templates.create_template(
            session,
            payload=templates.ProductTemplateVersionCreate(
                product_id=product.id,
                chart_ref="oci://example/chart",
                chart_version="1.0.0",
                values_schema_json={
                    "type": "object",
                    "properties": {"domain": {"type": "string", "title": "hostname"}},
                },
            ),
        )
        deployment = deployments.create_deployment(
            session,
            payload=deployments.DeploymentCreate(
                user_id=user.id,
                desired_template_id=template.id,
                user_values_json={"domain": f"pg-jobs-{token}.example.test"},
            ),
        ).deployment
        jobs = JobService(session)
        for _ in range(job_count - 1):
            jobs.enqueue_job(deployment_id=deployment.id, reason="update")


def _claim_once(engine, worker_id: str) -> int | None:
    with Session(engine) as session:
        job = JobService(session).claim_next_job(worker_id=worker_id)
        return None if job is None else job.id


def test_claim_next_job_postgres_no_double_claim_under_parallel_workers():
    engine = create_engine(PG_TEST_DATABASE_URL)
    init_db(engine)
    expected_claims = 8
    _seed_jobs(engine, job_count=expected_claims)

    worker_ids = [f"pg-worker-{i}" for i in range(16)]
    with ThreadPoolExecutor(max_workers=16) as executor:
        claimed_ids = list(executor.map(lambda w: _claim_once(engine, w), worker_ids))

    non_null_claims = [job_id for job_id in claimed_ids if job_id is not None]
    assert len(non_null_claims) == expected_claims
    assert len(set(non_null_claims)) == expected_claims


def _seed_deployment(engine) -> UUID:
    """Create one deployment (and therefore one queued create job) on Postgres."""
    token = uuid4().hex[:8]
    with Session(engine) as session:
        user = make_accepted_user(session, f"pg-lease-user-{token}@example.com")
        product = products.create_product(
            session,
            payload=products.ProductCreate(name=f"pg-lease-product-{token}", description="desc"),
        )
        template = templates.create_template(
            session,
            payload=templates.ProductTemplateVersionCreate(
                product_id=product.id,
                chart_ref="oci://example/chart",
                chart_version="1.0.0",
                values_schema_json={
                    "type": "object",
                    "properties": {"domain": {"type": "string", "title": "hostname"}},
                },
            ),
        )
        product_orm = session.get(ProductORM, product.id)
        product_orm.template_id = template.id
        session.add(product_orm)
        session.commit()
        ptv_id = create_free_plan_template(session, product.id)
        deployment = deployments.create_deployment(
            session,
            payload=deployments.DeploymentCreate(
                user_id=user.id,
                desired_template_id=template.id,
                user_values_json={"domain": f"pg-lease-{token}.example.test"},
                plan_template_id=ptv_id,
            ),
        ).deployment
        return deployment.id


def _backdate(engine, job_id: int, *, run_after: datetime, locked_at: datetime | None) -> None:
    with Session(engine) as session:
        job = session.get(DeploymentReconcileJobORM, job_id)
        job.run_after = run_after
        if locked_at is not None:
            job.locked_at = locked_at
        session.add(job)
        session.commit()


def test_expired_lease_is_reclaimed_on_postgres():
    """The FOR UPDATE SKIP LOCKED path must reclaim leases too, not just SQLite.

    The Postgres claim query is a different statement from the SQLite one, so the
    lease behavior asserted in test_jobs_service.py says nothing about the path
    that actually runs in production.
    """
    engine = create_engine(PG_TEST_DATABASE_URL)
    init_db(engine)
    deployment_id = _seed_deployment(engine)

    with Session(engine) as session:
        claimed = JobService(session).claim_next_job(worker_id="pg-worker-dead")
        assert claimed is not None
        assert claimed.deployment_id == deployment_id
        job_id = claimed.id
        assert claimed.attempt == 0

    # Sort this job to the very front of the queue so the assertions below do not
    # depend on what else happens to be pending in the shared test database.
    ancient = datetime(2000, 1, 1, tzinfo=UTC)
    _backdate(engine, job_id, run_after=ancient, locked_at=datetime.now(UTC))

    # A fresh lease is not stealable even though the job sorts first.
    with Session(engine) as session:
        other = JobService(session).claim_next_job(worker_id="pg-worker-thief")
        assert other is None or other.id != job_id
    with Session(engine) as session:
        assert session.get(DeploymentReconcileJobORM, job_id).locked_by == "pg-worker-dead"

    # Once the lease expires the job is reclaimed, with attempt bumped.
    _backdate(
        engine,
        job_id,
        run_after=ancient,
        locked_at=datetime.now(UTC) - timedelta(minutes=30),
    )
    with Session(engine) as session:
        reclaimed = JobService(session).claim_next_job(worker_id="pg-worker-live")
        assert reclaimed is not None
        assert reclaimed.id == job_id
        assert reclaimed.status == "running"
        assert reclaimed.locked_by == "pg-worker-live"
        assert reclaimed.attempt == 1

    # And a worker whose lease was stolen cannot report a result any more.
    with Session(engine) as session:
        jobs = JobService(session)
        ignored = jobs.mark_job_done(job_id=job_id, worker_id="pg-worker-dead")
        assert ignored.status == "running"
        assert ignored.locked_by == "pg-worker-live"
        done = jobs.mark_job_done(job_id=job_id, worker_id="pg-worker-live")
        assert done.status == "done"
