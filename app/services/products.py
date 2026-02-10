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
        raise IntegrityException(f"A product with this name already exists: {product.name}") from exc


def list_products(session: Session) -> list[ProductRead]:
    return list(session.exec(select(ProductORM)).all()) # TODO: filter out deleted products


def get_product(session: Session, product_id: int) -> ProductRead:
    product = session.get(ProductORM, product_id)
    if not product:
        raise NotFoundException("Product not found")
    return ProductRead.model_validate(product)

# TODO: delete product endpoint
