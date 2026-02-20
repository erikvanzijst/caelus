from __future__ import annotations

from datetime import datetime

from app.models import DeploymentORM, ProductORM, ProductTemplateVersionORM, UserORM
from app.services.reconcile import DeploymentReconciler


class FakeProvisioner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.raise_on_upgrade: Exception | None = None

    def ensure_namespace(self, *, name: str):
        self.calls.append(("ensure_namespace", {"name": name}))
        return None

    def helm_upgrade_install(
        self,
        *,
        release_name: str,
        namespace: str,
        chart_ref: str,
        chart_version: str,
        chart_digest: str | None,
        values: dict,
        timeout: int,
        atomic: bool,
        wait: bool,
    ):
        self.calls.append(
            (
                "helm_upgrade_install",
                {
                    "release_name": release_name,
                    "namespace": namespace,
                    "chart_ref": chart_ref,
                    "chart_version": chart_version,
                    "chart_digest": chart_digest,
                    "values": values,
                    "timeout": timeout,
                    "atomic": atomic,
                    "wait": wait,
                },
            )
        )
        if self.raise_on_upgrade is not None:
            raise self.raise_on_upgrade
        return None

    def helm_uninstall(self, *, release_name: str, namespace: str, timeout: int, wait: bool):
        self.calls.append(
            (
                "helm_uninstall",
                {"release_name": release_name, "namespace": namespace, "timeout": timeout, "wait": wait},
            )
        )
        return None

    def delete_namespace(self, *, name: str):
        self.calls.append(("delete_namespace", {"name": name}))
        return None


def _build_deployment(
    *,
    deleted_at: datetime | None = None,
    user_values_json: dict | None = None,
    values_schema_json: dict | None = None,
):
    user = UserORM(id=1, email="reconcile-user@example.com")
    product = ProductORM(id=1, name="reconcile-product", description="desc")
    template = ProductTemplateVersionORM(
        id=10,
        product_id=1,
        chart_ref="oci://example/chart",
        chart_version="1.2.3",
        default_values_json={"replicas": 1},
        values_schema_json=values_schema_json
        or {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "additionalProperties": False,
                },
                "replicas": {"type": "integer"},
            },
            "additionalProperties": False,
        },
        health_timeout_sec=120,
        product=product,
    )
    return DeploymentORM(
        id=77,
        user_id=1,
        desired_template_id=10,
        applied_template_id=None,
        domainname="reconcile.example.test",
        deployment_uid="reconcile-product-reconcile-user-abc123",
        user_values_json=user_values_json or {"message": "hello"},
        status="pending",
        generation=1,
        deleted_at=deleted_at,
        user=user,
        desired_template=template,
        applied_template=None,
    )


def test_reconcile_apply_happy_path_returns_ready_and_applied_template() -> None:
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(provisioner=fake_provisioner)
    deployment = _build_deployment()

    result = reconciler.reconcile(deployment)

    assert result.status == "ready"
    assert result.applied_template_id == deployment.desired_template_id
    assert result.last_error is None
    assert result.last_reconcile_at is not None
    assert fake_provisioner.calls[0][0] == "ensure_namespace"
    assert fake_provisioner.calls[1][0] == "helm_upgrade_install"
    assert fake_provisioner.calls[1][1]["values"] == {"replicas": 1, "user": {"message": "hello"}}


def test_reconcile_delete_returns_deleted_when_namespace_gone() -> None:
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(provisioner=fake_provisioner)
    deployment = _build_deployment(deleted_at=datetime.utcnow())

    result = reconciler.reconcile(deployment)

    assert result.status == "deleted"
    assert result.last_error is None
    assert [name for name, _ in fake_provisioner.calls] == [
        "helm_uninstall",
        "delete_namespace",
    ]


def test_reconcile_missing_required_relationship_returns_error_result() -> None:
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(provisioner=fake_provisioner)
    deployment = _build_deployment()
    deployment.desired_template = None

    result = reconciler.reconcile(deployment)

    assert result.status == "error"
    assert "desired_template" in (result.last_error or "")
    assert fake_provisioner.calls == []


def test_reconcile_schema_validation_failure_returns_error_result() -> None:
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(provisioner=fake_provisioner)
    deployment = _build_deployment(user_values_json={"message": 123})

    result = reconciler.reconcile(deployment)

    assert result.status == "error"
    assert result.last_error is not None
    assert "invalid" in result.last_error
    assert fake_provisioner.calls == []
