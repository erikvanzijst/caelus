from __future__ import annotations

import json
from typing import Any

import yaml
from PIL import Image

from app.db import session_scope
from app.models import DeploymentORM, DeploymentReconcileJobORM
from app.services.jobs import JobService
from app.services import templates as template_service, reconcile as reconcile_service
from sqlmodel import select


def _stdout(result) -> str:
    return getattr(result, "stdout", result.output)


def _stderr(result) -> str:
    return getattr(result, "stderr", result.output)


def _parse_yaml_stdout(result) -> Any:
    return yaml.safe_load(_stdout(result))


def _seed_deployment_via_services() -> tuple[int, int]:
    from app.db import session_scope
    from app.models import UserCreate, ProductCreate, ProductTemplateVersionCreate, DeploymentCreate
    from app.services import (
        users as user_service,
        products as product_service,
        templates as template_service,
        deployments as deployment_service,
    )

    with session_scope() as session:
        user = user_service.create_user(session, UserCreate(email="getdep@example.com"))
        product = product_service.create_product(
            session, payload=ProductCreate(name="dep-product", description="dep desc")
        )
        template = template_service.create_template(
            session,
            ProductTemplateVersionCreate(
                product_id=product.id,
                chart_ref="oci://example/chart",
                chart_version="1.0.0",
                values_schema_json={
                    "type": "object",
                    "properties": {"domain": {"type": "string", "title": "hostname"}},
                },
            ),
        )
        from app.models import ProductORM
        product_orm = session.get(ProductORM, product.id)
        product_orm.template_id = template.id
        session.add(product_orm)
        session.commit()
        deployment = deployment_service.create_deployment(
            session,
            payload=DeploymentCreate(
                user_id=user.id,
                desired_template_id=template.id,
                user_values_json={"domain": "dep.example.com"},
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


def _get_deployment_by_domain(hostname: str):
    with session_scope() as session:
        return session.exec(select(DeploymentORM).where(DeploymentORM.hostname == hostname)).one_or_none()


def _get_job_reasons_for_deployment(deployment_id: int) -> list[str]:
    with session_scope() as session:
        jobs = session.exec(
            select(DeploymentReconcileJobORM)
            .where(DeploymentReconcileJobORM.deployment_id == deployment_id)
            .order_by(DeploymentReconcileJobORM.id)
        ).all()
        return [job.reason for job in jobs]


def _get_deployment_by_id(deployment_id: int) -> DeploymentORM | None:
    with session_scope() as session:
        return session.get(DeploymentORM, deployment_id)


def _mark_first_open_job_done(deployment_id: int) -> None:
    with session_scope() as session:
        job = session.exec(
            select(DeploymentReconcileJobORM)
            .where(
                DeploymentReconcileJobORM.deployment_id == deployment_id,
                DeploymentReconcileJobORM.status.in_(("queued", "running")),
            )
            .order_by(DeploymentReconcileJobORM.id)
        ).first()
        assert job is not None
        JobService(session).mark_job_done(job_id=job.id)


def _finish_reconcile(deployment_id: int) -> None:
    """Mark the first open job done and set deployment to ready (simulates reconciler)."""
    _mark_first_open_job_done(deployment_id)
    with session_scope() as session:
        dep = session.get(DeploymentORM, deployment_id)
        assert dep is not None
        dep.status = "ready"
        session.add(dep)
        session.commit()


def _mark_first_open_job_failed(deployment_id: int, error: str = "boom") -> None:
    with session_scope() as session:
        job = session.exec(
            select(DeploymentReconcileJobORM)
            .where(
                DeploymentReconcileJobORM.deployment_id == deployment_id,
                DeploymentReconcileJobORM.status.in_(("queued", "running")),
            )
            .order_by(DeploymentReconcileJobORM.id)
        ).first()
        assert job is not None
        JobService(session).mark_job_failed(job_id=job.id, error=error)


def test_cli_user_flow(cli_runner):
    runner, app = cli_runner

    # Create user
    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    created_user = _parse_yaml_stdout(result)
    assert created_user["email"] == "cli@example.com"

    # List users to verify creation (includes auto-created auth user)
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    users = _parse_yaml_stdout(result)
    emails = [u["email"] for u in users]
    assert "cli@example.com" in emails


def test_cli_product_flow(cli_runner):
    """Test creating, listing, and deleting a product via CLI."""
    runner, app = cli_runner

    # Create a product
    create_res = runner.invoke(app, ["create-product", "testprod", "A test product"])
    assert create_res.exit_code == 0
    created_product = _parse_yaml_stdout(create_res)
    assert created_product["name"] == "testprod"

    # List products to get the ID
    list_res = runner.invoke(app, ["list-products"])
    assert list_res.exit_code == 0
    products = _parse_yaml_stdout(list_res)
    assert len(products) == 1
    prod_id = products[0]["id"]

    # Delete the product
    del_res = runner.invoke(app, ["delete-product", str(prod_id)])
    assert del_res.exit_code == 0
    deleted_product = _parse_yaml_stdout(del_res)
    assert deleted_product["id"] == prod_id

    # Verify product list is empty
    list_res2 = runner.invoke(app, ["list-products"])
    assert list_res2.exit_code == 0
    assert _parse_yaml_stdout(list_res2) == []

    result = runner.invoke(app, ["create-user", "cli@example.com"])
    assert result.exit_code == 0
    assert _parse_yaml_stdout(result)["email"] == "cli@example.com"

    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    users = _parse_yaml_stdout(result)
    emails = [u["email"] for u in users]
    assert "cli@example.com" in emails


def test_cli_update_product_supports_template_and_description(cli_runner):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "updatable", "old description"])
    assert create_res.exit_code == 0

    list_res = runner.invoke(app, ["list-products"])
    assert list_res.exit_code == 0
    products = _parse_yaml_stdout(list_res)
    prod_id = products[0]["id"]

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            str(prod_id),
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    update_res = runner.invoke(
        app,
        [
            "update-product",
            str(prod_id),
            "--template-id",
            str(template_id),
            "--description",
            "new description",
        ],
    )
    assert update_res.exit_code == 0
    updated = _parse_yaml_stdout(update_res)
    assert updated["id"] == prod_id
    assert updated["template_id"] == template_id
    assert updated["description"] == "new description"


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
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "2.1.0",
            "--chart-digest",
            "sha256:abc123",
            "--version-label",
            "stable-2.1.0",
            "--system-values-json",
            '{"message":"hello"}',
            "--values-schema-file",
            str(values_schema_file),
            "--capabilities-json",
            '{"requires_admin_upgrade":true}',
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    template = _get_template_from_services(1, template_id)
    assert template.chart_digest == "sha256:abc123"
    assert template.version_label == "stable-2.1.0"
    assert template.system_values_json == {"message": "hello"}
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
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--system-values-json",
            "{not-json}",
        ],
    )
    assert result.exit_code == 1
    assert "Error: Invalid JSON for --system-values-json" in result.output
    assert "Traceback" not in result.output


