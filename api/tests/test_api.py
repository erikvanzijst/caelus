from tests.conftest import client


def test_product(client):
    product = client.post(
        "/api/products", json={"name": "nextcloud", "description": "Nextcloud app"}
    )
    assert product.status_code == 201

    conflict = client.post(
        "/api/products", json={"name": "nextcloud", "description": "Nextcloud app"}
    )
    assert conflict.status_code == 409


def test_product_deletion(client):
    product = client.post(
        "/api/products", json={"name": "nextcloud", "description": "Nextcloud app"}
    )
    assert product.status_code == 201

    resp = client.delete(f"/api/products/{product.json()['id']}")
    assert resp.status_code == 204


def test_user_deployment_flow(client):
    user = client.post("/api/users", json={"email": "user@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]

    product = client.post(
        "/api/products", json={"name": "nextcloud", "description": "Nextcloud app"}
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    template = client.post(
        f"/api/products/{product_id}/templates",
        json={
            "chart_ref": "registry.home:80/nextcloud/",
            "chart_version": "1.0.0",
            "values_schema_json": {
                "type": "object",
                "properties": {
                    "user": {
                        "type": "object",
                        "properties": {"host": {"type": "string", "title": "DomainName"}},
                    }
                },
            },
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    deployment = client.post(
        f"/api/users/{user_id}/deployments",
        json={
            "desired_template_id": template_id,
            "user_values_json": {"user": {"host": "cloud.example.com"}},
        },
    )
    assert deployment.status_code == 201
    deployment_id = deployment.json()["id"]

    listed = client.get(f"/api/users/{user_id}/deployments")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [deployment_id]

    fetched = client.get(f"/api/users/{user_id}/deployments/{deployment_id}")
    assert fetched.status_code == 200
    assert fetched.json()["domainname"] == "cloud.example.com"


def test_user_deployment_flow_with_user_values(client):
    user = client.post("/api/users", json={"email": "user-values@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]

    product = client.post(
        "/api/products", json={"name": "nextcloud-values", "description": "Nextcloud app"}
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    template = client.post(
        f"/api/products/{product_id}/templates",
        json={
            "chart_ref": "oci://example/chart",
            "chart_version": "1.0.0",
            "values_schema_json": {
                "type": "object",
                "properties": {
                    "user": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string"},
                            "domain": {"type": "string", "title": "domainname"},
                        },
                        "required": ["message"],
                        "additionalProperties": False,
                    }
                },
                "required": ["user"],
                "additionalProperties": False,
            },
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    deployment = client.post(
        f"/api/users/{user_id}/deployments",
        json={
            "desired_template_id": template_id,
            "user_values_json": {"user": {"message": "hi", "domain": "values.example.com"}},
        },
    )
    assert deployment.status_code == 201
    assert deployment.json()["domainname"] == "values.example.com"
    assert deployment.json()["user_values_json"] == {"user": {"message": "hi", "domain": "values.example.com"}}


def test_deployment_write_contract_rejects_domainname(client):
    user = client.post("/api/users", json={"email": "contract@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]

    product = client.post(
        "/api/products", json={"name": "contract-product", "description": "Contract app"}
    )
    assert product.status_code == 201
    product_id = product.json()["id"]

    template_1 = client.post(
        f"/api/products/{product_id}/templates",
        json={
            "chart_ref": "oci://example/chart",
            "chart_version": "1.0.0",
            "values_schema_json": {
                "type": "object",
                "properties": {"user": {"type": "object"}},
            },
        },
    )
    assert template_1.status_code == 201
    template_1_id = template_1.json()["id"]

    template_2 = client.post(
        f"/api/products/{product_id}/templates",
        json={
            "chart_ref": "oci://example/chart",
            "chart_version": "2.0.0",
            "values_schema_json": {
                "type": "object",
                "properties": {"user": {"type": "object"}},
            },
        },
    )
    assert template_2.status_code == 201
    template_2_id = template_2.json()["id"]

    bad_create = client.post(
        f"/api/users/{user_id}/deployments",
        json={"desired_template_id": template_1_id, "domainname": "bad.example.com"},
    )
    assert bad_create.status_code == 422

    created = client.post(
        f"/api/users/{user_id}/deployments",
        json={"desired_template_id": template_1_id, "user_values_json": {"user": {}}},
    )
    assert created.status_code == 201
    deployment_id = created.json()["id"]

    bad_update = client.put(
        f"/api/users/{user_id}/deployments/{deployment_id}",
        json={"desired_template_id": template_2_id, "domainname": "bad.example.com"},
    )
    assert bad_update.status_code == 422


def test_user_delete_flow(client):
    # Create a user
    user = client.post("/api/users", json={"email": "del@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]
    # Delete the user
    delete_resp = client.delete(f"/api/users/{user_id}")
    assert delete_resp.status_code == 204
    # Verify user is gone
    get_resp = client.get(f"/api/users/{user_id}")
    assert get_resp.status_code == 404
