from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)


class UserORM(UserBase, table=True):
    __tablename__ = "user"
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    created_at: datetime



class ProductBase(SQLModel):
    name: str
    description: str
    template_id: Optional[int]



class ProductORM(ProductBase, table=True):
    __tablename__ = "product"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)  # TODO: make unique together with `deleted`
    template_id: Optional[int] = Field(default=None, foreign_key="product_template_version.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    # templates: Mapped[list["ProductTemplateVersionORM"]] = Relationship(back_populates="product")
    deleted: bool = Field(default=False)


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: int
    created_at: datetime


class ProductTemplateVersionBase(SQLModel):
    docker_image_url: Optional[str]
    product_id: int


class ProductTemplateVersionORM(ProductTemplateVersionBase, table=True):
    __tablename__ = "product_template_version"

    id: Optional[int] = Field(default=None, primary_key=True)
    docker_image_url: Optional[str] = Field(default=None)
    product_id: int = Field(foreign_key="product.id", index=True)
    # product: Mapped["ProductORM"] | None = Relationship(back_populates="templates")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted: bool = Field(default=False)


class ProductTemplateVersionCreate(ProductTemplateVersionBase):
    pass


class ProductTemplateVersionRead(ProductTemplateVersionBase):
    id: Optional[int]
    created_at: datetime


class DeploymentBase(SQLModel):
    template_id: int
    domainname: str
    user_id: int


class DeploymentORM(DeploymentBase, table=True):
    __tablename__ = "deployment"
    # TODO: Create compound unique constraint on (user_id, domainname, template_id, deleted)
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    template_id: int = Field(foreign_key="product_template_version.id", index=True)
    domainname: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted: bool = Field(default=False)


class DeploymentCreate(DeploymentBase):
    pass

class DeploymentRead(DeploymentBase):
    id: int
    created_at: datetime