def test_cli_create_template_rejects_both_json_and_file_for_same_field(cli_runner, tmp_path):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-product", "template-both-inputs", "desc"])
    assert create_res.exit_code == 0

    system_values_file = tmp_path / "system-values.json"
    system_values_file.write_text(json.dumps({"message": "from-file"}))

    result = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--system-values-json",
            '{"message":"from-inline"}',
            "--system-values-file",
            str(system_values_file),
        ],
    )
    assert result.exit_code == 1
    assert "Error: Provide only one of --system-values-json or --system-values-file" in result.output
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
    products = _parse_yaml_stdout(list_res)
    assert len(products) == 2
    ids_by_name = {product["name"]: product["id"] for product in products}
    prod_a_id = ids_by_name["prod-a"]
    prod_b_id = ids_by_name["prod-b"]

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            str(prod_b_id),
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "2.0.0",
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    update_res = runner.invoke(app, ["update-product", str(prod_a_id), "--template-id", str(template_id)])
    assert update_res.exit_code == 1
    assert "Error: Template not found" in update_res.output
    assert "Traceback" not in update_res.output


def test_cli_get_user_command(cli_runner):
    runner, app = cli_runner

    create_res = runner.invoke(app, ["create-user", "getuser@example.com"])
    assert create_res.exit_code == 0
    user_id = _parse_yaml_stdout(create_res)["id"]

    get_res = runner.invoke(app, ["get-user", str(user_id)])
    assert get_res.exit_code == 0
    assert _parse_yaml_stdout(get_res)["email"] == "getuser@example.com"

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
    assert _parse_yaml_stdout(get_prod_res)["name"] == "get-prod"

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--values-schema-json",
            '{"type":"object","properties":{"user":{"type":"object"}}}',
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    get_tmpl_res = runner.invoke(app, ["get-template", "1", str(template_id)])
    assert get_tmpl_res.exit_code == 0
    assert _parse_yaml_stdout(get_tmpl_res)["chart_ref"] == "oci://example/chart"

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
    assert _parse_yaml_stdout(get_dep_res)["hostname"] == "dep.example.com"

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

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--values-schema-json",
            '{"type":"object","properties":{"domain":{"type":"string","title":"hostname"}}}',
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    update_prod_res = runner.invoke(app, ["update-product", "1", "--template-id", str(template_id)])
    assert update_prod_res.exit_code == 0

    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(template_id),
            "--user-values-json",
            '{"domain":"cli-audit.example.test"}',
        ],
    )
    assert create_dep_res.exit_code == 0
    created_deployment = _parse_yaml_stdout(create_dep_res)
    assert created_deployment["hostname"] == "cli-audit.example.test"


