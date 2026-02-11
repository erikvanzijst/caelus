from tests.conftest import client


def test_delete_product_flow(client):
    # create product
    resp = client.post("/products", json={"name": "testprod", "description": "desc"})
    assert resp.status_code == 201
    prod_id = resp.json()["id"]
    # delete product
    del_resp = client.delete(f"/products/{prod_id}")
    assert del_resp.status_code == 204
    # get should 404
    get_resp = client.get(f"/products/{prod_id}")
    assert get_resp.status_code == 404
    # list should not include
    list_resp = client.get("/products")
    assert list_resp.status_code == 200
    ids = [p["id"] for p in list_resp.json()]
    assert prod_id not in ids


def test_delete_template_flow(client):
    # create product
    prod_resp = client.post("/products", json={"name": "tmplprod", "description": "desc"})
    assert prod_resp.status_code == 201
    prod_id = prod_resp.json()["id"]
    # create template
    tmpl_resp = client.post(
        f"/products/{prod_id}/templates", json={"docker_image_url": "img:latest"}
    )
    assert tmpl_resp.status_code == 201
    tmpl_id = tmpl_resp.json()["id"]
    # delete template
    del_resp = client.delete(f"/products/{prod_id}/templates/{tmpl_id}")
    assert del_resp.status_code == 204
    # get should 404
    get_resp = client.get(f"/products/{prod_id}/templates/{tmpl_id}")
    assert get_resp.status_code == 404
    # list templates should not include
    list_resp = client.get(f"/products/{prod_id}/templates")
    assert list_resp.status_code == 200
    ids = [t["id"] for t in list_resp.json()]
    assert tmpl_id not in ids
