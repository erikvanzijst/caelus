from starlette.testclient import TestClient

from tests.conftest import client, db_session
from tests.conftest import create_free_plan_template

from app.db import get_session
from app.main import app as fastapi_app


# ── /api/me tests ─────────────────────────────────────────────────────


def test_me_returns_user_for_known_email(client, db_session):
    # Pre-create a user via the normal endpoint
    resp = client.post("/api/users", json={"email": "known@example.com"})
    assert resp.status_code == 201

    # Now call /api/me with that email
    me_resp = client.get("/api/me", headers={"X-Auth-Request-Email": "known@example.com"})
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == "known@example.com"
    assert "id" in data
    assert "is_admin" in data


def test_me_auto_creates_unknown_email(client):
    me_resp = client.get("/api/me", headers={"X-Auth-Request-Email": "newuser@example.com"})
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["is_admin"] is False

    # Verify the user now appears in the user list (client is admin)
    users_resp = client.get("/api/users")
    emails = [u["email"] for u in users_resp.json()]
    assert "newuser@example.com" in emails


def test_me_case_insensitive_email(client, db_session):
    # Create a user with lowercase email
    client.post("/api/users", json={"email": "alice@example.com"})

    # Call /api/me with mixed-case variant
    me_resp = client.get("/api/me", headers={"X-Auth-Request-Email": "Alice@Example.COM"})
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "alice@example.com"


def test_me_returns_404_when_header_missing(db_session):
    # Use a client WITHOUT the default auth header
    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_session] = override_get_db
    with TestClient(fastapi_app) as no_auth_client:
        resp = no_auth_client.get("/api/me")
        assert resp.status_code == 404
    fastapi_app.dependency_overrides.clear()


# ── Auth enforcement on existing endpoints ────────────────────────────


def test_endpoints_return_404_without_auth_header(db_session):
    """All protected endpoints should return 404 when X-Auth-Request-Email is absent."""
    def override_get_db():
        yield db_session

    fastapi_app.dependency_overrides[get_session] = override_get_db
    with TestClient(fastapi_app) as no_auth_client:
        endpoints = [
            ("GET", "/api/users"),
            ("POST", "/api/users"),
            ("GET", "/api/users/1"),
            ("DELETE", "/api/users/1"),
            ("GET", "/api/users/1/deployments"),
            ("POST", "/api/users/1/deployments"),
            ("GET", "/api/users/1/deployments/00000000-0000-0000-0000-000000000001"),
            ("PUT", "/api/users/1/deployments/00000000-0000-0000-0000-000000000001"),
            ("DELETE", "/api/users/1/deployments/00000000-0000-0000-0000-000000000001"),
            ("GET", "/api/products"),
            ("POST", "/api/products"),
            ("GET", "/api/products/1"),
            ("PUT", "/api/products/1"),
            ("DELETE", "/api/products/1"),
            ("POST", "/api/products/1/templates"),
            ("GET", "/api/products/1/templates"),
            ("GET", "/api/products/1/templates/1"),
            ("DELETE", "/api/products/1/templates/1"),
            ("GET", "/api/hostnames/test.example.com"),
        ]
        for method, path in endpoints:
            resp = no_auth_client.request(method, path)
            assert resp.status_code == 404, (
                f"{method} {path} returned {resp.status_code}, expected 404"
            )
    fastapi_app.dependency_overrides.clear()


# ── Existing tests ────────────────────────────────────────────────────


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


def test_user_deployment_flow(client, db_session):
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
                        "properties": {"host": {"type": "string", "title": "Hostname"}},
                    }
                },
            },
        },
    )
    assert template.status_code == 201
    template_id = template.json()["id"]

    # Make it the canonical template
    client.put(f"/api/products/{product_id}", json={"template_id": template_id})

    ptv_id = create_free_plan_template(db_session, product_id)

    deployment = client.post(
        f"/api/users/{user_id}/deployments",
        json={
            "desired_template_id": template_id,
            "user_values_json": {"user": {"host": "cloud.example.com"}},
            "plan_template_id": ptv_id,
        },
    )
    assert deployment.status_code == 201
    deployment_id = deployment.json()["deployment"]["id"]

    listed = client.get(f"/api/users/{user_id}/deployments")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [deployment_id]

    fetched = client.get(f"/api/users/{user_id}/deployments/{deployment_id}")
    assert fetched.status_code == 200
    assert fetched.json()["hostname"] == "cloud.example.com"


def test_user_deployment_flow_with_user_values(client, db_session):
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
                            "domain": {"type": "string", "title": "hostname"},
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

    # Make it the canonical template
    client.put(f"/api/products/{product_id}", json={"template_id": template_id})

    ptv_id = create_free_plan_template(db_session, product_id)

    deployment = client.post(
        f"/api/users/{user_id}/deployments",
        json={
            "desired_template_id": template_id,
            "user_values_json": {"user": {"message": "hi", "domain": "values.example.com"}},
            "plan_template_id": ptv_id,
        },
    )
    assert deployment.status_code == 201
    assert deployment.json()["deployment"]["hostname"] == "values.example.com"
    assert deployment.json()["deployment"]["user_values_json"] == {"user": {"message": "hi", "domain": "values.example.com"}}


def test_deployment_write_contract_rejects_hostname(client, db_session):
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

    # Make it the canonical template
    client.put(f"/api/products/{product_id}", json={"template_id": template_1_id})

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

    ptv_id = create_free_plan_template(db_session, product_id)

    bad_create = client.post(
        f"/api/users/{user_id}/deployments",
        json={"desired_template_id": template_1_id, "hostname": "bad.example.com", "plan_template_id": ptv_id},
    )
    assert bad_create.status_code == 422

    created = client.post(
        f"/api/users/{user_id}/deployments",
        json={"desired_template_id": template_1_id, "user_values_json": {"user": {}}, "plan_template_id": ptv_id},
    )
    assert created.status_code == 201
    deployment_id = created.json()["deployment"]["id"]

    bad_update = client.put(
        f"/api/users/{user_id}/deployments/{deployment_id}",
        json={"desired_template_id": template_2_id, "hostname": "bad.example.com"},
    )
    assert bad_update.status_code == 422


def test_user_delete_returns_501(client):
    # Create a user
    user = client.post("/api/users", json={"email": "del@example.com"})
    assert user.status_code == 201
    user_id = user.json()["id"]
    # User deletion is disabled
    delete_resp = client.delete(f"/api/users/{user_id}")
    assert delete_resp.status_code == 501
    assert delete_resp.json()["detail"] == "User deletion is not yet implemented"
