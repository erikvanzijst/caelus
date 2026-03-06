from __future__ import annotations

import json
from datetime import datetime
from typing import BinaryIO

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import ProductRead, ProductORM, ProductCreate, ProductUpdate
from app.services import templates as template_service
from app.services.errors import NotFoundException, IntegrityException, ValidationException
from app.config import get_static_url_base
from app.services.images import process_icon, generate_icon_filename, save_icon, MAX_ICON_SIZE


def _product_orm_to_read(product_orm: ProductORM) -> ProductRead:
    """Convert ProductORM to ProductRead with computed icon_url."""
    data = {
        "id": product_orm.id,
        "name": product_orm.name,
        "description": product_orm.description,
        "template_id": product_orm.template_id,
        "created_at": product_orm.created_at,
        "template": product_orm.template,
    }
    if product_orm.rel_icon_path:
        data["icon_url"] = f"{get_static_url_base()}/{product_orm.rel_icon_path}"
    return ProductRead(**data)


def create_product(
    session: Session, payload: ProductCreate, icon_data: bytes | None = None
) -> ProductRead:
    """Create a product, optionally with an icon.

    Args:
        session: Database session
        payload: Product create payload
        icon_data: Optional raw icon image bytes

    Returns:
        Created ProductRead with icon_url if icon provided

    Raises:
        IntegrityException: If product name already exists
        ValidationException: If icon processing fails
    """
    if icon_data is not None and len(icon_data) > MAX_ICON_SIZE:
        raise ValidationException(
            f"Image file too large. Maximum size is {MAX_ICON_SIZE // (1024 * 1024)}MB"
        )

    product = ProductORM.model_validate(payload)
    session.add(product)

    try:
        if icon_data is not None:
            processed_icon = process_icon(icon_data)
            rel_icon_path = generate_icon_filename(processed_icon)
            save_icon(processed_icon, rel_icon_path)
            product.rel_icon_path = rel_icon_path

        session.commit()
        session.refresh(product)
        return _product_orm_to_read(product)
    except IntegrityError as exc:
        session.rollback()
        raise IntegrityException(
            f"A product with this name already exists: {product.name}"
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise ValidationException(str(exc)) from exc


def list_products(session: Session) -> list[ProductRead]:
    return [
        _product_orm_to_read(p)
        for p in session.exec(select(ProductORM).where(ProductORM.deleted_at == None)).all()
    ]


def get_product(session: Session, product_id: int) -> ProductRead:
    if not (
        product := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Product not found")
    return _product_orm_to_read(product)


def delete_product(session: Session, *, product_id: int) -> ProductRead:
    """Soft‑delete a product by setting its ``deleted`` flag.

    Raises NotFoundException if the product does not exist.
    """
    # Retrieve the product that is not already deleted
    if not (
        product := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Product not found")
    product.deleted_at = datetime.utcnow()
    session.commit()
    return _product_orm_to_read(product)


def update_product(session: Session, *, product: ProductUpdate) -> ProductRead:
    """Update a product's template_id and/or description.

    Validates that the product exists and that the template belongs to the product.
    Raises NotFoundException if either is missing.
    """
    if not (
        product_orm := session.exec(
            select(ProductORM).where(ProductORM.id == product.id, ProductORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Product not found")

    if product.template_id:
        template_service.get_template(
            session, product_id=product.id, template_id=product.template_id
        )
        product_orm.template_id = product.template_id
    if product.description:
        product_orm.description = product.description

    session.add(product_orm)
    session.commit()
    session.refresh(product_orm)
    return _product_orm_to_read(product_orm)


def upload_product_icon(session: Session, product_id: int, icon_data: bytes) -> ProductRead:
    """Upload and process an icon for a product.

    Args:
        session: Database session
        product_id: ID of the product
        icon_data: Raw icon image bytes

    Returns:
        Updated ProductRead with new icon_url

    Raises:
        NotFoundException: If product doesn't exist
        ValidationException: If icon processing fails
    """
    if len(icon_data) > MAX_ICON_SIZE:
        raise ValidationException(
            f"Image file too large. Maximum size is {MAX_ICON_SIZE // (1024 * 1024)}MB"
        )

    if not (
        product_orm := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Product not found")

    try:
        processed_icon = process_icon(icon_data)
        rel_icon_path = generate_icon_filename(processed_icon)
    except ValueError as e:
        raise ValidationException(str(e)) from e
    save_icon(processed_icon, rel_icon_path)

    product_orm.rel_icon_path = rel_icon_path
    session.add(product_orm)
    session.commit()
    session.refresh(product_orm)
    return _product_orm_to_read(product_orm)


def get_product_icon_path(session: Session, product_id: int) -> str | None:
    """Get the relative icon path for a product.

    Args:
        session: Database session
        product_id: ID of the product

    Returns:
        Relative icon path or None if no icon

    Raises:
        NotFoundException: If product doesn't exist
    """
    if not (
        product_orm := session.exec(
            select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Product not found")
    return product_orm.rel_icon_path
