import uuid as uuid_mod
from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import ConfigDict
from sqlmodel import Field, SQLModel, Relationship
from sqlalchemy import BigInteger, Column, Enum as SAEnum, ForeignKey, Integer, Index, JSON, String, Text, Uuid, func

from app.models.core import _utcnow, ProductORM, UserORM


class BillingInterval(StrEnum):
    MONTHLY = "monthly"
    ANNUAL = "annual"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    CURRENT = "current"
    ARREARS = "arrears"


class MolliePaymentStatus(StrEnum):
    OPEN = "open"
    PENDING = "pending"
    AUTHORIZED = "authorized"
    PAID = "paid"
    CANCELED = "canceled"
    EXPIRED = "expired"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Plan & PlanTemplateVersion
# ---------------------------------------------------------------------------


class PlanBase(SQLModel):
    name: str
    product_id: int
    template_id: Optional[int] = None
    sort_order: Optional[int] = None


class PlanORM(PlanBase, table=True):
    __tablename__ = "plan"
    __table_args__ = (
        Index(
            "uq_plan_name_active",
            "product_id",
            func.lower(Column("name")),
            unique=True,
            sqlite_where=Column("deleted_at").is_(None),
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(nullable=False)
    product_id: int = Field(
        sa_column=Column(Integer, ForeignKey("product.id"), nullable=False, index=True)
    )
    # Canonical plan template used for new subscriptions:
    template_id: Optional[int] = Field(
        default=None, foreign_key="plan_template_version.id", index=True
    )
    sort_order: Optional[int] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)

    product: ProductORM = Relationship(
        back_populates="plans",
        sa_relationship_kwargs={"foreign_keys": "PlanORM.product_id", "lazy": "joined"},
    )
    template: "PlanTemplateVersionORM" = Relationship(
        back_populates="plans",
        sa_relationship_kwargs={"foreign_keys": "PlanORM.template_id", "lazy": "joined"},
    )
    # The set of all plan templates, past and present, for this product:
    templates: list["PlanTemplateVersionORM"] = Relationship(
        back_populates="plan",
        sa_relationship_kwargs={"foreign_keys": "PlanTemplateVersionORM.plan_id"},
    )


class PlanCreate(SQLModel):
    name: str
    sort_order: Optional[int] = None


class PlanUpdate(SQLModel):
    name: Optional[str] = None
    template_id: Optional[int] = None
    sort_order: Optional[int] = None


class PlanReadBase(PlanBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class PlanTemplateVersionBase(SQLModel):
    plan_id: int
    price_cents: int
    billing_interval: BillingInterval
    storage_bytes: Optional[int] = None
    description: Optional[str] = None


class PlanTemplateVersionORM(PlanTemplateVersionBase, table=True):
    __tablename__ = "plan_template_version"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_id: int = Field(
        sa_column=Column(Integer, ForeignKey("plan.id"), nullable=False, index=True)
    )
    price_cents: int = Field(nullable=False)
    billing_interval: BillingInterval = Field(
        sa_column=Column(
            SAEnum(BillingInterval, values_callable=lambda e: [m.value for m in e]),
            nullable=False,
        )
    )
    storage_bytes: Optional[int] = Field(
        default=None, sa_column=Column(BigInteger, nullable=True)
    )
    # Uses Markdown for formatting:
    description: Optional[str] = Field(default=None, sa_column=Column(Text(), nullable=True))
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    deleted_at: Optional[datetime] = Field(default=None)

    plan: PlanORM = Relationship(
        back_populates="templates",
        sa_relationship_kwargs={"foreign_keys": "PlanTemplateVersionORM.plan_id", "lazy": "joined"},
    )
    plans: list[PlanORM] = Relationship(
        back_populates="template",
        sa_relationship_kwargs={"foreign_keys": "PlanORM.template_id"},
    )
    subscriptions: list["SubscriptionORM"] = Relationship(back_populates="plan_template")


class PlanTemplateVersionCreate(SQLModel):
    price_cents: int
    billing_interval: BillingInterval
    storage_bytes: Optional[int] = None
    description: Optional[str] = None


class PlanTemplateVersionRead(PlanTemplateVersionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    plan: Optional[PlanReadBase] = None


class PlanRead(PlanReadBase):
    template: Optional[PlanTemplateVersionRead] = None


# ---------------------------------------------------------------------------
# Subscription
# ---------------------------------------------------------------------------


class SubscriptionBase(SQLModel):
    plan_template_id: int
    user_id: int
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    payment_status: PaymentStatus = PaymentStatus.CURRENT
    cancelled_at: Optional[datetime] = None


class SubscriptionORM(SubscriptionBase, table=True):
    __tablename__ = "subscription"

    id: Optional[int] = Field(default=None, primary_key=True)
    plan_template_id: int = Field(
        sa_column=Column(
            Integer, ForeignKey("plan_template_version.id"), nullable=False, index=True
        )
    )
    user_id: int = Field(foreign_key="user.id", index=True)
    status: SubscriptionStatus = Field(
        default=SubscriptionStatus.ACTIVE,
        sa_column=Column(
            SAEnum(SubscriptionStatus, values_callable=lambda e: [m.value for m in e]),
            nullable=False,
        ),
    )
    payment_status: PaymentStatus = Field(
        default=PaymentStatus.CURRENT,
        sa_column=Column(
            SAEnum(PaymentStatus, values_callable=lambda e: [m.value for m in e]),
            nullable=False,
        ),
    )
    cancelled_at: Optional[datetime] = Field(default=None)
    mollie_subscription_id: Optional[str] = Field(default=None)
    mollie_mandate_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)

    plan_template: PlanTemplateVersionORM = Relationship(
        back_populates="subscriptions",
        sa_relationship_kwargs={"foreign_keys": "SubscriptionORM.plan_template_id", "lazy": "joined"},
    )
    user: UserORM = Relationship(
        back_populates="subscriptions",
        sa_relationship_kwargs={"foreign_keys": "SubscriptionORM.user_id", "lazy": "joined"},
    )
    deployments: list["DeploymentORM"] = Relationship(back_populates="subscription")
    mollie_payments: list["MolliePaymentORM"] = Relationship(back_populates="subscription")


class SubscriptionRead(SubscriptionBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    plan_template: Optional[PlanTemplateVersionRead] = None


# ---------------------------------------------------------------------------
# Mollie Payment
# ---------------------------------------------------------------------------


class MolliePaymentORM(SQLModel, table=True):
    __tablename__ = "mollie_payment"

    id: uuid_mod.UUID = Field(
        default_factory=uuid_mod.uuid4,
        sa_column=Column(Uuid, primary_key=True),
    )
    subscription_id: int = Field(
        sa_column=Column(Integer, ForeignKey("subscription.id"), nullable=False, index=True)
    )
    mollie_payment_id: str = Field(
        sa_column=Column(String(), unique=True, nullable=False)
    )
    status: MolliePaymentStatus = Field(
        sa_column=Column(
            SAEnum(MolliePaymentStatus, values_callable=lambda e: [m.value for m in e]),
            nullable=False,
        )
    )
    sequence_type: str = Field(nullable=False)
    amount_cents: int = Field(nullable=False)
    created_at: datetime = Field(default_factory=_utcnow, nullable=False)
    payload: Optional[dict] = Field(default=None, sa_column=Column(JSON, nullable=True))

    subscription: SubscriptionORM = Relationship(
        back_populates="mollie_payments",
        sa_relationship_kwargs={"foreign_keys": "MolliePaymentORM.subscription_id", "lazy": "joined"},
    )
