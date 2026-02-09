from __future__ import annotations

from sqlmodel import Session, select

from app.models import Product
from app.services.errors import NotFoundError


def create_product(session: Session, *, name: str, description: str, template: str | None) -> Product:
    product = Product(name=name, description=description, template=template)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def list_products(session: Session) -> list[Product]:
    return list(session.exec(select(Product)).all())


def get_product(session: Session, *, product_id: int) -> Product:
    product = session.get(Product, product_id)
    if not product:
        raise NotFoundError("Product not found")
    return product
