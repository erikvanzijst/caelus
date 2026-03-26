from __future__ import annotations

import logging
from datetime import date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Form
from sqlmodel import Session, select

from app.config import get_settings
from app.db import get_session
from app.deps import get_payment_provider
from app.models import (
    MolliePaymentORM,
    MolliePaymentStatus,
    PaymentStatus,
    SubscriptionORM,
)
from app.models.billing import BillingInterval
from app.services.jobs import JobService
from app.services.mollie import PaymentProvider
from app.services.reconcile_constants import (
    DEPLOYMENT_STATUS_PENDING,
    DEPLOYMENT_STATUS_PROVISIONING,
    JOB_REASON_CREATE,
)
from app.util import amend_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhooks"])

TERMINAL_FAILURE_STATUSES = {"failed", "expired", "canceled"}

BILLING_INTERVAL_TO_MOLLIE = {
    BillingInterval.MONTHLY: "1 month",
    BillingInterval.ANNUAL: "12 months",
}

BILLING_INTERVAL_MONTHS = {
    BillingInterval.MONTHLY: 1,
    BillingInterval.ANNUAL: 12,
}


@router.post("/webhooks/mollie", status_code=200)
def mollie_webhook(
    id: str = Form(...),
    session: Session = Depends(get_session),
    payment_provider: PaymentProvider | None = Depends(get_payment_provider),
) -> dict:
    """Receive Mollie payment status notifications.

    Unauthenticated — Mollie POSTs form-encoded ``id=tr_xxxxx``.
    Always returns 200 to avoid leaking information.
    """
    if payment_provider is None:
        logger.warning("Webhook received but no payment provider configured, ignoring id=%s", id)
        return {}
    logger.info("Received Mollie webhook for payment id=%s", id)

    # Never trust the webhook body alone — fetch the real status from Mollie.
    try:
        payment_info = payment_provider.get_payment(id)
    except Exception:
        logger.exception("Failed to fetch payment from Mollie id=%s", id)
        return {}

    # --- Lookup: find MolliePaymentORM and subscription ---
    mollie_payment = session.exec(
        select(MolliePaymentORM).where(MolliePaymentORM.mollie_payment_id == id)
    ).one_or_none()

    if mollie_payment:
        # Known payment (first payment created during deployment, or previously seen recurring)
        sub = session.get(SubscriptionORM, mollie_payment.subscription_id)
        logger.info(f"Found Caelus subscription ({sub.id}) for this payment ({id}) -- must be a first payment")
    elif payment_info.subscription_id:
        # New recurring payment — look up by Mollie subscription ID
        logger.info(f"This Mollie payment id is new to us (no known subscription) and hence must be recurring payment; "
                    f"retrieve through 'mollie_subscription_id' ({payment_info.subscription_id}) subscription id={payment_info.subscription_id}")
        sub = session.exec(
            select(SubscriptionORM).where(
                SubscriptionORM.mollie_subscription_id == payment_info.subscription_id
            )
        ).one_or_none()

        if sub:
            logger.info(f"Found Caelus subscription ({sub.id}) for this payment ({id}) -- record the recurring payment")
            mollie_payment = MolliePaymentORM(
                subscription_id=sub.id,
                mollie_payment_id=id,
                status=MolliePaymentStatus(payment_info.status),
                sequence_type="recurring",
                amount_cents=sub.plan_template.price_cents,
            )
            session.add(mollie_payment)
        else:
            logger.warning(f"No matching subscription found for Mollie subscription id={payment_info.subscription_id}")
    else:
        logger.warning(f"Unknow payment without Mollie 'subscription_id' reference -- ignoring")
        sub = None

    if not sub:
        logger.warning("Webhook for unknown payment id=%s, no matching subscription", id)
        return {}

    # Update payment record status and payload
    if mollie_payment:
        mollie_payment.status = MolliePaymentStatus(payment_info.status)
        mollie_payment.payload = payment_info.payload

    # --- Process based on payment type and status ---
    is_first = mollie_payment is not None and mollie_payment.sequence_type == "first"
    is_paid = payment_info.status == "paid"
    is_failed = payment_info.status in TERMINAL_FAILURE_STATUSES

    if is_first and is_paid:
        _handle_first_payment_paid(session, sub, payment_info, payment_provider)
    elif is_first and is_failed:
        _handle_first_payment_failed(sub)
    elif not is_first and is_paid:
        _handle_recurring_payment_paid(sub)
    elif not is_first and is_failed:
        _handle_recurring_payment_failed(sub)
    else:
        logger.warning("Ignoring webhook for payment id=%s with status=%s", id, payment_info.status)

    session.commit()
    return {}


