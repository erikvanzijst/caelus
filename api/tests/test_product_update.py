import pytest
from tests.conftest import client


def test_update_product_template(client):
    # Create product
    prod_resp = client.post("/products", json={"name": "updatable", "description": "desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    # Create template for product
    tmpl_resp = client.post(
        f"/products/{prod_id}/templates", json={"chart_ref": "registry.home:80/nextcloud/", "chart_version": "1.0.0"}
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]

    # Update product to set template_id
    upd_resp = client.put(f"/products/{prod_id}", json={"template_id": tmpl_id})
    assert upd_resp.status_code == 200
    assert upd_resp.json()["template_id"] == tmpl_id

    # Verify via GET
    get_resp = client.get(f"/products/{prod_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["template_id"] == tmpl_id
