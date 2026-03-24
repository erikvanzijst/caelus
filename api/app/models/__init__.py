"""
Models package — re-exports all models so ``from app.models import X`` keeps
working everywhere.

The models are split across two modules:
  - core.py:    User, Product, ProductTemplateVersion, Deployment,
                DeploymentReconcileJob (and their Base/Create/Update/Read
                variants).
  - billing.py: Plan, PlanTemplateVersion, Subscription (and their
                Base/Create/Update/Read variants), plus the BillingInterval,
                SubscriptionStatus, and PaymentStatus enums.
"""

from app.models.core import (  # noqa: F401
    _utcnow,
    DeploymentBase,
    DeploymentCreate,
    DeploymentORM,
    DeploymentRead,
    DeploymentReconcileJobBase,
    DeploymentReconcileJobORM,
    DeploymentUpdate,
    ProductBase,
    ProductCreate,
    ProductORM,
    ProductRead,
    ProductReadBase,
    ProductTemplateVersionBase,
    ProductTemplateVersionCreate,
    ProductTemplateVersionORM,
    ProductTemplateVersionRead,
    ProductUpdate,
    SQLModel,
    UserBase,
    UserCreate,
    UserORM,
    UserRead,
)

from app.models.billing import (  # noqa: F401
    BillingInterval,
    MolliePaymentORM,
    MolliePaymentStatus,
    PaymentStatus,
    PlanBase,
    PlanCreate,
    PlanORM,
    PlanRead,
    PlanReadBase,
    PlanTemplateVersionBase,
    PlanTemplateVersionCreate,
    PlanTemplateVersionORM,
    PlanTemplateVersionRead,
    PlanUpdate,
    SubscriptionBase,
    SubscriptionORM,
    SubscriptionRead,
    SubscriptionStatus,
)

# Rebuild DeploymentRead so Pydantic resolves the SubscriptionRead
# forward reference (defined in billing.py, referenced in core.py).
DeploymentRead.model_rebuild()
