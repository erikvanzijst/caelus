import pytest
from datetime import datetime

from app.services import templates, deployments, products, users, jobs
from sqlmodel import select
from app.models import DeploymentReconcileJobORM
from app.services.errors import IntegrityException
from tests.conftest import db_session


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
            product_id=product.id, chart_ref="registry.home:80/nextcloud/", chart_version="1.0.0")
    )
    # Create first deployment
    dep1 = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,desired_template_id=template.id, domainname="example.com"
        ),
    )
    # Attempt duplicate deployment
    with pytest.raises(IntegrityException):
        deployments.create_deployment(
            db_session,
            payload=deployments.DeploymentCreate(
                user_id=user.id, desired_template_id=template.id, domainname="example.com"
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
    jobs.mark_job_done(db_session, job_id=create_job.id)
    # Delete first deployment via service
    deployments.delete_deployment(db_session, user_id=user.id, deployment_id=dep1.id)

    # Now creating same deployment should succeed
    dep2 = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id,desired_template_id=template.id, domainname="example.com"
        ),
    )
    assert dep2.id != dep1.id
