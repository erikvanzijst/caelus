from __future__ import annotations

from datetime import UTC, datetime

from app.models import DeploymentCreate, DeploymentORM, ProductORM, PlanORM, PlanTemplateVersionORM, BillingInterval
from app.models.core import _utcnow
from app.services import deployments, products, templates, users
from app.services.reconcile import DeploymentReconciler
from tests.provisioner_utils import FakeProvisioner


def _create_plan_template(db_session, product_id: int, storage_bytes: int | None) -> int:
    """Create a Plan + PlanTemplateVersion with a specific storage_bytes value."""
    plan = PlanORM(name=f"plan-{storage_bytes}", product_id=product_id, created_at=_utcnow())
    db_session.add(plan)
    db_session.flush()
    ptv = PlanTemplateVersionORM(
        plan_id=plan.id,
        price_cents=0,
        billing_interval=BillingInterval.MONTHLY,
        storage_bytes=storage_bytes,
        created_at=_utcnow(),
    )
    db_session.add(ptv)
    db_session.flush()
    plan.template_id = ptv.id
    db_session.commit()
    db_session.refresh(ptv)
    return ptv.id


def _seed_deployment(db_session, *, storage_bytes: int | None = 0) -> int:
    """Seed a deployment with a plan template.

    ``storage_bytes`` defaults to 0 (free-plan behaviour used by existing tests).
    Pass an explicit int to test plan storage injection, or ``None`` for a plan
    with no storage quota.
    """
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
                "properties": {
                    "message": {"type": "string"},
                    "domain": {"type": "string", "title": "hostname"},
                },
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
            system_values_json={"replicas": 1},
            values_schema_json=schema,
            health_timeout_sec=120,
        ),
    )
    product_orm = db_session.get(ProductORM, product.id)
    product_orm.template_id = template.id
    db_session.add(product_orm)
    db_session.commit()
    ptv_id = _create_plan_template(db_session, product.id, storage_bytes)
    deployment = deployments.create_deployment(
        db_session,
        payload=DeploymentCreate(
            user_id=user.id,
            desired_template_id=template.id,
            user_values_json={"user": {"message": "hello", "domain": "reconcile.example.test"}},
            plan_template_id=ptv_id,
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
    assert fake_provisioner.calls[1][1]["values"] == {
        "replicas": 1,
        "user": {"message": "hello", "domain": "reconcile.example.test"},
        "caelus": {"plan": {"storageBytes": 0, "storageSize": "0"}},
    }


def test_reconcile_delete_returns_deleted_when_marked_deleted(db_session) -> None:
    deployment_id = _seed_deployment(db_session)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None
    deployment.deleted_at = datetime.now(UTC)
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
    deployment.name = ""
    db_session.add(deployment)
    db_session.commit()

    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    deployment = db_session.get(DeploymentORM, deployment_id)
    assert deployment is not None

    assert result.status == "error"
    assert "name" in (result.last_error or "")
    assert fake_provisioner.calls == []
    assert deployment.status == "error"
    assert "name" in (deployment.last_error or "")


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


def test_reconcile_injects_plan_storage_into_helm_values(db_session) -> None:
    """Plan storage_bytes is projected into caelus.plan namespace in Helm values."""
    deployment_id = _seed_deployment(db_session, storage_bytes=10737418240)  # 10 GiB
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    assert result.status == "ready"

    values = fake_provisioner.calls[1][1]["values"]
    assert values["caelus"] == {
        "plan": {"storageBytes": 10737418240, "storageSize": "10Gi"},
    }
    # Other values still present
    assert values["replicas"] == 1
    assert values["user"]["message"] == "hello"


def test_reconcile_omits_caelus_when_storage_bytes_is_none(db_session) -> None:
    """When plan has no storage quota, caelus namespace is not injected."""
    deployment_id = _seed_deployment(db_session, storage_bytes=None)
    fake_provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=fake_provisioner)

    result = reconciler.reconcile(deployment_id)
    assert result.status == "ready"

    values = fake_provisioner.calls[1][1]["values"]
    assert "caelus" not in values
    assert values["replicas"] == 1
