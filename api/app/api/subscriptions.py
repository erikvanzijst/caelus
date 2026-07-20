from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, status
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
    subscription_id: int = Path(..., description="ID of the subscription being accessed."),
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


@router.get(
    "/users/{user_id}/subscriptions",
    response_model=list[SubscriptionRead],
    summary="List a user's subscriptions",
    response_description="All subscriptions for the user, active and cancelled.",
    responses={
        403: {"description": "Caller may only access their own subscriptions."},
    },
)
def list_subscriptions(
    user_id: int = Path(..., description="ID of the user whose subscriptions to list."),
    _current_user: UserORM = Depends(require_self),
    session: Session = Depends(get_session),
) -> list[SubscriptionRead]:
    """List all subscriptions belonging to a user.

    Returns both active and cancelled subscriptions, each including its plan
    and pricing details. A user with no subscriptions receives an empty array.

    ## Authorization
    You may only list your own subscriptions; administrators may list any
    user's subscriptions. Other callers receive `403 Forbidden`.

    ## Parameters
    - **user_id** (path) — the user whose subscriptions are returned.

    ## Errors
    - **403 Forbidden** — attempting to access another user's subscriptions
      without administrator privileges.
    """
    return subscription_service.list_subscriptions_for_user(session, user_id)


@router.get(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionRead,
    summary="Get a subscription",
    response_description="The requested subscription with plan template details.",
    responses={
        403: {"description": "Caller does not own this subscription."},
        404: {"description": "No subscription exists with this id."},
    },
)
def get_subscription(
    subscription_id: int = Path(..., description="ID of the subscription to retrieve."),
    _current_user: UserORM = Depends(_require_subscription_owner),
    session: Session = Depends(get_session),
) -> SubscriptionRead:
    """Retrieve a single subscription by ID.

    The response includes the subscription's `status`, `payment_status`,
    `cancelled_at`, and its plan and pricing details.

    ## Authorization
    You may only retrieve subscriptions you own; administrators may retrieve
    any subscription. Other callers receive `403 Forbidden`.

    ## Parameters
    - **subscription_id** (path) — the subscription to retrieve.

    ## Errors
    - **403 Forbidden** — the subscription belongs to another user and the
      caller is not an administrator.
    - **404 Not Found** — no subscription exists with this id.
    """
    return subscription_service.get_subscription(session, subscription_id)


@router.put(
    "/subscriptions/{subscription_id}",
    response_model=SubscriptionRead,
    summary="Update a subscription",
    response_description="The updated subscription.",
    responses={
        400: {"description": "No valid update fields, or an unsupported transition (e.g. reactivating a cancelled subscription)."},
        403: {"description": "Caller does not own this subscription."},
        404: {"description": "No subscription exists with this id."},
    },
)
def update_subscription(
    subscription_id: int = Path(..., description="ID of the subscription to update."),
    payload: SubscriptionUpdate = ...,
    _current_user: UserORM = Depends(_require_subscription_owner),
    session: Session = Depends(get_session),
) -> SubscriptionRead:
    """Update a subscription's lifecycle status or payment status.

    Supply exactly one meaningful change in the request body. Only cancellation
    and payment-status changes are supported; reactivation is not.

    ## Authorization
    You may only update subscriptions you own; administrators may update any
    subscription. Other callers receive `403 Forbidden`.

    ## Parameters
    - **subscription_id** (path) — the subscription to update.

    ## Request body
    `SubscriptionUpdate` — both fields are optional; evaluated in this order:
    - **status = "cancelled"** cancels the subscription and stamps
      `cancelled_at`. Idempotent: cancelling an already-cancelled subscription
      leaves `cancelled_at` unchanged.
    - **status = "active"** is rejected — reactivating a cancelled subscription
      is not supported (→ 400).
    - **payment_status** updates the billing state (`current` ↔ `arrears`)
      without changing the lifecycle `status`.
    - If neither field yields a valid update, the request is rejected (→ 400).

    ## Behavior
    Cancellation is idempotent and does not alter `payment_status`. Updating
    `payment_status` leaves the lifecycle `status` unchanged. `status` is
    evaluated before `payment_status`, so a payload setting both is handled by
    the `status` branch first.

    ## Errors
    - **400 Bad Request** — no valid fields provided, or an unsupported
      transition (reactivating a cancelled subscription).
    - **403 Forbidden** — the subscription belongs to another user and the
      caller is not an administrator.
    - **404 Not Found** — no subscription exists with this id.
    """
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