def _handle_first_payment_paid(
    session: Session,
    sub: SubscriptionORM,
    payment_info,
    payment_provider: PaymentProvider,
) -> None:
    """First payment succeeded: provision deployment, create recurring subscription."""
    logger.info("First payment succeeded for subscription=%s", sub.id)
    was_pending = sub.payment_status == PaymentStatus.PENDING

    sub.payment_status = PaymentStatus.CURRENT
    sub.mollie_mandate_id = payment_info.mandate_id

    # Transition deployment(s) from pending → provisioning
    for deployment in sub.deployments:
        if deployment.status == DEPLOYMENT_STATUS_PENDING:
            deployment.status = DEPLOYMENT_STATUS_PROVISIONING

    # Only enqueue reconcile on pending → current transition (idempotency)
    if was_pending:
        session.flush()
        for deployment in sub.deployments:
            if deployment.status == DEPLOYMENT_STATUS_PROVISIONING:
                JobService(session).enqueue_job(
                    deployment_id=deployment.id, reason=JOB_REASON_CREATE,
                )

    # Create Mollie recurring subscription (idempotent: skip if already created)
    if not sub.mollie_subscription_id:
        settings = get_settings()
        plan_template = sub.plan_template
        interval_str = BILLING_INTERVAL_TO_MOLLIE[plan_template.billing_interval]
        months = BILLING_INTERVAL_MONTHS[plan_template.billing_interval]
        start = (date.today() + relativedelta(months=months)).isoformat()
        logger.info(f"Creating Mollie subscription for ongoing recurring payments of "
                    f"€{plan_template.price_cents/100}/{plan_template.billing_interval} according to plan "
                    f"{sub.plan_template.plan.name} starting at {start}...")

        mollie_sub_id = payment_provider.create_subscription(
            customer_id=sub.user.mollie_customer_id,
            mandate_id=payment_info.mandate_id,
            amount_cents=plan_template.price_cents,
            interval=interval_str,
            start_date=start,
            description=sub.deployments[0].payment_description(),
            webhook_url=amend_url(settings.mollie_webhook_base_url, "webhooks/mollie"),
            idempotency_key=f"subscription_{sub.id}",
        )
        sub.mollie_subscription_id = mollie_sub_id
        logger.info(f"Created Mollie recurring payment subscription id={mollie_sub_id} for subscription id={sub.id}")

    logger.info(
        "First payment paid: subscription_id=%s payment_status=current",
        sub.id,
    )


def _handle_first_payment_failed(sub: SubscriptionORM) -> None:
    """First payment failed/expired/canceled: mark subscription as arrears."""
    sub.payment_status = PaymentStatus.ARREARS
    logger.info("First payment failed: subscription_id=%s payment_status=arrears", sub.id)


def _handle_recurring_payment_paid(sub: SubscriptionORM) -> None:
    """Recurring payment succeeded: ensure subscription stays/returns to current."""
    if sub.payment_status != PaymentStatus.CURRENT:
        logger.info("Recurring payment recovered from arrears: subscription_id=%s", sub.id)
        sub.payment_status = PaymentStatus.CURRENT


def _handle_recurring_payment_failed(sub: SubscriptionORM) -> None:
    """Recurring payment failed: mark subscription as arrears."""
    sub.payment_status = PaymentStatus.ARREARS
    logger.info("Recurring payment failed: subscription_id=%s payment_status=arrears", sub.id)
