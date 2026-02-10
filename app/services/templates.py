from __future__ import annotations

from sqlmodel import Session, select

from app.models import (
    ProductTemplateVersionORM,
    ProductTemplateVersionRead,
    ProductTemplateVersionCreate,
)
from app.services.errors import NotFoundException
from app.services.products import get_product


def create_template(
    session: Session, payload: ProductTemplateVersionCreate
) -> ProductTemplateVersionORM:
    template = ProductTemplateVersionORM.model_validate(payload)
    # verify that the product exists:
    get_product(session, template.product_id)

    session.add(template)
    session.commit()
    session.refresh(template)
    return template


def list_templates(session: Session, product_id: int) -> list[ProductTemplateVersionRead]:
    # Return templates for the product that are not soft‑deleted
    templates = session.exec(
        select(ProductTemplateVersionORM)
        .where(ProductTemplateVersionORM.product_id == product_id)
        .where(ProductTemplateVersionORM.deleted == False)  # noqa: E712
    ).all()
    return [ProductTemplateVersionRead.model_validate(t) for t in templates]


def get_template(
    session: Session, *, product_id: int, template_id: int
) -> ProductTemplateVersionRead:
    template = session.get(ProductTemplateVersionORM, template_id)
    if not template or template.product_id != product_id or template.deleted:
        raise NotFoundException("Template not found")
    return ProductTemplateVersionRead.model_validate(template)


def delete_template(
    session: Session, *, product_id: int, template_id: int
) -> ProductTemplateVersionRead:
    """Soft‑delete a template.

    Ensures the template belongs to the specified product and marks it as deleted.
    Raises NotFoundException if not found.
    """
    template = session.get(ProductTemplateVersionORM, template_id)
    if not template or template.product_id != product_id:
        raise NotFoundException("Template not found")
    template.deleted = True
    session.add(template)
    session.commit()
    return ProductTemplateVersionRead.model_validate(template)
