from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models import Product, ProductTemplateVersion
from app.schemas import (
    ProductCreate,
    ProductRead,
    TemplateVersionCreate,
    TemplateVersionRead,
)
from app.services import products as product_service
from app.services import templates as template_service
from app.services.errors import NotFoundError

router = APIRouter(prefix="/products", tags=["products"])


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, session: Session = Depends(get_session)) -> Product:
    return product_service.create_product(
        session, name=payload.name, description=payload.description, template=payload.template
    )


@router.get("", response_model=list[ProductRead])
def list_products(session: Session = Depends(get_session)) -> list[Product]:
    return product_service.list_products(session)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)) -> Product:
    try:
        return product_service.get_product(session, product_id=product_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/{product_id}/templates",
    response_model=TemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    product_id: int,
    payload: TemplateVersionCreate,
    session: Session = Depends(get_session),
) -> ProductTemplateVersion:
    try:
        return template_service.create_template(
            session,
            product_id=product_id,
            docker_image_url=payload.docker_image_url,
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{product_id}/templates", response_model=list[TemplateVersionRead])
def list_templates(
    product_id: int, session: Session = Depends(get_session)
) -> list[ProductTemplateVersion]:
    return template_service.list_templates(session, product_id=product_id)


@router.get("/{product_id}/templates/{template_id}", response_model=TemplateVersionRead)
def get_template(
    product_id: int, template_id: int, session: Session = Depends(get_session)
) -> ProductTemplateVersion:
    try:
        return template_service.get_template(
            session, product_id=product_id, template_id=template_id
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
