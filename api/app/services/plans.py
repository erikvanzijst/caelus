from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models import (
    PlanORM,
    PlanCreate,
    PlanRead,
    PlanUpdate,
    PlanTemplateVersionORM,
    PlanTemplateVersionCreate,
    PlanTemplateVersionRead,
    ProductORM,
)
from app.services.errors import IntegrityException, NotFoundException


def create_plan(session: Session, *, product_id: int, payload: PlanCreate) -> PlanRead:
    """Create a plan for a product.

    Raises NotFoundException if the product does not exist.
    Raises IntegrityException if a plan with this name already exists for the product.
    """
    if not session.exec(
        select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
    ).one_or_none():
        raise NotFoundException(f"Product {product_id} not found")

    plan = PlanORM(product_id=product_id, **payload.model_dump())
    session.add(plan)
    try:
        session.commit()
        session.refresh(plan)
        return PlanRead.model_validate(plan)
    except IntegrityError as exc:
        session.rollback()
        raise IntegrityException(
            f"A plan with this name already exists for this product: {payload.name}"
        ) from exc


def list_plans_for_product(session: Session, product_id: int) -> list[PlanRead]:
    """List non-deleted plans for a product, including canonical template details."""
    if not session.exec(
        select(ProductORM).where(ProductORM.id == product_id, ProductORM.deleted_at == None)
    ).one_or_none():
        raise NotFoundException(f"Product {product_id} not found")

    plans = session.exec(
        select(PlanORM)
        .where(PlanORM.product_id == product_id, PlanORM.deleted_at == None)
        .order_by(PlanORM.sort_order, PlanORM.id)
    ).all()
    return [PlanRead.model_validate(p) for p in plans]


def get_plan(session: Session, plan_id: int) -> PlanRead:
    """Get a single plan by ID.

    Raises NotFoundException if not found or soft-deleted.
    """
    if not (
        plan := session.exec(
            select(PlanORM).where(PlanORM.id == plan_id, PlanORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException("Plan not found")
    return PlanRead.model_validate(plan)


def update_plan(session: Session, *, plan_id: int, payload: PlanUpdate) -> PlanRead:
    """Update a plan's mutable fields (name, template_id, sort_order).

    Raises NotFoundException if the plan or referenced template is not found.
    Raises IntegrityException if the new name conflicts with an existing plan.
    """
    if not (
        plan := session.exec(
            select(PlanORM).where(PlanORM.id == plan_id, PlanORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException(f"Plan {plan_id} not found")

    if payload.template_id is not None:
        tmpl = session.get(PlanTemplateVersionORM, payload.template_id)
        if not tmpl or tmpl.plan_id != plan.id or tmpl.deleted_at:
            raise NotFoundException("Plan template version not found or does not belong to this plan")
        plan.template_id = payload.template_id

    if payload.name is not None:
        plan.name = payload.name
    if payload.sort_order is not None:
        plan.sort_order = payload.sort_order

    try:
        session.commit()
        session.refresh(plan)
        return PlanRead.model_validate(plan)
    except IntegrityError as exc:
        session.rollback()
        raise IntegrityException(
            f"A plan with this name already exists for this product"
        ) from exc


def delete_plan(session: Session, *, plan_id: int) -> PlanRead:
    """Soft-delete a plan.

    Raises NotFoundException if not found.
    """
    if not (
        plan := session.exec(
            select(PlanORM).where(PlanORM.id == plan_id, PlanORM.deleted_at == None)
        ).one_or_none()
    ):
        raise NotFoundException(f"Plan {plan_id} not found")

    plan.deleted_at = datetime.now(UTC)
    session.commit()
    return PlanRead.model_validate(plan)


# ---------------------------------------------------------------------------
# Plan Template Versions
# ---------------------------------------------------------------------------


def get_plan_template_version(
    session: Session, *, plan_id: int, template_id: int
) -> PlanTemplateVersionRead:
    """Get a single plan template version.

    Raises NotFoundException if not found, soft-deleted, or doesn't belong to the plan.
    """
    tmpl = session.get(PlanTemplateVersionORM, template_id)
    if not tmpl or tmpl.plan_id != plan_id or tmpl.deleted_at:
        raise NotFoundException(f"Plan template version {template_id} of plan {plan_id} not found")
    return PlanTemplateVersionRead.model_validate(tmpl)


def create_plan_template_version(
    session: Session, *, plan_id: int, payload: PlanTemplateVersionCreate
) -> PlanTemplateVersionRead:
    """Create a new template version for a plan.

    Raises NotFoundException if the plan does not exist.
    """
    if not session.exec(
        select(PlanORM).where(PlanORM.id == plan_id, PlanORM.deleted_at == None)
    ).one_or_none():
        raise NotFoundException("Plan not found")

    tmpl = PlanTemplateVersionORM(plan_id=plan_id, **payload.model_dump())
    session.add(tmpl)
    session.commit()
    session.refresh(tmpl)
    return PlanTemplateVersionRead.model_validate(tmpl)


def list_plan_template_versions(
    session: Session, plan_id: int
) -> list[PlanTemplateVersionRead]:
    """List non-deleted template versions for a plan."""
    templates = session.exec(
        select(PlanTemplateVersionORM)
        .where(PlanTemplateVersionORM.plan_id == plan_id, PlanTemplateVersionORM.deleted_at == None)
    ).all()
    return [PlanTemplateVersionRead.model_validate(t) for t in templates]
