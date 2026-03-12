import io

import pytest
from PIL import Image

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


def _create_test_image(size=(100, 100)):
    img = Image.new("RGB", size, color="blue")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _setup_static_dir():
    from app.config import get_static_path

    static_path = get_static_path()
    icons_dir = static_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    yield


def test_update_product_multipart_with_icon(client):
    """PUT with multipart form should update fields and icon atomically."""
    prod_resp = client.post("/api/products", json={"name": "IconUpdate", "description": "before"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]
    assert prod_resp.json()["icon_url"] is None

    icon_data = _create_test_image()
    upd_resp = client.put(
        f"/api/products/{prod_id}",
        data={"payload": '{"name": "IconUpdated", "description": "after"}'},
        files={"icon": ("icon.png", icon_data, "image/png")},
    )
    assert upd_resp.status_code == 200
    data = upd_resp.json()
    assert data["name"] == "IconUpdated"
    assert data["description"] == "after"
    assert data["icon_url"] is not None
    assert data["icon_url"].startswith("/api/static/icons/")


def test_update_product_multipart_icon_only(client):
    """PUT with multipart form with only icon (empty JSON payload) should update icon."""
    prod_resp = client.post("/api/products", json={"name": "IconOnly", "description": "desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    icon_data = _create_test_image()
    upd_resp = client.put(
        f"/api/products/{prod_id}",
        data={"payload": "{}"},
        files={"icon": ("icon.png", icon_data, "image/png")},
    )
    assert upd_resp.status_code == 200
    data = upd_resp.json()
    # Name and description should be unchanged
    assert data["name"] == "IconOnly"
    assert data["description"] == "desc"
    assert data["icon_url"] is not None


def test_update_product_replaces_icon(client):
    """PUT with new icon should replace the existing icon."""
    prod_resp = client.post("/api/products", json={"name": "ReplaceIcon"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]

    icon_1 = _create_test_image((100, 100))
    resp_1 = client.put(
        f"/api/products/{prod_id}",
        data={"payload": "{}"},
        files={"icon": ("icon.png", icon_1, "image/png")},
    )
    url_1 = resp_1.json()["icon_url"]

    icon_2 = _create_test_image((200, 200))
    resp_2 = client.put(
        f"/api/products/{prod_id}",
        data={"payload": "{}"},
        files={"icon": ("icon.png", icon_2, "image/png")},
    )
    url_2 = resp_2.json()["icon_url"]

    assert url_1 != url_2
