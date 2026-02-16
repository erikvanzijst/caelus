from __future__ import annotations

import json

from app.db import session_scope
from app.services import templates as template_service


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


def _seed_deployment_via_services() -> tuple[int, int]:
    from app.db import session_scope
    from app.models import UserCreate, ProductCreate, ProductTemplateVersionCreate, DeploymentCreate
    from app.services import users as user_service, products as product_service, templates as template_service, \
        deployments as deployment_service

    with session_scope() as session:
        user = user_service.create_user(session, UserCreate(email="getdep@example.com"))
        product = product_service.create_product(
            session, payload=ProductCreate(name="dep-product", description="dep desc")
        )
        template = template_service.create_template(
            session,
            ProductTemplateVersionCreate(
                product_id=product.id,
                chart_ref="registry.home:80/dep/",
                chart_version="1.0.0",
            ),
        )
        deployment = deployment_service.create_deployment(
            session,
            payload=DeploymentCreate(
                user_id=user.id,
                desired_template_id=template.id,
                domainname="dep.example.com",
            ),
        )
        return user.id, deployment.id


def _get_template_from_services(product_id: int, template_id: int):
    with session_scope() as session:
        return template_service.get_template(
            session,
            product_id=product_id,
            template_id=template_id,
        )


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


def test_cli_create_template_supports_rest_extra_fields(cli_runner, tmp_path):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "template-rich", "desc"])
    assert create_res.exit_code == 0

    values_schema_file = tmp_path / "values-schema.json"
    values_schema_file.write_text(json.dumps({"type": "object", "properties": {"message": {"type": "string"}}}))

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "1",
            "registry.home:80/rich/",
            "2.1.0",
            "--chart-digest",
            "sha256:abc123",
            "--version-label",
            "stable-2.1.0",
            "--default-values-json",
            "{\"message\":\"hello\"}",
            "--values-schema-file",
            str(values_schema_file),
            "--capabilities-json",
            "{\"requires_admin_upgrade\":true}",
        ],
    )
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    template = _get_template_from_services(1, template_id)
    assert template.chart_digest == "sha256:abc123"
    assert template.version_label == "stable-2.1.0"
    assert template.default_values_json == {"message": "hello"}
    assert template.values_schema_json == {"type": "object", "properties": {"message": {"type": "string"}}}
    assert template.capabilities_json == {"requires_admin_upgrade": True}


def test_cli_create_template_invalid_json_returns_stable_error(cli_runner):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "template-invalid-json", "desc"])
    assert create_res.exit_code == 0

    result = runner.invoke(
        app,
        [
            "create-template",
            "1",
            "registry.home:80/invalid/",
            "1.0.0",
            "--default-values-json",
            "{not-json}",
        ],
    )
    assert result.exit_code == 1
    assert "Error: Invalid JSON for --default-values-json" in result.output
    assert "Traceback" not in result.output


def test_cli_create_template_rejects_both_json_and_file_for_same_field(cli_runner, tmp_path):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "template-both-inputs", "desc"])
    assert create_res.exit_code == 0

    default_values_file = tmp_path / "default-values.json"
    default_values_file.write_text(json.dumps({"message": "from-file"}))

    result = runner.invoke(
        app,
        [
            "create-template",
            "1",
            "registry.home:80/both/",
            "1.0.0",
            "--default-values-json",
            "{\"message\":\"from-inline\"}",
            "--default-values-file",
            str(default_values_file),
        ],
    )
    assert result.exit_code == 1
    assert "Error: Provide only one of --default-values-json or --default-values-file" in result.output
    assert "Traceback" not in result.output


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


def test_cli_get_user_command(cli_runner):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-user", "getuser@example.com"])
    assert create_res.exit_code == 0

    get_res = runner.invoke(app, ["get-user", "1"])
    assert get_res.exit_code == 0
    assert "getuser@example.com" in get_res.output

    miss_res = runner.invoke(app, ["get-user", "99999"])
    assert miss_res.exit_code == 1
    assert "Error: User not found" in miss_res.output
    assert "Traceback" not in miss_res.output


def test_cli_get_product_and_template_commands(cli_runner):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "get-prod", "desc"])
    assert create_res.exit_code == 0

    get_prod_res = runner.invoke(app, ["get-product", "1"])
    assert get_prod_res.exit_code == 0
    assert "get-prod" in get_prod_res.output

    template_res = runner.invoke(app, ["create-template", "1", "registry.home:80/get/", "1.0.0"])
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    get_tmpl_res = runner.invoke(app, ["get-template", "1", str(template_id)])
    assert get_tmpl_res.exit_code == 0
    assert "registry.home:80/get/" in get_tmpl_res.output

    missing_product_res = runner.invoke(app, ["get-product", "99999"])
    assert missing_product_res.exit_code == 1
    assert "Error: Product not found" in missing_product_res.output
    assert "Traceback" not in missing_product_res.output

    missing_template_res = runner.invoke(app, ["get-template", "1", "99999"])
    assert missing_template_res.exit_code == 1
    assert "Error: Template not found" in missing_template_res.output
    assert "Traceback" not in missing_template_res.output


