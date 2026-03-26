from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import (
    PaymentStatus,
    PlanTemplateVersionORM,
    SubscriptionORM,
    SubscriptionRead,
    SubscriptionStatus,
)
from app.services.errors import NotFoundException, ValidationException


def create_subscription(
    session: Session,
    *,
    plan_template_id: int,
    user_id: int,
    payment_status: PaymentStatus = PaymentStatus.CURRENT,
    commit: bool = True,
) -> SubscriptionORM:
    """Create a subscription for a user to a plan template version.

    When called from the deployment service, pass ``commit=False`` so the
    caller can commit both the subscription and deployment atomically.

    Raises ValidationException if the plan template version does not exist
    or is soft-deleted.

    Returns the ORM object (not the read model) so callers that need the
    ID before commit can access it after flush.
    """
    tmpl = session.get(PlanTemplateVersionORM, plan_template_id)
    if not tmpl or tmpl.deleted_at:
        raise ValidationException(
            f"Plan template version {plan_template_id} not found or deleted"
        )

    sub = SubscriptionORM(
        plan_template_id=plan_template_id,
        user_id=user_id,
        payment_status=payment_status,
    )
    session.add(sub)

    if commit:
        session.commit()
        session.refresh(sub)

    return sub


def get_subscription(session: Session, subscription_id: int) -> SubscriptionRead:
    """Get a single subscription by ID.

    Raises NotFoundException if not found.
    """
    if not (sub := session.get(SubscriptionORM, subscription_id)):
        raise NotFoundException("Subscription not found")
    return SubscriptionRead.model_validate(sub)


def list_subscriptions_for_user(
    session: Session, user_id: int
) -> list[SubscriptionRead]:
    """List all subscriptions for a user (active and cancelled)."""
    subs = session.exec(
        select(SubscriptionORM).where(SubscriptionORM.user_id == user_id)
    ).all()
    return [SubscriptionRead.model_validate(s) for s in subs]


def cancel_subscription(
    session: Session, *, subscription_id: int
) -> SubscriptionRead:
    """Cancel a subscription.

    Sets status to 'cancelled' and cancelled_at to now.
    Idempotent: cancelling an already-cancelled subscription is a no-op.

    Raises NotFoundException if not found.
    """
    if not (sub := session.get(SubscriptionORM, subscription_id)):
        raise NotFoundException("Subscription not found")

    if sub.status != SubscriptionStatus.CANCELLED:
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = datetime.now(UTC)
        session.commit()
        session.refresh(sub)

    return SubscriptionRead.model_validate(sub)


def update_payment_status(
    session: Session,
    *,
    subscription_id: int,
    payment_status: PaymentStatus,
) -> SubscriptionRead:
    """Update a subscription's payment status.

    Raises NotFoundException if not found.
    """
    if not (sub := session.get(SubscriptionORM, subscription_id)):
        raise NotFoundException("Subscription not found")

    sub.payment_status = payment_status
    session.commit()
    session.refresh(sub)
    return SubscriptionRead.model_validate(sub)
