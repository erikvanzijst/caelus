from datetime import UTC, datetime
from typing import Optional, Any

from pydantic import ConfigDict, model_validator
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import Column, ForeignKey, Integer, Index, JSON, Text, String, func

from app.services.reconcile_constants import DEPLOYMENT_STATUS_DELETED


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserBase(SQLModel):
    email: str


class UserORM(UserBase, table=True):
    __tablename__ = "user"
    __table_args__ = (
        Index(
            "uq_user_active",
            func.lower(Column("email")),
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(nullable=False, unique=False)
    is_admin: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deployments: list["DeploymentORM"] = Relationship(back_populates="user")
    subscriptions: list["SubscriptionORM"] = Relationship(
        back_populates="user",
        sa_relationship_kwargs={"foreign_keys": "SubscriptionORM.user_id"},
    )
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
            func.lower(Column("name")),
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field()
    # The product's canonical template used for new deployments:
    template_id: Optional[int] = Field(
        default=None, foreign_key="product_template_version.id", index=True
    )
    # Relative path to product icon under STATIC_PATH (e.g., "icons/<sha1>.png")
    rel_icon_path: Optional[str] = Field(default=None, nullable=True)
    template: "ProductTemplateVersionORM" = Relationship(
        back_populates="products",
        sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id", "lazy": "joined"},
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    templates: list["ProductTemplateVersionORM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id"},
    )
    plans: list["PlanORM"] = Relationship(
        back_populates="product",
        sa_relationship_kwargs={"foreign_keys": "PlanORM.product_id"},
    )
    deleted_at: Optional[datetime] = Field(default=None)


class ProductCreate(ProductBase):
    pass


class ProductUpdate(SQLModel):
    id: Optional[int] = None
    name: str | None = None
    template_id: Optional[int] = None
    description: str | None = None


class ProductReadBase(ProductBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    icon_url: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _compute_icon_url(cls, data: Any) -> Any:
        """Derive icon_url from rel_icon_path when serializing from ORM."""
        from app.config import get_static_url_base

        if isinstance(data, dict):
            rel = data.get("rel_icon_path")
        else:
            rel = getattr(data, "rel_icon_path", None)
        if rel:
            if isinstance(data, dict):
                data.setdefault("icon_url", f"{get_static_url_base()}/{rel}")
            else:
                # For ORM objects, we need to return a dict so we can inject icon_url
                d = {k: getattr(data, k) for k in cls.model_fields if hasattr(data, k)}
                d["icon_url"] = f"{get_static_url_base()}/{rel}"
                return d
        return data


class ProductRead(ProductReadBase):
    template: Optional["ProductTemplateVersionRead"]


class ProductTemplateVersionBase(SQLModel):
    product_id: int
    chart_ref: str = None
    chart_version: str = None
    chart_digest: Optional[str] = None
    version_label: Optional[str] = None
    system_values_json: Optional[dict[str, Any]] = None
    values_schema_json: Optional[dict[str, Any]] = None
    capabilities_json: Optional[dict[str, Any]] = None


class ProductTemplateVersionORM(ProductTemplateVersionBase, table=True):
    __tablename__ = "product_template_version"

    id: Optional[int] = Field(default=None, primary_key=True)
    version_label: Optional[str] = Field(default=None)
    chart_ref: str
    chart_version: str
    system_values_json: Optional[dict[str, Any]] = Field(
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
        sa_column=Column(Integer, ForeignKey("product.id"), nullable=False, index=True)
    )
    product: ProductORM = Relationship(
        back_populates="templates",
        sa_relationship_kwargs={"foreign_keys": "ProductTemplateVersionORM.product_id", "lazy": "joined"},
    )
    products: list["ProductORM"] = Relationship(
        back_populates="template", sa_relationship_kwargs={"foreign_keys": "ProductORM.template_id"}
    )
    deployments: list["DeploymentORM"] = Relationship(
        back_populates="applied_template",
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id"},
    )
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)


class ProductTemplateVersionCreate(ProductTemplateVersionBase):
    product_id: Optional[int] = None


class ProductTemplateVersionRead(ProductTemplateVersionBase):
    id: Optional[int]
    created_at: datetime
    product: ProductReadBase


# ---------------------------------------------------------------------------
# Deployment
# ---------------------------------------------------------------------------


class DeploymentBase(SQLModel):
    desired_template_id: int
    user_id: int
    user_values_json: Optional[dict[str, Any]] = Field(default=None)


class DeploymentORM(DeploymentBase, table=True):
    __tablename__ = "deployment"
    __table_args__ = (
        Index(
            "uq_deployment_active",
            "user_id",
            "hostname",
            "desired_template_id",
            unique=True,
            sqlite_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
            postgresql_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
        ),
        Index(
            "uq_hostname_active",
            "hostname",
            unique=True,
            sqlite_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
            postgresql_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
        ),
        Index(
            "uq_deployment_ns_name_active",
            "namespace",
            "name",
            unique=True,
            sqlite_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
            postgresql_where=Column("status") != DEPLOYMENT_STATUS_DELETED,
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
    hostname: Optional[str] = Field(
        default=None, sa_column=Column(String(), nullable=True, index=True)
    )
    name: str = Field(sa_column=Column(String(), nullable=False, index=True))
    namespace: str = Field(sa_column=Column(String(), nullable=False, index=True))
    user_values_json: Optional[dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    status: str = Field(default="pending", nullable=False, index=True)
    generation: int = Field(default=1, nullable=False)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    last_reconcile_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)
    reconcile_jobs: list["DeploymentReconcileJobORM"] = Relationship(back_populates="deployment")
    user: UserORM = Relationship(back_populates="deployments", sa_relationship_kwargs={"lazy": "joined"})
    desired_template: Optional[ProductTemplateVersionORM] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.desired_template_id", "lazy": "joined"}
    )
    applied_template: Optional[ProductTemplateVersionORM] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.applied_template_id", "lazy": "joined"}
    )
    subscription_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("subscription.id"),
            nullable=True,
            index=True,
        ),
    )
    subscription: Optional["SubscriptionORM"] = Relationship(
        back_populates="deployments",
        sa_relationship_kwargs={"foreign_keys": "DeploymentORM.subscription_id", "lazy": "joined"},
    )


class DeploymentCreate(DeploymentBase):
    model_config = ConfigDict(extra="forbid")
    plan_template_id: Optional[int] = None
    user_values_json: dict[str, Any] = Field(default=dict())
    user_id: Optional[int] = None


class DeploymentUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")
    id: Optional[int] = None
    user_id: Optional[int] = None
    desired_template_id: int
    user_values_json: Optional[dict[str, Any]] = Field(default=None)


class DeploymentRead(DeploymentBase):
    id: int
    created_at: datetime
    user: UserRead
    hostname: Optional[str] = None
    desired_template: ProductTemplateVersionRead
    applied_template: Optional[ProductTemplateVersionRead]
    subscription_id: Optional[int] = None
    name: Optional[str] = None
    namespace: Optional[str] = None
    status: str = Field(default="pending")
    generation: int = Field(default=1)
    last_error: Optional[str] = None
    last_reconcile_at: Optional[datetime] = None


class DeploymentReconcileJobBase(SQLModel):
    deployment_id: int
    reason: str
    status: str = Field(default="queued")
    run_after: datetime = Field(default_factory=_utcnow, nullable=False)
    # TODO: remove this field. Jobs are not being retried:
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
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=_utcnow, nullable=False)
