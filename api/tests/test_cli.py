from __future__ import annotations


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
    lines = [ln for ln in list_res.output.strip().splitlines() if ln]
    assert len(lines) == 1
    prod_id_str, prod_name = lines[0].split(maxsplit=1)
    assert prod_name == "testprod"
    prod_id = int(prod_id_str)

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
