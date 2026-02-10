from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlmodel import Session

from app.db import get_session
from app.models import ProductRead, ProductCreate, ProductTemplateVersionRead, ProductTemplateVersionCreate
from app.services import products as product_service, templates as template_service

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


@router.get("/{product_id}/templates", response_model=list[ProductTemplateVersionRead])
def list_templates(product_id: int, session: Session = Depends(get_session)) -> list[ProductTemplateVersionRead]:
    return template_service.list_templates(session, product_id=product_id)


@router.get("/{product_id}/templates/{template_id}", response_model=ProductTemplateVersionRead)
def get_template(
    product_id: int, template_id: int, session: Session = Depends(get_session)
) -> ProductTemplateVersionRead:
    return template_service.get_template(session, product_id=product_id, template_id=template_id)
