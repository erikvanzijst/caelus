from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db import get_session
from app.models import (
    ProductRead,
    ProductCreate,
    ProductTemplateVersionRead,
    ProductTemplateVersionCreate,
    ProductUpdate,
)
from fastapi import HTTPException
from app.services import templates as template_service, products as product_service

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, session: Session = Depends(get_session)) -> ProductRead:
    return product_service.create_product(session, payload)


@router.get("", response_model=list[ProductRead])
def list_products(session: Session = Depends(get_session)) -> list[ProductRead]:
    return product_service.list_products(session)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)) -> ProductRead:
    return product_service.get_product(session, product_id=product_id)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, payload: ProductUpdate, session: Session = Depends(get_session)
) -> ProductRead:
    if payload.template_id is None:
        raise HTTPException(status_code=400, detail="template_id required")
    return product_service.update_product_template(
        session, product_id=product_id, template_id=payload.template_id
    )


@router.post(
    "/{product_id}/templates",
    response_model=ProductTemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    product_id: int,
    payload: ProductTemplateVersionCreate,
    session: Session = Depends(get_session),
):
    payload.product_id = product_id
    return template_service.create_template(session, payload)


@router.delete("/{product_id}", status_code=204)
def delete_product_endpoint(product_id: int, session: Session = Depends(get_session)) -> None:
    product_service.delete_product(session, product_id=product_id)


@router.get("/{product_id}/templates", response_model=list[ProductTemplateVersionRead])
def list_templates(
    product_id: int, session: Session = Depends(get_session)
) -> list[ProductTemplateVersionRead]:
    return template_service.list_templates(session, product_id=product_id)


@router.get("/{product_id}/templates/{template_id}", response_model=ProductTemplateVersionRead)
def get_template(
    product_id: int, template_id: int, session: Session = Depends(get_session)
) -> ProductTemplateVersionRead:
    return template_service.get_template(session, product_id=product_id, template_id=template_id)


@router.delete("/{product_id}/templates/{template_id}", status_code=204)
def delete_template_endpoint(
    product_id: int, template_id: int, session: Session = Depends(get_session)
) -> None:
    template_service.delete_template(session, product_id=product_id, template_id=template_id)
