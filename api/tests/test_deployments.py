from tests.conftest import client, db_session
from sqlmodel import select

from app.models import DeploymentORM, DeploymentReconcileJobORM


def test_delete_deployment_flow(client, db_session):
    # Setup: create user, product, template, deployment
    user_resp = client.post("/users", json={"email": "deldep@example.com"})
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]

    product_resp = client.post(
        "/products", json={"name": "nextcloud", "description": "Nextcloud app"}
    )
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    template_resp = client.post(
        f"/products/{product_id}/templates", json={"chart_ref": "registry.home:80/nextcloud/", "chart_version": "1.0.0"}
    )
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    deployment_resp = client.post(
        f"/users/{user_id}/deployments",
        json={"desired_template_id": template_id, "domainname": "cloud.example.com"},
    )
    assert deployment_resp.status_code == 201
    deployment_id = deployment_resp.json()["id"]
    assert deployment_resp.json()["status"] == "pending"
    assert deployment_resp.json()["generation"] == 1
    create_jobs = db_session.exec(
        select(DeploymentReconcileJobORM).where(
            DeploymentReconcileJobORM.deployment_id == deployment_id,
            DeploymentReconcileJobORM.reason == "create",
        )
    ).all()
    assert len(create_jobs) == 1

    # Delete the deployment
    del_resp = client.delete(f"/users/{user_id}/deployments/{deployment_id}")
    assert del_resp.status_code == 204
    deleted = db_session.get(DeploymentORM, deployment_id)
    assert deleted is not None
    assert deleted.status == "deleting"
    delete_jobs = db_session.exec(
        select(DeploymentReconcileJobORM).where(
            DeploymentReconcileJobORM.deployment_id == deployment_id,
            DeploymentReconcileJobORM.reason == "delete",
        )
    ).all()
    assert len(delete_jobs) == 1

    # Verify it is not listed
    list_resp = client.get(f"/users/{user_id}/deployments")
    assert list_resp.status_code == 200
    ids = [d["id"] for d in list_resp.json()]
    assert deployment_id not in ids

    # Deleting a non‑existent deployment should return 404
    not_found_resp = client.delete(f"/users/{user_id}/deployments/99999")
    assert not_found_resp.status_code == 404


def test_upgrade_deployment_endpoint_sets_state_and_enqueues_job(client, db_session):
    user_resp = client.post("/users", json={"email": "upgrade-api@example.com"})
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]

    product_resp = client.post("/products", json={"name": "upgrade-api-prod", "description": "desc"})
    assert product_resp.status_code == 201
    product_id = product_resp.json()["id"]

    tmpl1_resp = client.post(
        f"/products/{product_id}/templates", json={"chart_ref": "oci://example/chart", "chart_version": "1.0.0"}
    )
    assert tmpl1_resp.status_code == 201
    tmpl1_id = tmpl1_resp.json()["id"]

    tmpl2_resp = client.post(
        f"/products/{product_id}/templates", json={"chart_ref": "oci://example/chart", "chart_version": "2.0.0"}
    )
    assert tmpl2_resp.status_code == 201
    tmpl2_id = tmpl2_resp.json()["id"]

    dep_resp = client.post(
        f"/users/{user_id}/deployments",
        json={"desired_template_id": tmpl1_id, "domainname": "upgrade-api.example.test"},
    )
    assert dep_resp.status_code == 201
    dep_id = dep_resp.json()["id"]

    upgrade_resp = client.put(
        f"/users/{user_id}/deployments/{dep_id}",
        json={"desired_template_id": tmpl2_id},
    )
    assert upgrade_resp.status_code == 200
    assert upgrade_resp.json()["status"] == "upgrading"
    assert upgrade_resp.json()["desired_template_id"] == tmpl2_id
    assert upgrade_resp.json()["generation"] == 2

    update_jobs = db_session.exec(
        select(DeploymentReconcileJobORM).where(
            DeploymentReconcileJobORM.deployment_id == dep_id,
            DeploymentReconcileJobORM.reason == "update",
        )
    ).all()
    assert len(update_jobs) == 1
