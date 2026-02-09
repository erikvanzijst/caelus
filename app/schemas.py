from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import SQLModel


class UserCreate(SQLModel):
    email: str


class UserRead(SQLModel):
    id: int
    email: str
    created_at: datetime


class ProductCreate(SQLModel):
    name: str
    description: str
    template: Optional[str] = None


class ProductRead(SQLModel):
    id: int
    name: str
    description: str
    created_at: datetime
    deleted: bool
    template: Optional[str]


class TemplateVersionCreate(SQLModel):
    docker_image_url: Optional[str] = None


class TemplateVersionRead(SQLModel):
    id: int
    product_id: int
    docker_image_url: Optional[str]
    created_at: datetime


class DeploymentCreate(SQLModel):
    template_id: int
    domainname: str


class DeploymentRead(SQLModel):
    id: int
    user_id: int
    template_id: int
    domainname: str
    created_at: datetime
    deleted: bool
