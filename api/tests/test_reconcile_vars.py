"""Materializing a release's vars into the tenant's namespace.

What matters here is mostly what does *not* happen: no value in the Helm
values, no value in a log record, and no Secret at all when a release carries
no vars.
"""

from __future__ import annotations

import json
import logging

import pytest
from cryptography.fernet import Fernet

from app.config import CaelusSettings
from app.models import (
    BillingInterval,
    DeploymentCreate,
    DeploymentORM,
    PlanORM,
    PlanTemplateVersionORM,
    ProductORM,
    VarWrite,
)
from app.models.core import _utcnow
from app.services import deployments, products, templates, var_crypto
from app.services import vars as vars_service
from app.services.reconcile import DeploymentReconciler, vars_secret_name
from tests.conftest import make_accepted_user
from tests.provisioner_utils import FakeProvisioner

SECRET = "hunter2-swordfish"

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "host": {"type": "string", "title": "hostname"},
        "LOG_LEVEL": {"type": "string", "x-caelus-target": "runtime"},
        "ADMIN_TOKEN": {
            "type": "string",
            "x-caelus-target": "runtime",
            "x-caelus-sensitive": True,
        },
    },
}


@pytest.fixture(autouse=True)
def _settings(monkeypatch):
    monkeypatch.setattr(
        "app.services.reconcile.get_settings",
        lambda: CaelusSettings(wildcard_domains=[], domain="", _env_file=None),
    )


def _seed(db_session, *, vars: dict | None = None):
    user = make_accepted_user(db_session, "vars-reconcile@example.com")
    product = products.create_product(
        db_session, payload=products.ProductCreate(name="vars-product", description="d")
    )
    template = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="oci://example/chart",
            chart_version="1.2.3",
            system_values_json={"replicas": 1},
            values_schema_json=SCHEMA,
        ),
    )
    product_orm = db_session.get(ProductORM, product.id)
    product_orm.template_id = template.id
    db_session.add(product_orm)
    db_session.commit()

    plan = PlanORM(name="plan", product_id=product.id, created_at=_utcnow())
    db_session.add(plan)
    db_session.flush()
    ptv = PlanTemplateVersionORM(
        plan_id=plan.id,
        price_cents=0,
        billing_interval=BillingInterval.MONTHLY,
        storage_bytes=0,
        created_at=_utcnow(),
    )
    db_session.add(ptv)
    db_session.flush()
    plan.template_id = ptv.id
    db_session.commit()

    return deployments.create_deployment(
        db_session,
        payload=DeploymentCreate(
            user_id=user.id,
            desired_template_id=template.id,
            user_values_json={"host": "vars.example.test"},
            plan_template_id=ptv.id,
            vars=vars or {},
        ),
    ).deployment.id


def _helm_values(provisioner: FakeProvisioner) -> dict:
    return next(c[1]["values"] for c in provisioner.calls if c[0] == "helm_upgrade_install")


def _secrets(provisioner: FakeProvisioner) -> list[dict]:
    return [c[1] for c in provisioner.calls if c[0] == "upsert_secret"]


def test_a_release_with_vars_publishes_a_secret_before_helm(db_session):
    deployment_id = _seed(
        db_session,
        vars={
            "LOG_LEVEL": VarWrite(value="debug"),
            "ADMIN_TOKEN": VarWrite(value=SECRET),
        },
    )
    provisioner = FakeProvisioner()

    DeploymentReconciler(session=db_session, provisioner=provisioner).reconcile(deployment_id)

    deployment = db_session.get(DeploymentORM, deployment_id)
    secret = _secrets(provisioner)[0]
    assert secret["name"] == vars_secret_name(deployment) == f"{deployment.name}-vars"
    assert secret["namespace"] == deployment.namespace
    assert secret["string_data"] == {"LOG_LEVEL": "debug", "ADMIN_TOKEN": SECRET}

    # Before Helm, so no pod ever starts expecting a Secret that is not there.
    order = [c[0] for c in provisioner.calls]
    assert order.index("upsert_secret") < order.index("helm_upgrade_install")
    assert order.index("ensure_namespace") < order.index("upsert_secret")


