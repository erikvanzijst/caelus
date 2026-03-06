from __future__ import annotations

import json

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile as FastAPIUploadFile,
    status,
)
from fastapi.requests import Request
from fastapi.responses import RedirectResponse
from starlette.datastructures import UploadFile
from sqlmodel import Session

from app.db import get_session
from app.models import (
    ProductRead,
    ProductCreate,
    ProductTemplateVersionRead,
    ProductTemplateVersionCreate,
    ProductUpdate,
)
from app.services import templates as template_service, products as product_service

router = APIRouter(prefix="/products", tags=["products"])


async def parse_product_request(request: Request) -> tuple[ProductCreate, bytes | None]:
    content_type = request.headers.get("content-type", "")
    body = await request.body()

    if "multipart/form-data" in content_type:
        form = await request.form()
        payload_data = form.get("payload")

        if payload_data is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Product JSON payload is required",
            )

        try:
            payload_dict = json.loads(str(payload_data))
        except json.JSONDecodeError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"Invalid product JSON: {e}",
            ) from e

        payload = ProductCreate(**payload_dict)

        icon_data: bytes | None = None
        icon_file = form.get("icon")
        if icon_file is not None and not isinstance(icon_file, UploadFile):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Icon must be a file upload",
            )
        if isinstance(icon_file, UploadFile):
            try:
                icon_data = await icon_file.read()
            except OSError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to read icon upload: {exc}",
                ) from exc

        return payload, icon_data
    else:
        try:
            if body:
                payload = ProductCreate.model_validate(json.loads(body))
            else:
                payload = ProductCreate.model_validate({})
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid JSON body",
            )
        return payload, None


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
async def create_product(request: Request, session: Session = Depends(get_session)) -> ProductRead:
    payload, icon_data = await parse_product_request(request)
    product = product_service.create_product(session, payload, icon_data)
    return product


@router.get("", response_model=list[ProductRead])
def list_products(session: Session = Depends(get_session)) -> list[ProductRead]:
    return product_service.list_products(session)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, session: Session = Depends(get_session)) -> ProductRead:
    return product_service.get_product(session, product_id=product_id)


@router.put("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int, product: ProductUpdate, session: Session = Depends(get_session)
) -> ProductRead:
    product.id = product_id
    return product_service.update_product(session, product=product)


@router.delete("/{product_id}", status_code=204)
def delete_product_endpoint(product_id: int, session: Session = Depends(get_session)) -> None:
    product_service.delete_product(session, product_id=product_id)


@router.post(
    "/{product_id}/templates",
    response_model=ProductTemplateVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    product_id: int, payload: ProductTemplateVersionCreate, session: Session = Depends(get_session)
):
    payload.product_id = product_id
    return template_service.create_template(session, payload)


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


@router.put("/{product_id}/icon", response_model=ProductRead)
def upload_icon(
    product_id: int, icon: FastAPIUploadFile = File(...), session: Session = Depends(get_session)
) -> ProductRead:
    icon_data = icon.file.read()
    return product_service.upload_product_icon(session, product_id, icon_data)


@router.get("/{product_id}/icon")
def get_icon_redirect(product_id: int, session: Session = Depends(get_session)):
    rel_path = product_service.get_product_icon_path(session, product_id)
    if rel_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Icon not found")
    from app.config import get_static_url_base

    return RedirectResponse(
        url=f"{get_static_url_base()}/{rel_path}", status_code=status.HTTP_302_FOUND
    )
