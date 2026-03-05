import pytest
from datetime import datetime

from app.services import templates, deployments, products, users
from app.services.jobs import JobService
from sqlmodel import select
from app.models import DeploymentReconcileJobORM
from app.services.errors import IntegrityException
from app.services.reconcile import DeploymentReconciler
from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETED
from tests.conftest import db_session
from tests.provisioner_utils import FakeProvisioner


def test_product_name_unique_constraint(db_session):
    def delete_product(prod: products.ProductORM):
        orm = db_session.get(products.ProductORM, prod.id)
        orm.deleted_at = datetime.utcnow()
        db_session.add(orm)
        db_session.commit()

    # Create first product
    p1 = products.create_product(
        db_session, payload=products.ProductCreate(name="testprod", description="desc")
    )
    # Attempt to create duplicate product with same name
    with pytest.raises(IntegrityException):
        products.create_product(
            db_session, payload=products.ProductCreate(name="testprod", description="another")
        )

    # rollback the failed transaction
    db_session.rollback()
    # Mark first product as deleted manually
    delete_product(p1)

    # Now creating a product with same name should succeed
    p2 = products.create_product(
        db_session, payload=products.ProductCreate(name="testprod", description="new")
    )
    assert p2.id != p1.id
    # deletion should still work (the partial index should allow duplicate deleted name entries)
    delete_product(p2)


def test_deployment_unique_constraint(db_session):
    # Setup user
    user = users.create_user(db_session, payload=users.UserCreate(email="user@example.com"))
    # Setup product and template
    product = products.create_product(
        db_session, payload=products.ProductCreate(name="prod2", description="desc")
    )
    template = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="registry.home:80/nextcloud/",
            chart_version="1.0.0",
            values_schema_json={
                "type": "object",
                "properties": {"domain": {"type": "string", "title": "domainname"}},
            },
        )
    )
    # Create first deployment
    dep1 = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id, desired_template_id=template.id, user_values_json={"domain": "example.com"}
        ),
    )
    # Attempt duplicate deployment
    with pytest.raises(IntegrityException):
        deployments.create_deployment(
            db_session,
            payload=deployments.DeploymentCreate(
                user_id=user.id, desired_template_id=template.id, user_values_json={"domain": "example.com"}
            ),
        )
    # rollback the failed transaction
    db_session.rollback()
    create_job = db_session.exec(
        select(DeploymentReconcileJobORM).where(
            DeploymentReconcileJobORM.deployment_id == dep1.id,
            DeploymentReconcileJobORM.reason == "create",
        )
    ).one()
    JobService(db_session).mark_job_done(job_id=create_job.id)
    # Delete first deployment via service
    deployments.delete_deployment(db_session, user_id=user.id, deployment_id=dep1.id)

    # Run the reconciler to actually process the delete request and set the status to deleted:
    reconciler = DeploymentReconciler(session=db_session, provisioner=FakeProvisioner())

    result = reconciler.reconcile(dep1.id)
    assert result.status == DEPLOYMENT_STATUS_DELETED

    # Now creating same deployment should succeed
    dep2 = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id, desired_template_id=template.id, user_values_json={"domain": "example.com"}
        ),
    )
    assert dep2.id != dep1.id


def test_domainname_active_unique_constraint_across_non_deleted_deployments(db_session):
    user_a = users.create_user(db_session, payload=users.UserCreate(email="domain-a@example.com"))
    user_b = users.create_user(db_session, payload=users.UserCreate(email="domain-b@example.com"))
    product = products.create_product(
        db_session,
        payload=products.ProductCreate(name="domain-uniq-product", description="desc"),
    )
    template_v1 = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="registry.home:80/nextcloud/",
            chart_version="1.0.0",
            values_schema_json={
                "type": "object",
                "properties": {"domain": {"type": "string", "title": "domainname"}},
            },
        ),
    )
    template_v2 = templates.create_template(
        db_session,
        payload=templates.ProductTemplateVersionCreate(
            product_id=product.id,
            chart_ref="registry.home:80/nextcloud/",
            chart_version="2.0.0",
            values_schema_json={
                "type": "object",
                "properties": {"domain": {"type": "string", "title": "domainname"}},
            },
        ),
    )

    dep_a = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user_a.id,
            desired_template_id=template_v1.id,
            user_values_json={"domain": "shared.example.com"},
        ),
    )
    assert dep_a.domainname == "shared.example.com"

    with pytest.raises(IntegrityException):
        deployments.create_deployment(
            db_session,
            payload=deployments.DeploymentCreate(
                user_id=user_b.id,
                desired_template_id=template_v2.id,
                user_values_json={"domain": "shared.example.com"},
            ),
        )

    db_session.rollback()
    dep_a_orm = db_session.get(deployments.DeploymentORM, dep_a.id)
    assert dep_a_orm is not None
    dep_a_orm.status = DEPLOYMENT_STATUS_DELETED
    db_session.add(dep_a_orm)
    db_session.commit()

    dep_b = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user_b.id,
            desired_template_id=template_v2.id,
            user_values_json={"domain": "shared.example.com"},
        ),
    )
    assert dep_b.domainname == "shared.example.com"
