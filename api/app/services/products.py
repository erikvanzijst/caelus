from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import ProductRead, ProductORM, ProductCreate
from app.services.errors import NotFoundException, IntegrityException


def create_product(session: Session, payload: ProductCreate) -> ProductRead:
    product = ProductORM.model_validate(payload)
    session.add(product)
    try:
        session.commit()
        session.refresh(product)
        return ProductRead.model_validate(product)
    except IntegrityError as exc:
        raise IntegrityException(
            f"A product with this name already exists: {product.name}"
        ) from exc


def list_products(session: Session) -> list[ProductRead]:
    # Return products that are not soft‑deleted
    products = session.exec(
        select(ProductORM).where(ProductORM.deleted_at == None)  # noqa: E712
    ).all()
    return [ProductRead.model_validate(p) for p in products]


def get_product(session: Session, product_id: int) -> ProductRead:
    if not (
        product := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Product not found")
    return ProductRead.model_validate(product)


def delete_product(session: Session, *, product_id: int) -> ProductRead:
    """Soft‑delete a product by setting its ``deleted`` flag.

    Raises NotFoundException if the product does not exist.
    """
    # Retrieve the product that is not already deleted
    product = session.exec(
        select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)  # noqa: E712
    ).one_or_none()
    if not product:
        raise NotFoundException("Product not found")
    product.deleted_at = datetime.utcnow()
    session.commit()
    return ProductRead.model_validate(product)


def update_product_template(session: Session, *, product_id: int, template_id: int) -> ProductRead:
    """Update a product's template_id.

    Validates that the product exists and that the template belongs to the product.
    Raises NotFoundException if either is missing.
    """
    # Ensure product exists and is not deleted
    product = session.exec(
        select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)  # noqa: E712
    ).one_or_none()
    if not product:
        raise NotFoundException("Product not found")
    # Validate template belongs to product using template service
    from app.services import templates as template_service

    # This will raise NotFoundException if not valid
    template_service.get_template(session, product_id=product_id, template_id=template_id)
    product.template_id = template_id
    session.add(product)
    session.commit()
    session.refresh(product)
    return ProductRead.model_validate(product)
    """Soft‑delete a product by setting its ``deleted`` flag.

    Raises NotFoundException if the product does not exist.
    """
    # Retrieve the product that is not already deleted
    product = session.exec(
        select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)  # noqa: E712
    ).one_or_none()
    if not product:
        raise NotFoundException("Product not found")
    product.deleted_at = datetime.utcnow()
    session.commit()
    return ProductRead.model_validate(product)
