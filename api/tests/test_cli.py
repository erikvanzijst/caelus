from __future__ import annotations


def _get_product_id_from_list_output(output: str) -> int:
    lines = [ln for ln in output.strip().splitlines() if ln]
    assert len(lines) == 1
    prod_id_str, prod_name = lines[0].split(maxsplit=1)
    assert prod_name
    return int(prod_id_str)


def _get_template_id_from_create_output(output: str) -> int:
    # Expected format: "Created template {id} for product {product_id}"
    parts = output.strip().split()
    return int(parts[2])


def test_cli_user_flow(cli_runner):
    runner, app = cli_runner

    # Create user
    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    assert "Created user" in result.output

    # List users to verify creation
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "cli@example.com" in result.output


def test_cli_product_flow(cli_runner):
    """Test creating, listing, and deleting a product via CLI."""
    runner, app = cli_runner

    # Create a product
    create_res = runner.invoke(app, ["create-product", "testprod", "A test product"])
    assert create_res.exit_code == 0
    assert "Created product" in create_res.output

    # List products to get the ID
    list_res = runner.invoke(app, ["list-products"])
    assert list_res.exit_code == 0
    # Expected format: "{id} {name}" per line
    prod_id = _get_product_id_from_list_output(list_res.output)

    # Delete the product
    del_res = runner.invoke(app, ["delete-product", str(prod_id)])
    assert del_res.exit_code == 0
    assert "Deleted product" in del_res.output

    # Verify product list is empty
    list_res2 = runner.invoke(app, ["list-products"])
    assert list_res2.exit_code == 0
    assert list_res2.output.strip() == ""

    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert result.output.strip() == ""

    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    assert "Created user" in result.output

    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    assert "cli@example.com" in result.output


def test_cli_update_product_supports_template_and_description(cli_runner):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "updatable", "old description"])
    assert create_res.exit_code == 0

    list_res = runner.invoke(app, ["list-products"])
    assert list_res.exit_code == 0
    prod_id = _get_product_id_from_list_output(list_res.output)

    template_res = runner.invoke(app, ["create-template", str(prod_id), "registry.home:80/nextcloud/", "1.0.0"])
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    update_res = runner.invoke(
        app,
        ["update-product", str(prod_id), "--template-id", str(template_id), "--description", "new description"],
    )
    assert update_res.exit_code == 0
    assert "Updated product" in update_res.output
    assert f"template_id={template_id}" in update_res.output
    assert "description=new description" in update_res.output


def test_cli_update_product_not_found_returns_stable_error(cli_runner):
    runner, app = cli_runner

    update_res = runner.invoke(app, ["update-product", "99999", "--description", "x"])
    assert update_res.exit_code == 1
    assert "Error: Product not found" in update_res.output
    assert "Traceback" not in update_res.output


def test_cli_update_product_template_validation_returns_stable_error(cli_runner):
    runner, app = cli_runner

    create_res_1 = runner.invoke(app, ["create-product", "prod-a", "desc a"])
    assert create_res_1.exit_code == 0
    create_res_2 = runner.invoke(app, ["create-product", "prod-b", "desc b"])
    assert create_res_2.exit_code == 0

    list_res = runner.invoke(app, ["list-products"])
    assert list_res.exit_code == 0
    lines = [ln for ln in list_res.output.strip().splitlines() if ln]
    assert len(lines) == 2
    ids_by_name = {}
    for line in lines:
        prod_id_str, prod_name = line.split(maxsplit=1)
        ids_by_name[prod_name] = int(prod_id_str)
    prod_a_id = ids_by_name["prod-a"]
    prod_b_id = ids_by_name["prod-b"]

    template_res = runner.invoke(app, ["create-template", str(prod_b_id), "registry.home:80/other/", "2.0.0"])
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    update_res = runner.invoke(app, ["update-product", str(prod_a_id), "--template-id", str(template_id)])
    assert update_res.exit_code == 1
    assert "Error: Template not found" in update_res.output
    assert "Traceback" not in update_res.output