def test_the_merged_values_carry_the_name_and_no_value(db_session):
    deployment_id = _seed(
        db_session,
        vars={"LOG_LEVEL": VarWrite(value="debug"), "ADMIN_TOKEN": VarWrite(value=SECRET)},
    )
    provisioner = FakeProvisioner()

    DeploymentReconciler(session=db_session, provisioner=provisioner).reconcile(deployment_id)

    deployment = db_session.get(DeploymentORM, deployment_id)
    values = _helm_values(provisioner)
    assert values["caelus"]["vars"] == {"secretName": vars_secret_name(deployment)}
    # Merged values are logged in full and persisted by Helm into a
    # tenant-namespace object, so no value may travel through them.
    serialized = json.dumps(values)
    assert SECRET not in serialized
    assert "debug" not in serialized


def test_a_known_plaintext_reaches_no_log_record(db_session, caplog):
    deployment_id = _seed(db_session, vars={"ADMIN_TOKEN": VarWrite(value=SECRET)})
    provisioner = FakeProvisioner()

    with caplog.at_level(logging.DEBUG):
        DeploymentReconciler(session=db_session, provisioner=provisioner).reconcile(deployment_id)

    assert SECRET not in caplog.text
    # And it did reach the Secret, so the assertion above is not vacuous.
    assert _secrets(provisioner)[0]["string_data"]["ADMIN_TOKEN"] == SECRET


def test_a_release_with_no_vars_produces_no_secret_and_no_block(db_session):
    deployment_id = _seed(db_session)
    provisioner = FakeProvisioner()

    DeploymentReconciler(session=db_session, provisioner=provisioner).reconcile(deployment_id)

    assert _secrets(provisioner) == []
    assert "vars" not in _helm_values(provisioner).get("caelus", {})


def test_the_secret_name_is_stable_across_releases(db_session):
    """Updated in place, rather than one Secret accumulating per release."""
    deployment_id = _seed(db_session, vars={"LOG_LEVEL": VarWrite(value="debug")})
    provisioner = FakeProvisioner()
    reconciler = DeploymentReconciler(session=db_session, provisioner=provisioner)
    reconciler.reconcile(deployment_id)

    deployment = db_session.get(DeploymentORM, deployment_id)
    vars_service.write_vars(
        db_session,
        deployment=deployment,
        actor=deployment.user,
        entries={"LOG_LEVEL": VarWrite(value="trace")},
    )
    vars_service.snapshot_release(
        db_session,
        release_id=deployment.desired_release_id,
        deployment_id=deployment.id,
    )
    db_session.commit()
    reconciler.reconcile(deployment_id)

    names = {secret["name"] for secret in _secrets(provisioner)}
    assert names == {f"{deployment.name}-vars"}


def test_the_applied_snapshot_is_the_releases_not_head(db_session):
    """A var written after the release was created waits for the next one."""
    deployment_id = _seed(db_session, vars={"LOG_LEVEL": VarWrite(value="debug")})
    deployment = db_session.get(DeploymentORM, deployment_id)
    vars_service.write_vars(
        db_session,
        deployment=deployment,
        actor=deployment.user,
        entries={"LOG_LEVEL": VarWrite(value="trace")},
    )
    db_session.commit()

    provisioner = FakeProvisioner()
    DeploymentReconciler(session=db_session, provisioner=provisioner).reconcile(deployment_id)

    assert _secrets(provisioner)[0]["string_data"] == {"LOG_LEVEL": "debug"}


def test_an_undecryptable_row_fails_the_reconcile_and_writes_nothing(db_session, monkeypatch):
    """E11: a partial Secret would start a pod missing some of its variables."""
    deployment_id = _seed(
        db_session,
        vars={"LOG_LEVEL": VarWrite(value="debug"), "ADMIN_TOKEN": VarWrite(value=SECRET)},
    )
    stored_key_id = var_crypto.current_key_id()

    # The worker comes up holding a different key than the one that encrypted.
    monkeypatch.setattr(
        "app.services.var_crypto.get_settings",
        lambda: CaelusSettings(
            var_encryption_keys=[Fernet.generate_key().decode()], _env_file=None
        ),
    )
    var_crypto.get_keyring.cache_clear()

    provisioner = FakeProvisioner()
    result = DeploymentReconciler(session=db_session, provisioner=provisioner).reconcile(
        deployment_id
    )

    assert result.status == "error"
    assert stored_key_id in result.last_error
    assert _secrets(provisioner) == []
    assert [c[0] for c in provisioner.calls].count("helm_upgrade_install") == 0

    var_crypto.get_keyring.cache_clear()
