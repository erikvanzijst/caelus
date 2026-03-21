from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_user, require_admin
from app.models import (
    PlanCreate,
    PlanRead,
    PlanTemplateVersionCreate,
    PlanTemplateVersionRead,
    PlanUpdate,
    UserORM,
)
from app.services import plans as plan_service

router = APIRouter(tags=["plans"])


# ---------------------------------------------------------------------------
# Plan browsing (any authenticated user)
# ---------------------------------------------------------------------------


@router.get("/products/{product_id}/plans", response_model=list[PlanRead])
def list_plans(
    product_id: int,
    _current_user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[PlanRead]:
    return plan_service.list_plans_for_product(session, product_id)


@router.get("/plans/{plan_id}", response_model=PlanRead)
def get_plan(
    plan_id: int,
    _current_user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PlanRead:
    return plan_service.get_plan(session, plan_id)


# ---------------------------------------------------------------------------
# Plan administration (admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/products/{product_id}/plans",
    response_model=PlanRead,
    status_code=status.HTTP_201_CREATED,
)
def create_plan(
    product_id: int,
    payload: PlanCreate,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PlanRead:
    return plan_service.create_plan(session, product_id=product_id, payload=payload)


@router.put("/plans/{plan_id}", response_model=PlanRead)
def update_plan(
    plan_id: int,
    payload: PlanUpdate,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PlanRead:
    return plan_service.update_plan(session, plan_id=plan_id, payload=payload)


@router.delete("/plans/{plan_id}", status_code=204)
def delete_plan(
    plan_id: int,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> None:
    plan_service.delete_plan(session, plan_id=plan_id)


# ---------------------------------------------------------------------------
# Plan template versions (admin only)
# ---------------------------------------------------------------------------


@router.post(
    "/plans/{plan_id}/templates",
    response_model=PlanTemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_plan_template(
    plan_id: int,
    payload: PlanTemplateVersionCreate,
    _current_user: UserORM = Depends(require_admin),
    session: Session = Depends(get_session),
) -> PlanTemplateVersionRead:
    return plan_service.create_plan_template_version(
        session, plan_id=plan_id, payload=payload
    )
