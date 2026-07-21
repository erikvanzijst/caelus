"""Tests for recording the accepted Terms of Service version on a deployment."""
from uuid import UUID

from sqlmodel import select

from app.models import DeploymentORM
from app.services.reconcile_constants import DEPLOYMENT_STATUS_READY
from app.services.jobs import JobService
from app.models import DeploymentReconcileJobORM
from tests.conftest import client, db_session  # noqa: F401
from tests.conftest import create_free_plan_template, create_user


def _setup_product_template_plan(client, db_session, name):
    """Create a product with a canonical template and a free plan; return ids."""
    product_id = client.post(
        "/api/products", json={"name": name, "description": "desc"}
    ).json()["id"]
    template_id = client.post(
        f"/api/products/{product_id}/templates",
        json={
            "chart_ref": "registry.home/app/",
            "chart_version": "1.0.0",
            "values_schema_json": {
                "type": "object",
                "properties": {
                    "ingress": {
                        "type": "object",
                        "properties": {"host": {"type": "string", "title": "hostname"}},
                    }
                },
            },
        },
    ).json()["id"]
    client.put(f"/api/products/{product_id}", json={"template_id": template_id})
    ptv_id = create_free_plan_template(db_session, product_id)
    return template_id, ptv_id


def _create_body(template_id, ptv_id, host, **overrides):
    body = {
        "desired_template_id": template_id,
        "user_values_json": {"ingress": {"host": host}},
        "plan_template_id": ptv_id,
        "tos_version": "2026-07-01",
    }
    body.update(overrides)
    return body


def test_create_records_tos_version(client, db_session):
    user_id = create_user(client, "tos-ok@example.com")["id"]
    template_id, ptv_id = _setup_product_template_plan(client, db_session, "tos-ok")

    resp = client.post(
        f"/api/users/{user_id}/deployments",
        json=_create_body(template_id, ptv_id, "tos-ok.example.com"),
    )
    assert resp.status_code == 201
    # Returned in the read envelope
    assert resp.json()["deployment"]["tos_version"] == "2026-07-01"

    # Persisted on the row
    dep_id = UUID(resp.json()["deployment"]["id"])
    dep = db_session.get(DeploymentORM, dep_id)
    assert dep.tos_version == "2026-07-01"


def test_create_requires_tos_version(client, db_session):
    user_id = create_user(client, "tos-missing@example.com")["id"]
    template_id, ptv_id = _setup_product_template_plan(client, db_session, "tos-missing")

    body = _create_body(template_id, ptv_id, "tos-missing.example.com")
    del body["tos_version"]
    resp = client.post(f"/api/users/{user_id}/deployments", json=body)
    assert resp.status_code == 422

    # Nothing was created
    assert db_session.exec(select(DeploymentORM)).all() == []


def test_create_rejects_malformed_tos_version(client, db_session):
    user_id = create_user(client, "tos-bad@example.com")["id"]
    template_id, ptv_id = _setup_product_template_plan(client, db_session, "tos-bad")

    resp = client.post(
        f"/api/users/{user_id}/deployments",
        json=_create_body(
            template_id, ptv_id, "tos-bad.example.com", tos_version="July 1, 2026"
        ),
    )
    assert resp.status_code == 422
    assert db_session.exec(select(DeploymentORM)).all() == []


def test_read_returns_tos_version(client, db_session):
    user_id = create_user(client, "tos-read@example.com")["id"]
    template_id, ptv_id = _setup_product_template_plan(client, db_session, "tos-read")

    dep_id = client.post(
        f"/api/users/{user_id}/deployments",
        json=_create_body(template_id, ptv_id, "tos-read.example.com"),
    ).json()["deployment"]["id"]

    # Advance to ready to simulate a normal read path
    create_job = db_session.exec(
        select(DeploymentReconcileJobORM).where(
            DeploymentReconcileJobORM.deployment_id == UUID(dep_id),
            DeploymentReconcileJobORM.reason == "create",
        )
    ).one()
    JobService(db_session).mark_job_done(job_id=create_job.id)
    dep = db_session.get(DeploymentORM, UUID(dep_id))
    dep.status = DEPLOYMENT_STATUS_READY
    db_session.add(dep)
    db_session.commit()

    read = client.get(f"/api/users/{user_id}/deployments/{dep_id}")
    assert read.status_code == 200
    assert read.json()["tos_version"] == "2026-07-01"
