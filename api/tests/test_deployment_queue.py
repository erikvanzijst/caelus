from __future__ import annotations

import pytest
from sqlmodel import select

from app.models import DeploymentReconcileJobORM
from app.services import deployments, jobs, products, templates, users
from app.services.errors import DeploymentInProgressException, IntegrityException
from app.services.reconcile_constants import DEPLOYMENT_STATUS_PROVISIONING, DEPLOYMENT_STATUS_DELETING


def _setup_user_and_templates(db_session):
    user = users.create_user(db_session, payload=users.UserCreate(email="queue-user@example.com"))
    product = products.create_product(
        db_session,
        payload=products.ProductCreate(name="queue-product", description="queue desc"),
    )
    template_v1 = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="oci://example/chart",
            chart_version="1.0.0",
        ),
    )
    template_v2 = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="oci://example/chart",
            chart_version="2.0.0",
        ),
    )
    return user, template_v1, template_v2


def test_create_deployment_enqueues_create_job(db_session):
    user, template_v1, _ = _setup_user_and_templates(db_session)

    dep = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,
            desired_template_id=template_v1.id,
            domainname="queue-create.example.test",
        ),
    )

    assert dep.status == DEPLOYMENT_STATUS_PROVISIONING
    jobs = db_session.exec(
        select(DeploymentReconcileJobORM).where(DeploymentReconcileJobORM.deployment_id == dep.id)
    ).all()
    assert len(jobs) == 1
    assert jobs[0].reason == "create"
    assert jobs[0].status == "queued"


def test_delete_deployment_sets_state_and_enqueues_delete_job(db_session):
    user, template_v1, _ = _setup_user_and_templates(db_session)
    dep = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,
            desired_template_id=template_v1.id,
            domainname="queue-delete.example.test",
        ),
    )

    create_job = db_session.exec(
        select(DeploymentReconcileJobORM)
        .where(DeploymentReconcileJobORM.deployment_id == dep.id, DeploymentReconcileJobORM.reason == "create")
    ).one()
    jobs.mark_job_done(db_session, job_id=create_job.id)

    deleted = deployments.delete_deployment(db_session, user_id=user.id, deployment_id=dep.id)
    assert deleted.status == DEPLOYMENT_STATUS_DELETING
    assert deleted.generation == 2
    deleted_orm = db_session.get(deployments.DeploymentORM, dep.id)
    assert deleted_orm is not None
    assert deleted_orm.deleted_at is not None

    queued_jobs = db_session.exec(
        select(DeploymentReconcileJobORM)
        .where(DeploymentReconcileJobORM.deployment_id == dep.id)
        .order_by(DeploymentReconcileJobORM.id)
    ).all()
    assert [j.reason for j in queued_jobs] == ["create", "delete"]


def test_upgrade_deployment_enqueues_update_and_rejects_downgrade(db_session):
    user, template_v1, template_v2 = _setup_user_and_templates(db_session)
    dep = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,
            desired_template_id=template_v1.id,
            domainname="queue-upgrade.example.test",
        ),
    )

    create_job = db_session.exec(
        select(DeploymentReconcileJobORM)
        .where(DeploymentReconcileJobORM.deployment_id == dep.id, DeploymentReconcileJobORM.reason == "create")
    ).one()
    jobs.mark_job_done(db_session, job_id=create_job.id)

    upgraded = deployments.update_deployment(
        db_session,
        update=deployments.DeploymentUpdate(id=dep.id, user_id=user.id, desired_template_id=template_v2.id)
    )
    assert upgraded.status == DEPLOYMENT_STATUS_PROVISIONING
    assert upgraded.generation == 2
    assert upgraded.desired_template_id == template_v2.id

    queued_jobs = db_session.exec(
        select(DeploymentReconcileJobORM)
        .where(DeploymentReconcileJobORM.deployment_id == dep.id)
        .order_by(DeploymentReconcileJobORM.id)
    ).all()
    assert [j.reason for j in queued_jobs] == ["create", "update"]

    with pytest.raises(IntegrityException):
        deployments.update_deployment(
            db_session,
            deployments.DeploymentUpdate(id=dep.id, user_id=user.id, desired_template_id=template_v1.id)
        )


def test_update_rolls_back_when_open_job_exists(db_session):
    user, template_v1, template_v2 = _setup_user_and_templates(db_session)
    dep = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,
            desired_template_id=template_v1.id,
            domainname="queue-rollback.example.test",
        ),
    )

    with pytest.raises(DeploymentInProgressException):
        deployments.update_deployment(
            db_session,
            update=deployments.DeploymentUpdate(
                id=dep.id,
                user_id=user.id,
                desired_template_id=template_v2.id,
            ),
        )

    current = db_session.get(deployments.DeploymentORM, dep.id)
    assert current is not None
    assert current.desired_template_id == template_v1.id
    assert current.status == DEPLOYMENT_STATUS_PROVISIONING
    assert current.generation == 1
