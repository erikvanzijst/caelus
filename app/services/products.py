from __future__ import annotations

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
        select(ProductORM).where(ProductORM.deleted == False)  # noqa: E712
    ).all()
    return [ProductRead.model_validate(p) for p in products]


def get_product(session: Session, product_id: int) -> ProductRead:
    product = session.get(ProductORM, product_id)
    if not product or product.deleted:
        raise NotFoundException("Product not found")
    return ProductRead.model_validate(product)


def delete_product(session: Session, *, product_id: int) -> ProductRead:
    """Soft‑delete a product by setting its ``deleted`` flag.

    Raises NotFoundException if the product does not exist.
    """
    product = session.get(ProductORM, product_id)
    if not product:
        raise NotFoundException("Product not found")
    product.deleted = True
    session.add(product)
    session.commit()
    return ProductRead.model_validate(product)
