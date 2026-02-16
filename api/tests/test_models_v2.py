from app.models import (
    ProductTemplateVersionCreate,
    DeploymentCreate,
    DeploymentRead,
    DeploymentReconcileJobORM,
)


def test_product_template_v2_fields_supported() -> None:
    payload = ProductTemplateVersionCreate.model_validate(
        {
            "product_id": 10,
            "version_label": "hello-static-0.1.0",
            "chart_ref": "oci://registry.example.com/hello-static",
            "chart_version": "0.1.0",
            "default_values_json": {"user": {"message": "hello"}},
            "values_schema_json": {"type": "object"},
            "capabilities_json": {"requires_admin_upgrade": True},
            "health_timeout_sec": 600,
        }
    )
    assert payload.chart_ref == "oci://registry.example.com/hello-static"
    assert payload.default_values_json == {"user": {"message": "hello"}}


def test_deployment_create_supports_user_values_alias() -> None:
    payload = DeploymentCreate.model_validate(
        {
            "user_id": 1,
            "desired_template_id": 2,
            "domainname": "cloud.example.com",
            "user_values_json": {"message": "hi"},
        }
    )
    assert payload.user_values_json == {"message": "hi"}


def test_deployment_read_has_new_state_fields() -> None:
    fields = set(DeploymentRead.model_fields.keys())
    for expected in (
        "deployment_uid",
        "desired_template",
        "applied_template",
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

