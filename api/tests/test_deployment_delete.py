from sqlmodel import select

from app.models import DeploymentReconcileJobORM
from app.services import jobs
from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETING
from tests.conftest import client


def test_delete_deployment_flow(client, db_session):
    # create user
    user_resp = client.post("/users", json={"email": "deldep@example.com"})
    assert user_resp.status_code == 201
    user_id = user_resp.json()["id"]
    # create product
    prod_resp = client.post("/products", json={"name": "prod1", "description": "desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]
    # create template
    tmpl_resp = client.post(
        f"/products/{prod_id}/templates", json={"chart_ref": "registry.home:80/nextcloud/", "chart_version": "1.0.0"}
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]
    # create deployment
    dep_resp = client.post(
        f"/users/{user_id}/deployments", json={"desired_template_id": tmpl_id, "domainname": "example.com"}
    )
    assert dep_resp.status_code == 201
    dep_id = dep_resp.json()["id"]
    create_job = db_session.exec(
        select(DeploymentReconcileJobORM).where(
            DeploymentReconcileJobORM.deployment_id == dep_id,
            DeploymentReconcileJobORM.reason == "create",
        )
    ).one()
    jobs.mark_job_done(db_session, job_id=create_job.id)
    # delete deployment
    del_resp = client.delete(f"/users/{user_id}/deployments/{dep_id}")
    assert del_resp.status_code == 204
    # After deletion, the deployment can still be retrieved:
    get_resp = client.get(f"/users/{user_id}/deployments/{dep_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == DEPLOYMENT_STATUS_DELETING

    # And also still present in listing:
    list_resp = client.get(f"/users/{user_id}/deployments")
    assert list_resp.status_code == 200
    assert dep_id in {d["id"] for d in list_resp.json()}
