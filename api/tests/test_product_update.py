import pytest
from tests.conftest import client


def test_update_product_template(client):
    # Create product
    prod_resp = client.post("/api/products", json={"name": "updatable", "description": "desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    # Create template for product
    tmpl_resp = client.post(
        f"/api/products/{prod_id}/templates",
        json={"chart_ref": "registry.home:80/nextcloud/", "chart_version": "1.0.0"},
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]

    # Update product to set template_id
    upd_resp = client.put(f"/api/products/{prod_id}", json={"template_id": tmpl_id})
    assert upd_resp.status_code == 200
    assert upd_resp.json()["template_id"] == tmpl_id

    # Verify via GET
    get_resp = client.get(f"/api/products/{prod_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["template_id"] == tmpl_id


def test_update_product_name(client):
    prod_resp = client.post("/api/products", json={"name": "OldName", "description": "desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    upd_resp = client.put(f"/api/products/{prod_id}", json={"name": "NewName"})
    assert upd_resp.status_code == 200
    assert upd_resp.json()["name"] == "NewName"

    get_resp = client.get(f"/api/products/{prod_id}")
    assert get_resp.json()["name"] == "NewName"
    # Description should be unchanged
    assert get_resp.json()["description"] == "desc"


def test_update_product_description(client):
    prod_resp = client.post("/api/products", json={"name": "DescTest", "description": "old"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    upd_resp = client.put(f"/api/products/{prod_id}", json={"description": "new description"})
    assert upd_resp.status_code == 200
    assert upd_resp.json()["description"] == "new description"

    get_resp = client.get(f"/api/products/{prod_id}")
    assert get_resp.json()["description"] == "new description"
    # Name should be unchanged
    assert get_resp.json()["name"] == "DescTest"


def test_update_product_clear_description(client):
    prod_resp = client.post("/api/products", json={"name": "ClearDesc", "description": "will be cleared"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    upd_resp = client.put(f"/api/products/{prod_id}", json={"description": ""})
    assert upd_resp.status_code == 200
    assert upd_resp.json()["description"] == ""

    get_resp = client.get(f"/api/products/{prod_id}")
    assert get_resp.json()["description"] == ""


def test_update_product_name_and_description(client):
    prod_resp = client.post("/api/products", json={"name": "BothTest", "description": "old desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    upd_resp = client.put(
        f"/api/products/{prod_id}",
        json={"name": "BothRenamed", "description": "new desc"},
    )
    assert upd_resp.status_code == 200
    assert upd_resp.json()["name"] == "BothRenamed"
    assert upd_resp.json()["description"] == "new desc"