def test_cli_create_deployment_accepts_user_values_json(cli_runner):
    runner, app = cli_runner

    user_res = runner.invoke(app, ["create-user", "depjson@example.com"])
    assert user_res.exit_code == 0

    product_res = runner.invoke(app, ["create-product", "dep-json-product", "dep json desc"])
    assert product_res.exit_code == 0

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--values-schema-json",
            '{"type":"object","properties":{"domain":{"type":"string","title":"hostname"},"message":{"type":"string"}}}',
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    update_prod_res = runner.invoke(app, ["update-product", "1", "--template-id", str(template_id)])
    assert update_prod_res.exit_code == 0

    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(template_id),
            "--user-values-json",
            '{"domain":"cli-json.example.test","message":"hi"}',
        ],
    )
    assert create_dep_res.exit_code == 0
    created_deployment = _parse_yaml_stdout(create_dep_res)
    assert created_deployment["hostname"] == "cli-json.example.test"
    assert created_deployment["user_values_json"] == {"domain": "cli-json.example.test", "message": "hi"}


def test_cli_create_deployment_accepts_user_values_file(cli_runner, tmp_path):
    runner, app = cli_runner

    user_res = runner.invoke(app, ["create-user", "depfile@example.com"])
    assert user_res.exit_code == 0

    product_res = runner.invoke(app, ["create-product", "dep-file-product", "dep file desc"])
    assert product_res.exit_code == 0

    template_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--values-schema-json",
            '{"type":"object","properties":{"domain":{"type":"string","title":"hostname"},"replicas":{"type":"integer"},"feature":{"type":"object"}}}',
        ],
    )
    assert template_res.exit_code == 0
    template_id = _parse_yaml_stdout(template_res)["id"]

    update_prod_res = runner.invoke(app, ["update-product", "1", "--template-id", str(template_id)])
    assert update_prod_res.exit_code == 0

    # TODO: use `with NamedTemporaryFile()`
    values_file = tmp_path / "user-values.json"
    values_file.write_text(
        json.dumps({"domain": "cli-file.example.test", "replicas": 2, "feature": {"enabled": True}})
    )

    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(template_id),
            "--user-values-file",
            str(values_file),
        ],
    )
    assert create_dep_res.exit_code == 0
    created_deployment = _parse_yaml_stdout(create_dep_res)
    assert created_deployment["hostname"] == "cli-file.example.test"
    assert created_deployment["user_values_json"] == {
        "domain": "cli-file.example.test",
        "replicas": 2,
        "feature": {"enabled": True},
    }


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
        ],
    )
    assert missing_user_res.exit_code == 1
    assert "Error: User not found" in missing_user_res.output
    assert "Traceback" not in missing_user_res.output


