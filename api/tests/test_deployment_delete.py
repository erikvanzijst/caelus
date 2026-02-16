from tests.conftest import client


def test_delete_deployment_flow(client):
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
    # delete deployment
    del_resp = client.delete(f"/users/{user_id}/deployments/{dep_id}")
    assert del_resp.status_code == 204
    # get should be 404
    get_resp = client.get(f"/users/{user_id}/deployments/{dep_id}")
    assert get_resp.status_code == 404
    # list should not include
    list_resp = client.get(f"/users/{user_id}/deployments")
    assert list_resp.status_code == 200
    ids = [d["id"] for d in list_resp.json()]
    assert dep_id not in ids
