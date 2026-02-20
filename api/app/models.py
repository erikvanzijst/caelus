from datetime import datetime
from typing import Optional, Any

from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, ForeignKey, Integer, Index, JSON, Text, String

from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETED


class UserBase(SQLModel):
    email: str


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
    email: str = Field(nullable=False, unique=False)
    is_admin: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deployments: list["DeploymentORM"] = Relationship(back_populates="user")
    deleted_at: Optional[datetime] = Field(default=None)


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    is_admin: bool
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
    name: str = Field()
    # The product's canonical template used for new deployments:
    template_id: Optional[int] = Field(default=None, foreign_key="product_template_version.id", index=True)
    template: "ProductTemplateVersionORM" = Relationship(
        back_populates="products", sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id"})
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    templates: list["ProductTemplateVersionORM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id"},
    )
    deleted_at: Optional[datetime] = Field(default=None)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(SQLModel):
    id: Optional[int] = None
    template_id: Optional[int] = None
    description: str | None = None


class ProductReadBase(ProductBase):
    id: int
    created_at: datetime


class ProductRead(ProductReadBase):
    template: Optional['ProductTemplateVersionRead']


class ProductTemplateVersionBase(SQLModel):
    product_id: int
    chart_ref: str = None
    chart_version: str = None
    chart_digest: Optional[str] = None
    version_label: Optional[str] = None
    default_values_json: Optional[dict[str, Any]] = None
    values_schema_json: Optional[dict[str, Any]] = None
    capabilities_json: Optional[dict[str, Any]] = None


class ProductTemplateVersionORM(ProductTemplateVersionBase, table=True):
    __tablename__ = "product_template_version"
    __table_args__ = (
        Index(
            "uq_producttemplate_active",
            "chart_ref", "chart_version", "product_id",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    version_label: Optional[str] = Field(default=None)
    chart_ref: str
    chart_version: str
    default_values_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    values_schema_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    capabilities_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    health_timeout_sec: Optional[int] = Field(default=None)
    product_id: int = Field(sa_column=Column(Integer, ForeignKey("product.id"), nullable=False, index=True))
    product: ProductORM = Relationship(back_populates="templates",
                                       sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id"})
    products: list["ProductORM"] = Relationship(back_populates="template",
                                                sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id"})
    deployments: list["DeploymentORM"] = Relationship(back_populates="applied_template",
                                                      sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id"})
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)


class ProductTemplateVersionCreate(ProductTemplateVersionBase):
    product_id: Optional[int] = None


class ProductTemplateVersionRead(ProductTemplateVersionBase):
    id: Optional[int]
    created_at: datetime
    product: ProductReadBase


class DeploymentBase(SQLModel):
    desired_template_id: int
    domainname: str
    user_id: int
    user_values_json: Optional[dict[str, Any]] = Field(default=None)


class DeploymentORM(DeploymentBase, table=True):
    __tablename__ = "deployment"
    __table_args__ = (
        Index(
            "uq_deployment_active",
            "user_id", "domainname", "desired_template_id",
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
        ),
        Index(
            "uq_domainname_active",
            "domainname",
            unique=True,
            sqlite_where=Column("status").is_not(DEPLOYMENT_STATUS_DELETED),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    desired_template_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("product_template_version.id"),
            nullable=False,
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
    domainname: str = Field(index=True)
    deployment_uid: str = Field(sa_column=Column(String(), nullable=False, index=True))
    user_values_json: Optional[dict[str, Any]] = Field(default=None, sa_column=Column(JSON, nullable=True))
    status: str = Field(default="pending", nullable=False, index=True)
    generation: int = Field(default=1, nullable=False)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    last_reconcile_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)
    reconcile_jobs: list["DeploymentReconcileJobORM"] = Relationship(back_populates="deployment")
    user: UserORM = Relationship(back_populates="deployments")
    desired_template: Optional[ProductTemplateVersionORM] = Relationship(sa_relationship_kwargs={"foreign_keys": "DeploymentORM.desired_template_id"})
    applied_template: Optional[ProductTemplateVersionORM] = Relationship(sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id"})


class DeploymentCreate(DeploymentBase):
    user_values_json: Optional[dict[str, Any]] = Field(default=None)
    user_id: Optional[int] = None


class DeploymentUpdate(DeploymentBase):
    id: Optional[int] = None
    user_id: Optional[int] = None
    domainname: Optional[str] = None
    desired_template_id: Optional[int] = Field(default=None)
    user_values_json: Optional[dict[str, Any]] = Field(default=None)


class DeploymentRead(DeploymentBase):
    id: int
    created_at: datetime
    user: UserRead
    desired_template: ProductTemplateVersionRead
    applied_template: Optional[ProductTemplateVersionRead]
    deployment_uid: Optional[str] = None
    status: str = Field(default="pending")
    generation: int = Field(default=1)
    last_error: Optional[str] = None
    last_reconcile_at: Optional[datetime] = None


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
    __table_args__ = (
        Index(
            "uq_open_reconcile_job_per_deployment",
            "deployment_id",
            unique=True,
            sqlite_where=Column("status").in_(("queued", "running")),
            postgresql_where=Column("status").in_(("queued", "running")),
        ),
    )

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
