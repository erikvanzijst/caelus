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
        f"/products/{product_id}/templates", json={"docker_image_url": "nextcloud:latest"}
    )
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    deployment_resp = client.post(
        f"/users/{user_id}/deployments",
        json={"template_id": template_id, "domainname": "cloud.example.com"},
    )
    assert deployment_resp.status_code == 201
    deployment_id = deployment_resp.json()["id"]

    # Delete the deployment
    del_resp = client.delete(f"/users/{user_id}/deployments/{deployment_id}")
    assert del_resp.status_code == 204

    # Verify it is not listed
    list_resp = client.get(f"/users/{user_id}/deployments")
    assert list_resp.status_code == 200
    ids = [d["id"] for d in list_resp.json()]
    assert deployment_id not in ids

    # Deleting a non‑existent deployment should return 404
    not_found_resp = client.delete(f"/users/{user_id}/deployments/99999")
    assert not_found_resp.status_code == 404
