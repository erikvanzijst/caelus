from tests.conftest import client


def test_product(client):
    product = client.post("/products", json={"name": "nextcloud", "description": "Nextcloud app"})
    assert product.status_code == 201

    conflict = client.post("/products", json={"name": "nextcloud", "description": "Nextcloud app"})
    assert conflict.status_code == 409


def test_product_deletion(client):
    product = client.post("/products", json={"name": "nextcloud", "description": "Nextcloud app"})
    assert product.status_code == 201

    resp = client.delete(f"/products/{product.json()['id']}")
    assert resp.status_code == 204


def test_user_deployment_flow(client):
    user = client.post("/users", json={"email": "user@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]

    product = client.post("/products", json={"name": "nextcloud", "description": "Nextcloud app"})
    assert product.status_code == 201
    product_id = product.json()["id"]

    template = client.post(
        f"/products/{product_id}/templates", json={"docker_image_url": "nextcloud:latest"}
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    deployment = client.post(
        f"/users/{user_id}/deployments",
        json={"template_id": template_id, "domainname": "cloud.example.com"},
    )
    assert deployment.status_code == 201
    deployment_id = deployment.json()["id"]

    listed = client.get(f"/users/{user_id}/deployments")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [deployment_id]

    fetched = client.get(f"/users/{user_id}/deployments/{deployment_id}")
    assert fetched.status_code == 200
    assert fetched.json()["domainname"] == "cloud.example.com"


def test_user_delete_flow(client):
    # Create a user
    user = client.post("/users", json={"email": "del@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]
    # Delete the user
    delete_resp = client.delete(f"/users/{user_id}")
    assert delete_resp.status_code == 204
    # Verify user is gone
    get_resp = client.get(f"/users/{user_id}")
    assert get_resp.status_code == 404