def test_cli_get_deployment_command(cli_runner):
    runner, app = cli_runner

    user_id, deployment_id = _seed_deployment_via_services()

    get_dep_res = runner.invoke(app, ["get-deployment", str(user_id), str(deployment_id)])
    assert get_dep_res.exit_code == 0
    assert "dep.example.com" in get_dep_res.output

    missing_dep_res = runner.invoke(app, ["get-deployment", str(user_id), "99999"])
    assert missing_dep_res.exit_code == 1
    assert "Error: Deployment not found" in missing_dep_res.output
    assert "Traceback" not in missing_dep_res.output


def test_cli_create_deployment_uses_current_payload_shape(cli_runner):
    runner, app = cli_runner

    user_res = runner.invoke(app, ["create-user", "newdep@example.com"])
    assert user_res.exit_code == 0

    product_res = runner.invoke(app, ["create-product", "dep-cli-product", "dep product desc"])
    assert product_res.exit_code == 0

    template_res = runner.invoke(app, ["create-template", "1", "registry.home:80/deploy/", "1.0.0"])
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(template_id),
            "--domainname",
            "cli-audit.example.test",
        ],
    )
    assert create_dep_res.exit_code == 0
    assert "Created deployment:" in create_dep_res.output
    assert "cli-audit.example.test" in create_dep_res.output


def test_cli_create_deployment_accepts_user_values_json(cli_runner):
    runner, app = cli_runner

    user_res = runner.invoke(app, ["create-user", "depjson@example.com"])
    assert user_res.exit_code == 0

    product_res = runner.invoke(app, ["create-product", "dep-json-product", "dep json desc"])
    assert product_res.exit_code == 0

    template_res = runner.invoke(app, ["create-template", "1", "registry.home:80/deploy-json/", "1.0.0"])
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(template_id),
            "--domainname",
            "cli-json.example.test",
            "--user-values-json",
            "{\"message\":\"hi\"}",
        ],
    )
    assert create_dep_res.exit_code == 0
    assert "Created deployment:" in create_dep_res.output
    assert "cli-json.example.test" in create_dep_res.output


def test_cli_create_deployment_accepts_user_values_file(cli_runner, tmp_path):
    runner, app = cli_runner

    user_res = runner.invoke(app, ["create-user", "depfile@example.com"])
    assert user_res.exit_code == 0

    product_res = runner.invoke(app, ["create-product", "dep-file-product", "dep file desc"])
    assert product_res.exit_code == 0

    template_res = runner.invoke(app, ["create-template", "1", "registry.home:80/deploy-file/", "1.0.0"])
    assert template_res.exit_code == 0
    template_id = _get_template_id_from_create_output(template_res.output)

    values_file = tmp_path / "user-values.json"
    values_file.write_text(json.dumps({"replicas": 2, "feature": {"enabled": True}}))

    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(template_id),
            "--domainname",
            "cli-file.example.test",
            "--user-values-file",
            str(values_file),
        ],
    )
    assert create_dep_res.exit_code == 0
    assert "Created deployment:" in create_dep_res.output
    assert "cli-file.example.test" in create_dep_res.output


def test_cli_create_deployment_user_values_invalid_json_returns_stable_error(cli_runner):
    runner, app = cli_runner

    result = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            "1",
            "--domainname",
            "bad-json.example.test",
            "--user-values-json",
            "{not-json}",
        ],
    )
    assert result.exit_code == 1
    assert "Error: Invalid JSON for --user-values-json" in result.output
    assert "Traceback" not in result.output


def test_cli_create_deployment_not_found_returns_stable_error(cli_runner):
    runner, app = cli_runner

    missing_user_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "99999",
            "--desired-template-id",
            "1",
            "--domainname",
            "missing-user.example.test",
        ],
    )
    assert missing_user_res.exit_code == 1
    assert "Error: User not found" in missing_user_res.output
    assert "Traceback" not in missing_user_res.output


def test_cli_duplicate_create_commands_return_stable_errors(cli_runner):
    runner, app = cli_runner

    user_first = runner.invoke(app, ["create-user", "dup@example.com"])
    assert user_first.exit_code == 0
    user_dup = runner.invoke(app, ["create-user", "dup@example.com"])
    assert user_dup.exit_code == 1
    assert "Error: Email already in use: dup@example.com" in user_dup.output
    assert "Traceback" not in user_dup.output

    prod_first = runner.invoke(app, ["create-product", "dup-product", "desc"])
    assert prod_first.exit_code == 0
    prod_dup = runner.invoke(app, ["create-product", "dup-product", "desc"])
    assert prod_dup.exit_code == 1
    assert "Error: A product with this name already exists: dup-product" in prod_dup.output
    assert "Traceback" not in prod_dup.output


def test_cli_missing_delete_commands_return_stable_errors(cli_runner):
    runner, app = cli_runner

    delete_user_res = runner.invoke(app, ["delete-user", "999999"])
    assert delete_user_res.exit_code == 1
    assert "Error: User not found" in delete_user_res.output
    assert "Traceback" not in delete_user_res.output

    delete_product_res = runner.invoke(app, ["delete-product", "999999"])
    assert delete_product_res.exit_code == 1
    assert "Error: Product not found" in delete_product_res.output
    assert "Traceback" not in delete_product_res.output

    delete_template_res = runner.invoke(app, ["delete-template", "1", "999999"])
    assert delete_template_res.exit_code == 1
    assert "Error: Template not found" in delete_template_res.output
    assert "Traceback" not in delete_template_res.output
