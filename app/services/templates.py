from __future__ import annotations

from sqlmodel import Session, select

from app.models import Product, ProductTemplateVersion
from app.services.errors import NotFoundError


def create_template(
    session: Session, *, product_id: int, docker_image_url: str | None
) -> ProductTemplateVersion:
    product = session.get(Product, product_id)
    if not product:
        raise NotFoundError("Product not found")

    template = ProductTemplateVersion(product_id=product_id, docker_image_url=docker_image_url)
    session.add(template)
    session.commit()
    session.refresh(template)
    return template


def list_templates(session: Session, *, product_id: int) -> list[ProductTemplateVersion]:
    return list(
        session.exec(
            select(ProductTemplateVersion).where(ProductTemplateVersion.product_id == product_id)
        ).all()
    )


def get_template(
    session: Session, *, product_id: int, template_id: int
) -> ProductTemplateVersion:
    template = session.get(ProductTemplateVersion, template_id)
    if not template or template.product_id != product_id:
        raise NotFoundError("Template not found")
    return template
