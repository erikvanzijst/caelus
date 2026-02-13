from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, ForeignKey, Integer, Index


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)


class UserORM(UserBase, table=True):
    __tablename__ = "user"
    __table_args__ = (
        Index(
            "uq_user_active",
            "email",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deployments: list["DeploymentORM"] = Relationship(back_populates="user")
    deleted_at: Optional[datetime] = Field(default=None)


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    created_at: datetime


class ProductBase(SQLModel):
    name: str
    description: str | None = None
    template_id: Optional[int] = None


class ProductORM(ProductBase, table=True):
    __tablename__ = "product"
    __table_args__ = (
        Index(
            "uq_product_name_active",
            "name",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    template_id: Optional[int] = Field(
        default=None, foreign_key="product_template_version.id", index=True
    )
    template: "ProductTemplateVersionORM" = Relationship(
        back_populates="products", sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id"}
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    templates: list["ProductTemplateVersionORM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={
            "foreign_keys": "ProductTemplateVersionORM.product_id",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )
    deleted_at: Optional[datetime] = Field(default=None)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(SQLModel):
    template_id: Optional[int] = None


class ProductRead(ProductBase):
    id: int
    created_at: datetime


class ProductTemplateVersionBase(SQLModel):
    docker_image_url: Optional[str]
    product_id: int


class ProductTemplateVersionORM(ProductTemplateVersionBase, table=True):
    __tablename__ = "product_template_version"
    __table_args__ = (
        Index(
            "uq_producttemplate_active",
            "docker_image_url", "product_id",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    docker_image_url: Optional[str] = Field(default=None)
    product_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("product.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    product: ProductORM = Relationship(
        back_populates="templates",
        sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id"},
    )
    products: list["ProductORM"] = Relationship(
        back_populates="template", sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id"}
    )
    deployments: list["DeploymentORM"] = Relationship(
        back_populates="template",
        sa_relationship_kwargs={
            "foreign_keys": "DeploymentORM.template_id",
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)


class ProductTemplateVersionCreate(ProductTemplateVersionBase):
    product_id: Optional[int] = None


class ProductTemplateVersionRead(ProductTemplateVersionBase):
    id: Optional[int]
    created_at: datetime
    product: ProductRead


class DeploymentBase(SQLModel):
    template_id: int
    domainname: str
    user_id: Optional[int] = Field(default=None)


class DeploymentORM(DeploymentBase, table=True):
    __tablename__ = "deployment"
    __table_args__ = (
        Index(
            "uq_deployment_active",
            "user_id", "domainname", "template_id",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    user: UserORM = Relationship(back_populates="deployments")
    template_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    template: ProductTemplateVersionORM = Relationship(
        back_populates="deployments",
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.template_id"},
    )
    domainname: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)


class DeploymentCreate(DeploymentBase):
    pass


class DeploymentRead(DeploymentBase):
    id: int
    created_at: datetime
    user: UserRead
    template: ProductTemplateVersionRead
