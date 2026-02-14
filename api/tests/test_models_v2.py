from app.models import (
    UserCreate,
    ProductTemplateVersionCreate,
    DeploymentCreate,
    DeploymentRead,
    DeploymentUpdate,
    DeploymentUpgrade,
    DeploymentReconcileJobORM,
)


def test_user_create_defaults_is_admin_false() -> None:
    user = UserCreate(email="modelv2@example.com")
    assert user.is_admin is False


def test_product_template_v2_fields_supported() -> None:
    payload = ProductTemplateVersionCreate.model_validate(
        {
            "product_id": 10,
            "docker_image_url": "legacy:latest",
            "version_label": "hello-static-0.1.0",
            "package_type": "helm-chart",
            "chart_ref": "oci://registry.example.com/hello-static",
            "chart_version": "0.1.0",
            "chart_digest": "sha256:abc",
            "default_values_json": {"user": {"message": "hello"}},
            "values_schema_json": {"type": "object"},
            "capabilities_json": {"requires_admin_upgrade": True},
            "health_timeout_sec": 600,
        }
    )
    assert payload.package_type == "helm-chart"
    assert payload.chart_ref == "oci://registry.example.com/hello-static"
    assert payload.default_values_json == {"user": {"message": "hello"}}


def test_deployment_create_supports_user_values_alias() -> None:
    payload = DeploymentCreate.model_validate(
        {
            "user_id": 1,
            "template_id": 2,
            "domainname": "cloud.example.com",
            "user_values": {"message": "hi"},
        }
    )
    assert payload.user_values_json == {"message": "hi"}
    dumped = payload.model_dump(by_alias=True)
    assert dumped["user_values"] == {"message": "hi"}


def test_deployment_update_and_upgrade_models() -> None:
    upd = DeploymentUpdate.model_validate({"domainname": "new.example.com", "user_values": {"message": "x"}})
    assert upd.domainname == "new.example.com"
    assert upd.user_values_json == {"message": "x"}

    upg = DeploymentUpgrade(template_id=99)
    assert upg.template_id == 99


def test_deployment_read_has_new_state_fields() -> None:
    fields = set(DeploymentRead.model_fields.keys())
    for expected in (
        "deployment_uid",
        "namespace_name",
        "release_name",
        "desired_template_id",
        "applied_template_id",
        "status",
        "generation",
        "last_error",
        "last_reconcile_at",
        "user_values_json",
    ):
        assert expected in fields


def test_reconcile_job_model_has_required_fields() -> None:
    fields = set(DeploymentReconcileJobORM.model_fields.keys())
    for expected in (
        "deployment_id",
        "reason",
        "status",
        "run_after",
        "attempt",
        "locked_by",
        "locked_at",
        "last_error",
        "created_at",
        "updated_at",
    ):
        assert expected in fields

