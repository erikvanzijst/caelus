from __future__ import annotations

from datetime import UTC, datetime

from typing import Any

from jsonschema import SchemaError
from jsonschema.validators import validator_for
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import (
    ProductTemplateVersionORM,
    ProductTemplateVersionRead,
    ProductTemplateVersionCreate,
)
from app.services.errors import NotFoundException, IntegrityException, ValidationException
from app.services.products import get_product


def _check_values_schema(schema: dict[str, Any] | None) -> None:
    """Meta-validate a template's `values_schema_json` document.

    `values_schema_json` is optional; `None` means the template takes no user
    values and is always accepted. When present, the document must itself be a
    well-formed JSON Schema. The dialect is selected from the document's own
    `$schema` key via `validator_for`, so templates declaring draft 2020-12
    are checked against 2020-12 rather than a hardcoded draft.

    Without this check a malformed schema is stored happily and only blows up
    later, in `validate_user_values`, for whichever tenant next tries to create
    a deployment.
    """
    if schema is None:
        return
    try:
        cls = validator_for(schema)
        cls.check_schema(schema)
    except SchemaError as exc:
        raise ValidationException(f"values_schema_json is not a valid JSON Schema: {exc.message}") from exc


def create_template(session: Session, payload: ProductTemplateVersionCreate) -> ProductTemplateVersionORM:
    _check_values_schema(payload.values_schema_json)
    template = ProductTemplateVersionORM.model_validate(payload)
    # verify that the product exists:
    get_product(session, template.product_id)

    session.add(template)
    try:
        session.commit()
        session.refresh(template)
        return template
    except IntegrityError as exc:
        raise IntegrityException(f"A template for this product version already exists") from exc


def list_templates(session: Session, product_id: int) -> list[ProductTemplateVersionRead]:
    # Return templates for the product that are not soft‑deleted
    templates = session.exec(
        select(ProductTemplateVersionORM)
        .where(ProductTemplateVersionORM.product_id == product_id)
        .where(ProductTemplateVersionORM.deleted_at == None)  # noqa: E712
    ).all()
    return [ProductTemplateVersionRead.model_validate(t) for t in templates]


def get_template(session: Session, *, product_id: int, template_id: int) -> ProductTemplateVersionRead:
    template = session.get(ProductTemplateVersionORM, template_id)
    if not template or template.product_id != product_id or template.deleted_at:
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
    template.deleted_at = datetime.now(UTC)
    session.add(template)
    session.commit()
    return ProductTemplateVersionRead.model_validate(template)
