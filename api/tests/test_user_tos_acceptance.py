"""Tests for the user-level Terms of Service acceptance resource.

Acceptance is recorded once, on the user, via `POST /api/me/tos-acceptance` and
read via `GET /api/me/tos-acceptance`. Deploying requires prior acceptance.
"""
from sqlmodel import select

from app.config import get_settings
from app.models import DeploymentORM, UserORM
from tests.conftest import client, db_session  # noqa: F401
from tests.conftest import create_free_plan_template, create_user

CURRENT = get_settings().current_tos_version


def _headers(email):
    return {"X-Auth-Request-Email": email}


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
    }
    body.update(overrides)
    return body


# --- The acceptance resource -------------------------------------------------


def test_acceptance_initially_absent(client, db_session):
    email = "tos-absent@example.com"
    create_user(client, email, accept_tos=False)
    resp = client.get("/api/me/tos-acceptance", headers=_headers(email))
    assert resp.status_code == 200
    assert resp.json() == {"version": None, "accepted_at": None}


def test_record_acceptance(client, db_session):
    email = "tos-record@example.com"
    user = create_user(client, email, accept_tos=False)

    resp = client.post(
        "/api/me/tos-acceptance", json={"version": CURRENT}, headers=_headers(email)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == CURRENT
    assert body["accepted_at"] is not None

    # Persisted on the user and reflected by a subsequent GET.
    u = db_session.get(UserORM, user["id"])
    assert u.tos_accepted_version == CURRENT
    assert u.tos_accepted_at is not None
    assert client.get(
        "/api/me/tos-acceptance", headers=_headers(email)
    ).json()["version"] == CURRENT


def test_record_mismatch_is_conflict(client, db_session):
    email = "tos-mismatch@example.com"
    user = create_user(client, email, accept_tos=False)

    resp = client.post(
        "/api/me/tos-acceptance", json={"version": "2025-01-01"}, headers=_headers(email)
    )
    assert resp.status_code == 409
    assert db_session.get(UserORM, user["id"]).tos_accepted_version is None


def test_record_malformed_rejected(client, db_session):
    email = "tos-malformed@example.com"
    user = create_user(client, email, accept_tos=False)

    resp = client.post(
        "/api/me/tos-acceptance", json={"version": "July 1, 2026"}, headers=_headers(email)
    )
    assert resp.status_code == 422
    assert db_session.get(UserORM, user["id"]).tos_accepted_version is None


def test_record_is_idempotent(client, db_session):
    email = "tos-idem@example.com"
    create_user(client, email, accept_tos=False)
    client.post("/api/me/tos-acceptance", json={"version": CURRENT}, headers=_headers(email))
    resp = client.post(
        "/api/me/tos-acceptance", json={"version": CURRENT}, headers=_headers(email)
    )
    assert resp.status_code == 200
    assert resp.json()["version"] == CURRENT


# --- Deployment precondition -------------------------------------------------


def test_deploy_requires_prior_acceptance(client, db_session):
    email = "tos-deploy-blocked@example.com"
    user = create_user(client, email, accept_tos=False)
    template_id, ptv_id = _setup_product_template_plan(client, db_session, "tos-blocked")

    resp = client.post(
        f"/api/users/{user['id']}/deployments",
        json=_create_body(template_id, ptv_id, "tos-blocked.example.com"),
    )
    assert resp.status_code == 400  # must accept the Terms first
    assert db_session.exec(select(DeploymentORM)).all() == []


def test_deploy_succeeds_after_acceptance(client, db_session):
    email = "tos-deploy-ok@example.com"
    user = create_user(client, email, accept_tos=False)
    template_id, ptv_id = _setup_product_template_plan(client, db_session, "tos-ok")

    client.post("/api/me/tos-acceptance", json={"version": CURRENT}, headers=_headers(email))
    resp = client.post(
        f"/api/users/{user['id']}/deployments",
        json=_create_body(template_id, ptv_id, "tos-ok.example.com"),
    )
    assert resp.status_code == 201
    # ToS is no longer part of the deployment payload or response.
    assert "tos_version" not in resp.json()["deployment"]
