from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlmodel import Session, create_engine

from app.db import init_db
from app.services import deployments, jobs, products, templates, users


PG_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not PG_TEST_DATABASE_URL,
    reason="POSTGRES_TEST_DATABASE_URL is not set",
)


def _seed_jobs(engine, *, job_count: int) -> None:
    token = uuid4().hex[:8]
    with Session(engine) as session:
        user = users.create_user(session, payload=users.UserCreate(email=f"pg-jobs-user-{token}@example.com"))
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
            ),
        )
        deployment = deployments.create_deployment(
            session,
            payload=deployments.DeploymentCreate(
                user_id=user.id,
                desired_template_id=template.id,
                domainname=f"pg-jobs-{token}.example.test",
            ),
        )
        for _ in range(job_count - 1):
            jobs.enqueue_job(session, deployment_id=deployment.id, reason="update")


def _claim_once(engine, worker_id: str) -> int | None:
    with Session(engine) as session:
        job = jobs.claim_next_job(session, worker_id=worker_id)
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