def test_cli_rejects_removed_hostname_write_option(cli_runner):
    runner, app = cli_runner

    create_with_domain_option = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            "1",
            "--hostname",
            "deprecated.example.test",
        ],
    )
    assert create_with_domain_option.exit_code != 0
    assert "No such option: --hostname" in create_with_domain_option.output

    update_with_domain_option = runner.invoke(
        app,
        [
            "update-deployment",
            "--user-id",
            "1",
            "--deployment-id",
            "1",
            "--desired-template-id",
            "2",
            "--hostname",
            "deprecated.example.test",
        ],
    )
    assert update_with_domain_option.exit_code != 0
    assert "No such option: --hostname" in update_with_domain_option.output


def test_cli_upgrade_deployment_and_delete_enqueue_jobs(cli_runner):
    runner, app = cli_runner

    user_res = runner.invoke(app, ["create-user", "upgradecli@example.com"])
    assert user_res.exit_code == 0

    product_res = runner.invoke(app, ["create-product", "upgrade-cli-product", "desc"])
    assert product_res.exit_code == 0

    tmpl1_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "1.0.0",
            "--values-schema-json",
            '{"type":"object","properties":{"domain":{"type":"string","title":"hostname"}}}',
        ],
    )
    assert tmpl1_res.exit_code == 0
    tmpl1_id = _parse_yaml_stdout(tmpl1_res)["id"]

    tmpl2_res = runner.invoke(
        app,
        [
            "create-template",
            "--product-id",
            "1",
            "--chart-ref",
            "oci://example/chart",
            "--chart-version",
            "2.0.0",
            "--values-schema-json",
            '{"type":"object","properties":{"domain":{"type":"string","title":"hostname"}}}',
        ],
    )
    assert tmpl2_res.exit_code == 0
    tmpl2_id = _parse_yaml_stdout(tmpl2_res)["id"]

    update_prod_res = runner.invoke(app, ["update-product", "1", "--template-id", str(tmpl1_id)])
    assert update_prod_res.exit_code == 0

    domain = "upgrade-cli.example.test"
    create_dep_res = runner.invoke(
        app,
        [
            "create-deployment",
            "--user-id",
            "1",
            "--desired-template-id",
            str(tmpl1_id),
            "--user-values-json",
            json.dumps({"domain": domain}),
        ],
    )
    assert create_dep_res.exit_code == 0

    deployment = _get_deployment_by_domain(domain)
    assert deployment is not None
    dep_id = deployment.id
    assert dep_id is not None
    _finish_reconcile(dep_id)

    upgrade_res = runner.invoke(
        app,
        [
            "update-deployment",
            "--user-id",
            "1",
            "--deployment-id",
            str(dep_id),
            "--desired-template-id",
            str(tmpl2_id),
        ],
    )
    assert upgrade_res.exit_code == 0
    upgraded = _parse_yaml_stdout(upgrade_res)
    assert upgraded["id"] == dep_id
    assert upgraded["desired_template_id"] == tmpl2_id
    _mark_first_open_job_done(dep_id)

    delete_res = runner.invoke(app, ["delete-deployment", "1", str(dep_id)])
    assert delete_res.exit_code == 0
    deleted = _parse_yaml_stdout(delete_res)
    assert deleted["id"] == dep_id

    reasons = _get_job_reasons_for_deployment(dep_id)
    assert reasons == ["create", "update", "delete"]


