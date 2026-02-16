from __future__ import annotations

from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import ProductRead, ProductORM, ProductCreate, ProductUpdate
from app.services import templates as template_service
from app.services.errors import NotFoundException, IntegrityException


def create_product(session: Session, payload: ProductCreate) -> ProductRead:
    product = ProductORM.model_validate(payload)
    session.add(product)
    try:
        session.commit()
        session.refresh(product)
        return ProductRead.model_validate(product)
    except IntegrityError as exc:
        raise IntegrityException(f"A product with this name already exists: {product.name}") from exc


def list_products(session: Session) -> list[ProductRead]:
    return [ProductRead.model_validate(p) for p in
            session.exec(select(ProductORM).where(ProductORM.deleted_at == None)).all()]


def get_product(session: Session, product_id: int) -> ProductRead:
    if not (product := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)).one_or_none()):
        raise NotFoundException("Product not found")
    return ProductRead.model_validate(product)


def delete_product(session: Session, *, product_id: int) -> ProductRead:
    """Soft‑delete a product by setting its ``deleted`` flag.

    Raises NotFoundException if the product does not exist.
    """
    # Retrieve the product that is not already deleted
    if not (product := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)).one_or_none()):
        raise NotFoundException("Product not found")
    product.deleted_at = datetime.utcnow()
    session.commit()
    return ProductRead.model_validate(product)


def update_product(session: Session, *, product: ProductUpdate) -> ProductRead:
    """Update a product's template_id and/or description.

    Validates that the product exists and that the template belongs to the product.
    Raises NotFoundException if either is missing.
    """
    if not (product_orm := session.exec(
            select(ProductORM).where(ProductORM.id == product.id, ProductORM.deleted_at == None)).one_or_none()):
        raise NotFoundException("Product not found")

    if product.template_id:
        template_service.get_template(session, product_id=product.id, template_id=product.template_id)
        product_orm.template_id = product.template_id
    if product.description:
        product_orm.description = product.description

    session.add(product_orm)
    session.commit()
    session.refresh(product_orm)
    return ProductRead.model_validate(product_orm)
