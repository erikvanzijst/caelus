from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.deps import get_current_user, require_self
from app.models import (
    SubscriptionORM,
    SubscriptionRead,
    SubscriptionStatus,
    PaymentStatus,
    UserORM,
)
from app.services import subscriptions as subscription_service
from app.services.errors import ValidationException

router = APIRouter(tags=["subscriptions"])


class SubscriptionUpdate(BaseModel):
    status: Optional[SubscriptionStatus] = None
    payment_status: Optional[PaymentStatus] = None


def _require_subscription_owner(
    subscription_id: int,
    current_user: UserORM = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UserORM:
    """Verify the current user owns the subscription, or is an admin."""
    sub = session.get(SubscriptionORM, subscription_id)
    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    if sub.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return current_user


@router.get("/users/{user_id}/subscriptions", response_model=list[SubscriptionRead])
def list_subscriptions(
    user_id: int,
    _current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> list[SubscriptionRead]:
    return subscription_service.list_subscriptions_for_user(session, user_id)


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionRead)
def get_subscription(
    subscription_id: int,
    _current_user: UserORM = Depends(_require_subscription_owner),
    session: Session = Depends(get_session),
) -> SubscriptionRead:
    return subscription_service.get_subscription(session, subscription_id)


@router.put("/subscriptions/{subscription_id}", response_model=SubscriptionRead)
def update_subscription(
    subscription_id: int,
    payload: SubscriptionUpdate,
    _current_user: UserORM = Depends(_require_subscription_owner),
    session: Session = Depends(get_session),
) -> SubscriptionRead:
    if payload.status == SubscriptionStatus.CANCELLED:
        return subscription_service.cancel_subscription(
            session, subscription_id=subscription_id
        )
    if payload.status == SubscriptionStatus.ACTIVE:
        raise ValidationException("Reactivating a cancelled subscription is not supported")
    if payload.payment_status is not None:
        return subscription_service.update_payment_status(
            session,
            subscription_id=subscription_id,
            payment_status=payload.payment_status,
        )
    raise ValidationException("No valid update fields provided")
