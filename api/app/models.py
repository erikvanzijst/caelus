from datetime import datetime
from typing import Optional, Any

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, ForeignKey, Integer, Index, JSON


class UserBase(SQLModel):
    email: str = Field(index=True, unique=True)
    is_admin: bool = Field(default=False, nullable=False)


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
    version_label: Optional[str] = None
    package_type: str = Field(default="helm-chart")
    chart_ref: Optional[str] = None
    chart_version: Optional[str] = None
    chart_digest: Optional[str] = None
    default_values_json: Optional[dict[str, Any]] = None
    values_schema_json: Optional[dict[str, Any]] = None
    capabilities_json: Optional[dict[str, Any]] = None
    health_timeout_sec: Optional[int] = None


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
    version_label: Optional[str] = Field(default=None)
    package_type: str = Field(default="helm-chart", nullable=False)
    chart_ref: Optional[str] = Field(default=None)
    chart_version: Optional[str] = Field(default=None)
    chart_digest: Optional[str] = Field(default=None)
    default_values_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    values_schema_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    capabilities_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    health_timeout_sec: Optional[int] = Field(default=None)
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
    user_values_json: Optional[dict[str, Any]] = Field(
        default=None, alias="user_values"
    )
    user_id: Optional[int] = Field(default=None)
    deployment_uid: Optional[str] = None
    namespace_name: Optional[str] = None
    release_name: Optional[str] = None
    desired_template_id: Optional[int] = None
    applied_template_id: Optional[int] = None
    status: str = Field(default="pending")
    generation: int = Field(default=1)
    last_error: Optional[str] = None
    last_reconcile_at: Optional[datetime] = None

    model_config = {"populate_by_name": True}


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
    desired_template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id"),
            nullable=True,
            index=True,
        ),
    )
    applied_template_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id"),
            nullable=True,
            index=True,
        ),
    )
    desired_template: Optional[ProductTemplateVersionORM] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.desired_template_id"},
    )
    applied_template: Optional[ProductTemplateVersionORM] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id"},
    )
    domainname: str = Field(index=True)
    deployment_uid: Optional[str] = Field(default=None, index=True)
    namespace_name: Optional[str] = Field(default=None, index=True)
    release_name: Optional[str] = Field(default=None, index=True)
    user_values_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    status: str = Field(default="pending", nullable=False)
    generation: int = Field(default=1, nullable=False)
    last_error: Optional[str] = Field(default=None)
    last_reconcile_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)
    reconcile_jobs: list["DeploymentReconcileJobORM"] = Relationship(
        back_populates="deployment",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "passive_deletes": True,
        },
    )


class DeploymentCreate(DeploymentBase):
    pass


class DeploymentUpdate(SQLModel):
    domainname: Optional[str] = None
    user_values_json: Optional[dict[str, Any]] = Field(default=None, alias="user_values")

    model_config = {"populate_by_name": True}


class DeploymentUpgrade(SQLModel):
    template_id: int


class DeploymentRead(DeploymentBase):
    id: int
    created_at: datetime
    user: UserRead
    template: ProductTemplateVersionRead


class DeploymentReconcileJobBase(SQLModel):
    deployment_id: int
    reason: str
    status: str = Field(default="queued")
    run_after: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    attempt: int = Field(default=0, nullable=False)
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    last_error: Optional[str] = None


class DeploymentReconcileJobORM(DeploymentReconcileJobBase, table=True):
    __tablename__ = "deployment_reconcile_job"

    id: Optional[int] = Field(default=None, primary_key=True)
    deployment_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("deployment.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    deployment: DeploymentORM = Relationship(back_populates="reconcile_jobs")
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
