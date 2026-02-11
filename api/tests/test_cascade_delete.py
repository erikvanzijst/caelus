import sqlalchemy as sa
from sqlmodel import select

from app.models import DeploymentORM, ProductORM, ProductTemplateVersionORM, UserORM


def test_product_delete_cascades_templates_and_deployments(db_session):
    db_session.exec(sa.text("PRAGMA foreign_keys=ON"))

    product = ProductORM(name="demo", description=None)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)

    template = ProductTemplateVersionORM(product_id=product.id, docker_image_url="demo:latest")
    db_session.add(template)
    db_session.commit()
    db_session.refresh(template)

    product.template_id = template.id
    db_session.add(product)
    db_session.commit()

    user = UserORM(email="cascade@example.com")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    deployment = DeploymentORM(
        user_id=user.id,
        template_id=template.id,
        domainname="demo.example.com",
    )
    db_session.add(deployment)
    db_session.commit()

    db_session.delete(product)
    db_session.commit()

    assert db_session.exec(select(ProductTemplateVersionORM)).all() == []
    assert db_session.exec(select(DeploymentORM)).all() == []
