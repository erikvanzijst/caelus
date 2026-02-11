import pytest

from app.services import users, products, templates, deployments
from app.services.errors import IntegrityException
from tests.conftest import db_session


def test_product_name_unique_constraint(db_session):
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
    orm = db_session.get(products.ProductORM, p1.id)
    orm.deleted = True
    db_session.add(orm)
    db_session.commit()

    # Now creating a product with same name should succeed
    p2 = products.create_product(
        db_session, payload=products.ProductCreate(name="testprod", description="new")
    )
    assert p2.id != p1.id


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
            product_id=product.id, docker_image_url="docker.io/img"
        ),
    )
    # Create first deployment
    dep1 = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id, template_id=template.id, domainname="example.com"
        ),
    )
    # Attempt duplicate deployment
    with pytest.raises(IntegrityException):
        deployments.create_deployment(
            db_session,
            payload=deployments.DeploymentCreate(
                user_id=user.id, template_id=template.id, domainname="example.com"
            ),
        )
    # rollback the failed transaction
    db_session.rollback()
    # Delete first deployment via service
    deployments.delete_deployment(db_session, user_id=user.id, deployment_id=dep1.id)

    # Now creating same deployment should succeed
    dep2 = deployments.create_deployment(
        db_session,
        payload=deployments.DeploymentCreate(
            user_id=user.id, template_id=template.id, domainname="example.com"
        ),
    )
    assert dep2.id != dep1.id