def test_cli_duplicate_create_commands_return_stable_errors(cli_runner):
    runner, app = cli_runner

    user_first = runner.invoke(app, ["create-user", "dup@example.com"])
    assert user_first.exit_code == 0
    user_dup = runner.invoke(app, ["create-user", "dup@example.com"])
    assert user_dup.exit_code == 1
    assert _stdout(user_dup) == ""
    assert "Error: Email already in use: dup@example.com" in _stderr(user_dup)
    assert "Traceback" not in _stderr(user_dup)

    prod_first = runner.invoke(app, ["create-product", "dup-product", "desc"])
    assert prod_first.exit_code == 0
    prod_dup = runner.invoke(app, ["create-product", "dup-product", "desc"])
    assert prod_dup.exit_code == 1
    assert _stdout(prod_dup) == ""
    assert "Error: A product with this name already exists: dup-product" in _stderr(prod_dup)
    assert "Traceback" not in _stderr(prod_dup)


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


def test_cli_reconcile_command_reconciles_deployment(cli_runner, monkeypatch):
    runner, app = cli_runner
    _, deployment_id = _seed_deployment_via_services()

    class _FakeProvisioner:
        def ensure_namespace(self, *, name: str):
            return None

        def helm_upgrade_install(self, **kwargs):
            return None

        def helm_uninstall(self, **kwargs):
            return None

        def delete_namespace(self, *, name: str):
            return None

    monkeypatch.setattr(reconcile_service, "default_provisioner", _FakeProvisioner())
    result = runner.invoke(app, ["reconcile", str(deployment_id)])

    assert result.exit_code == 0
    reconciled = _parse_yaml_stdout(result)
    assert reconciled["status"] == "ready"
    assert reconciled["applied_template_id"] is not None

    deployment = _get_deployment_by_id(deployment_id)
    assert deployment is not None
    assert deployment.status == "ready"
    assert deployment.applied_template_id == deployment.desired_template_id
    assert deployment.last_error is None
    assert deployment.last_reconcile_at is not None


def test_cli_reconcile_command_not_found_returns_stable_error(cli_runner):
    runner, app = cli_runner
    result = runner.invoke(app, ["reconcile", "999999"])
    assert result.exit_code == 1
    assert "Error: Deployment not found" in result.output
    assert "Traceback" not in result.output


def test_cli_worker_processes_jobs_and_streams_yaml(cli_runner, monkeypatch):
    runner, app = cli_runner

    # Seed deployment via services to ensure a queued create job exists
    user_id, deployment_id = _seed_deployment_via_services()

    # Ensure fake provisioner to avoid external calls
    class _FakeProvisioner:
        def ensure_namespace(self, *, name: str):
            return None

        def helm_upgrade_install(self, **kwargs):
            return None

        def helm_uninstall(self, **kwargs):
            return None

        def delete_namespace(self, *, name: str):
            return None

    monkeypatch.setenv("CAELUS_WORKER_ID", "worker-test")
    monkeypatch.setattr(reconcile_service, "default_provisioner", _FakeProvisioner())

    result = runner.invoke(app, ["worker", "-n", "1"])
    assert result.exit_code == 0
    # Expect one YAML document (id/status present)
    lines = [line for line in result.output.strip().splitlines() if line]
    assert any(line.startswith("id:") for line in lines)
    assert any("status: done" in line for line in lines)

    # With no remaining jobs and follow disabled, worker should exit cleanly
    result_empty = runner.invoke(app, ["worker", "-n", "1"])
    assert result_empty.exit_code == 0
    assert result_empty.output.strip() == ""


