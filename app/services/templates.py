from __future__ import annotations

from sqlmodel import Session, select

from app.models import ProductTemplateVersionORM, ProductTemplateVersionRead, ProductTemplateVersionCreate
from app.services.errors import NotFoundException
from app.services.products import get_product


def create_template(session: Session, payload: ProductTemplateVersionCreate) -> ProductTemplateVersionORM:
    template = ProductTemplateVersionORM.model_validate(payload)
    # verify that the product exists:
    get_product(session, template.product_id)

    session.add(template)
    session.commit()
    session.refresh(template)
    return template


def list_templates(session: Session, product_id: int) -> list[ProductTemplateVersionRead]:
    # TODO: filter out deleted templates
    return list(
        session.exec(
            select(ProductTemplateVersionORM).where(ProductTemplateVersionORM.product_id == product_id)
        ).all()
    )


def get_template(session: Session, *, product_id: int, template_id: int) -> ProductTemplateVersionRead:
    template = session.get(ProductTemplateVersionORM, template_id)
    if not template or template.product_id != product_id:
        raise NotFoundException("Template not found")
    return ProductTemplateVersionRead.model_validate(template)

# TODO: delete template