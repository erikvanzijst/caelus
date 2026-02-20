from __future__ import annotations

from datetime import datetime

from app.models import DeploymentCreate, DeploymentORM
from app.services import deployments, products, templates, users
from app.services.reconcile import DeploymentReconciler
from tests.provisioner_utils import FakeProvisioner


def _seed_deployment(db_session) -> int:
    user = users.create_user(db_session, payload=users.UserCreate(email="reconcile-user@example.com"))
    product = products.create_product(
        db_session,
        payload=products.ProductCreate(name="reconcile-product", description="desc"),
    )
    schema = {
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
    }
    template = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="oci://example/chart",
            chart_version="1.2.3",
            default_values_json={"replicas": 1},
            values_schema_json=schema,
            health_timeout_sec=120,
        ),
    )
    deployment = deployments.create_deployment(
        db_session,
        payload=DeploymentCreate(
            user_id=user.id,
            desired_template_id=template.id,
            domainname="reconcile.example.test",
            user_values_json={"message": "hello"},
        ),
    )
    return deployment.id


def test_reconcile_apply_happy_path_returns_ready_and_applied_template(db_session) -> None:
    deployment_id = _seed_deployment(db_session)
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None

    assert result.status == "ready"
    assert result.applied_template_id == deployment.desired_template_id
    assert result.last_error is None
    assert result.last_reconcile_at is not None
    assert deployment.status == "ready"
    assert deployment.applied_template_id == deployment.desired_template_id
    assert fake_provisioner.calls[0][0] == "ensure_namespace"
    assert fake_provisioner.calls[1][0] == "helm_upgrade_install"
    assert fake_provisioner.calls[1][1]["values"] == {"replicas": 1, "user": {"message": "hello"}}


def test_reconcile_delete_returns_deleted_when_marked_deleted(db_session) -> None:
    deployment_id = _seed_deployment(db_session)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None
    deployment.deleted_at = datetime.utcnow()
    db_session.add(deployment)
    db_session.commit()

    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None

    assert result.status == "deleted"
    assert deployment.status == "deleted"
    assert result.last_error is None
    assert [name for name, _ in fake_provisioner.calls] == [
        "helm_uninstall",
        "delete_namespace",
    ]


def test_reconcile_validation_failure_returns_error_and_persists(db_session) -> None:
    deployment_id = _seed_deployment(db_session)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None
    deployment.deployment_uid = ""
    db_session.add(deployment)
    db_session.commit()

    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None

    assert result.status == "error"
    assert "deployment_uid" in (result.last_error or "")
    assert fake_provisioner.calls == []
    assert deployment.status == "error"
    assert "deployment_uid" in (deployment.last_error or "")


def test_reconcile_schema_validation_failure_returns_error_result(db_session) -> None:
    deployment_id = _seed_deployment(db_session)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None
    deployment.user_values_json = {"message": 123}
    db_session.add(deployment)
    db_session.commit()

    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None

    assert result.status == "error"
    assert result.last_error is not None
    assert "invalid" in result.last_error
    assert fake_provisioner.calls == []
    assert deployment.status == "error"