def test_cli_worker_marks_failure_and_continues(cli_runner, monkeypatch):
    runner, app = cli_runner

    user_id, deployment_id = _seed_deployment_via_services()

    class _FailingProvisioner:
        def ensure_namespace(self, *, name: str):
            raise RuntimeError("fail")

        def helm_upgrade_install(self, **kwargs):
            raise RuntimeError("fail")

        def helm_uninstall(self, **kwargs):
            raise RuntimeError("fail")

        def delete_namespace(self, *, name: str):
            raise RuntimeError("fail")

    monkeypatch.setenv("CAELUS_WORKER_ID", "worker-fail")
    monkeypatch.setattr(reconcile_service, "default_provisioner", _FailingProvisioner())

    result = runner.invoke(app, ["worker", "-n", "1"])
    assert result.exit_code == 0
    lines = [line for line in result.output.strip().splitlines() if line]
    assert any("status: failed" in line for line in lines)

    # Ensure job is marked failed in DB
    with session_scope() as session:
        jobs = JobService(session).list_jobs(deployment_id=deployment_id, statuses=["failed"], limit=10)
        assert len(jobs) == 1


def test_cli_jobs_lists_open_and_filters_status(cli_runner):
    runner, app = cli_runner

    user_id, deployment_id = _seed_deployment_via_services()

    # initial queued create job should appear
    result = runner.invoke(app, ["jobs", "-d", str(deployment_id)])
    assert result.exit_code == 0
    jobs_list = _parse_yaml_stdout(result)
    assert len(jobs_list) >= 1
    assert all(job["status"] in ("queued", "running") for job in jobs_list)

    # mark it failed, then list failed-only
    _mark_first_open_job_failed(deployment_id)
    result_failed = runner.invoke(app, ["jobs", "--failed", "-d", str(deployment_id)])
    assert result_failed.exit_code == 0
    failed_jobs = _parse_yaml_stdout(result_failed)
    assert all(job["status"] == "failed" for job in failed_jobs)


def test_cli_create_product_with_icon(cli_runner, tmp_path):
    """Test creating a product with an icon via CLI."""
    runner, app = cli_runner

    icon_path = tmp_path / "test_icon.png"

    img = Image.new("RGB", (100, 100), color="red")
    img.save(icon_path)

    create_res = runner.invoke(
        app,
        ["create-product", "icon-prod", "Product with icon", "--icon", str(icon_path)],
    )
    assert create_res.exit_code == 0
    product = _parse_yaml_stdout(create_res)
    assert product["name"] == "icon-prod"
    assert product["icon_url"] is not None
    assert "/api/static/icons/" in product["icon_url"]


def test_cli_create_product_without_icon(cli_runner):
    """Test creating a product without an icon via CLI."""
    runner, app = cli_runner

    create_res = runner.invoke(
        app,
        ["create-product", "noicon-prod", "Product without icon"],
    )
    assert create_res.exit_code == 0
    product = _parse_yaml_stdout(create_res)
    assert product["name"] == "noicon-prod"
    assert product["icon_url"] is None


# ── CLI authentication tests ──────────────────────────────────────────


def test_cli_auth_via_env_var(cli_runner):
    """CAELUS_USER_EMAIL env var authenticates the CLI user."""
    runner, app = cli_runner
    # The fixture sets CAELUS_USER_EMAIL=cli-test@example.com
    # Running any command should auto-create that user
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 0
    users = _parse_yaml_stdout(result)
    emails = [u["email"] for u in users]
    assert "cli-test@example.com" in emails


def test_cli_auth_as_user_override(cli_runner, monkeypatch):
    """--as-user flag overrides CAELUS_USER_EMAIL."""
    runner, app = cli_runner
    # Even though CAELUS_USER_EMAIL=cli-test@example.com, --as-user wins
    result = runner.invoke(app, ["--as-user", "override@example.com", "list-users"])
    assert result.exit_code == 0
    users = _parse_yaml_stdout(result)
    emails = [u["email"] for u in users]
    assert "override@example.com" in emails


def test_cli_auth_missing_email_errors(cli_runner, monkeypatch):
    """CLI commands fail with clear error when no email is configured."""
    runner, app = cli_runner
    monkeypatch.delenv("CAELUS_USER_EMAIL", raising=False)
    result = runner.invoke(app, ["list-users"])
    assert result.exit_code == 1
    assert "No user email configured" in result.output
    assert "CAELUS_USER_EMAIL" in result.output
