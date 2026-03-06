import io

import pytest
from PIL import Image


def create_test_image(size=(100, 100), format="PNG"):
    img = Image.new("RGB", size, color="red")
    buf = io.BytesIO()
    img.save(buf, format=format)
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def setup_static_dir():
    from app.config import get_static_path

    static_path = get_static_path()
    icons_dir = static_path / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    yield


def test_product_icon_url_absent_on_create(client):
    """Product created without icon should have null icon_url."""
    resp = client.post("/api/products", json={"name": "test-prod", "description": "Test"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["icon_url"] is None
    assert "rel_icon_path" not in data


def test_product_icon_url_present_after_upload(client):
    """Product with icon should have icon_url pointing to static path."""
    resp = client.post("/api/products", json={"name": "test-prod-2", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data = create_test_image()
    upload_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data, "image/png")},
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["icon_url"] is not None
    assert data["icon_url"].startswith("/api/static/icons/")


def test_product_rel_icon_path_not_exposed(client):
    """API responses should not expose rel_icon_path."""
    resp = client.post("/api/products", json={"name": "test-prod-3", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data = create_test_image()
    client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data, "image/png")},
    )

    get_resp = client.get(f"/api/products/{product_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert "rel_icon_path" not in data
    assert data["icon_url"] is not None


def test_multipart_create_with_icon(client):
    """POST /api/products with multipart form should create product with icon."""
    icon_data = create_test_image()
    resp = client.post(
        "/api/products",
        data={"payload": '{"name": "multi-prod", "description": "Multipart"}'},
        files={"icon": ("icon.png", icon_data, "image/png")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["icon_url"] is not None
    assert data["icon_url"].startswith("/api/static/icons/")


def test_multipart_create_without_icon(client):
    """POST /api/products with multipart form without icon should work."""
    resp = client.post(
        "/api/products",
        json={"name": "multi-prod-noicon", "description": "No icon"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["icon_url"] is None


def test_multipart_create_invalid_json(client):
    """Multipart with invalid JSON should return 422."""
    resp = client.post(
        "/api/products",
        data={"payload": "not valid json"},
        files={"icon": ("icon.png", create_test_image(), "image/png")},
    )
    assert resp.status_code == 422


def test_multipart_create_missing_payload(client):
    """Multipart without payload should return 422."""
    resp = client.post(
        "/api/products",
        files={"icon": ("icon.png", create_test_image(), "image/png")},
    )
    assert resp.status_code == 422


def test_multipart_create_icon_field_not_file(client):
    """Multipart with non-file icon field should return 422."""
    resp = client.post(
        "/api/products",
        data={
            "payload": '{"name": "multi-prod-bad-icon", "description": "Bad icon"}',
            "icon": "not-a-file",
        },
        files={"dummy": ("dummy.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 422


def test_icon_upload_nonexistent_product(client):
    """Uploading icon to nonexistent product should return 404."""
    resp = client.put(
        "/api/products/99999/icon",
        files={"icon": ("test.png", create_test_image(), "image/png")},
    )
    assert resp.status_code == 404


def test_get_icon_redirect_with_icon(client):
    """GET /api/products/{id}/icon should redirect to static path."""
    resp = client.post("/api/products", json={"name": "icon-redirect-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data = create_test_image()
    client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data, "image/png")},
    )

    redirect_resp = client.get(f"/api/products/{product_id}/icon", follow_redirects=False)
    assert redirect_resp.status_code == 302
    assert "/api/static/icons/" in redirect_resp.headers["Location"]


def test_get_icon_redirect_no_icon(client):
    """GET /api/products/{id}/icon with no icon should return 404."""
    resp = client.post("/api/products", json={"name": "no-icon-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    get_icon_resp = client.get(f"/api/products/{product_id}/icon")
    assert get_icon_resp.status_code == 404


def test_icon_file_immutable_on_replacement(client):
    """Replacing icon should create new file, old file should remain."""
    resp = client.post("/api/products", json={"name": "immutable-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data_1 = create_test_image()
    first_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data_1, "image/png")},
    )
    first_url = first_resp.json()["icon_url"]

    icon_data_2 = create_test_image((200, 200))
    second_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test2.png", icon_data_2, "image/png")},
    )
    second_url = second_resp.json()["icon_url"]

    assert first_url != second_url


def test_icon_size_limit(client):
    """Icon larger than 10MB should be rejected."""
    resp = client.post("/api/products", json={"name": "size-limit-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    large_data = b"x" * (11 * 1024 * 1024)
    upload_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("large.png", large_data, "image/png")},
    )
    assert upload_resp.status_code == 400


def test_icon_resolution_limit(client):
    """Icon with resolution > 2048 should be rejected."""
    resp = client.post("/api/products", json={"name": "res-limit-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    large_img = create_test_image((3000, 3000))
    upload_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("large.png", large_img, "image/png")},
    )
    assert upload_resp.status_code == 400


def test_static_file_serving(client):
    """Static endpoint should serve uploaded files."""
    resp = client.post("/api/products", json={"name": "static-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data = create_test_image()
    upload_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data, "image/png")},
    )
    icon_url = upload_resp.json()["icon_url"]

    static_path = icon_url.replace("/api/static/", "/api/static/")
    file_resp = client.get(static_path)
    assert file_resp.status_code == 200
    assert file_resp.headers.get("content-type") == "image/png"


def test_static_etag_present(client):
    """Static responses should include ETag."""
    resp = client.post("/api/products", json={"name": "etag-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data = create_test_image()
    upload_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data, "image/png")},
    )
    icon_url = upload_resp.json()["icon_url"]
    static_path = icon_url.replace("/api/static/", "/api/static/")

    file_resp = client.get(static_path)
    assert "ETag" in file_resp.headers


def test_static_if_none_match_304(client):
    """Static endpoint should return 304 when ETag matches."""
    resp = client.post("/api/products", json={"name": "notmodified-test", "description": "Test"})
    assert resp.status_code == 201
    product_id = resp.json()["id"]

    icon_data = create_test_image()
    upload_resp = client.put(
        f"/api/products/{product_id}/icon",
        files={"icon": ("test.png", icon_data, "image/png")},
    )
    icon_url = upload_resp.json()["icon_url"]
    static_path = icon_url.replace("/api/static/", "/api/static/")

    first_resp = client.get(static_path)
    etag = first_resp.headers.get("ETag")

    second_resp = client.get(static_path, headers={"If-None-Match": etag})
    assert second_resp.status_code == 304


def test_static_path_traversal_blocked(client):
    """Static endpoint should block path traversal."""
    resp = client.get("/api/static/../../../etc/passwd")
    assert resp.status_code == 404
