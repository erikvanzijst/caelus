import json
import logging
from dataclasses import dataclass
from typing import Any, Protocol

from mollie import (
    Amount,
    EntityCustomer,
    PaymentRequest,
    Security,
    SequenceType,
    SubscriptionRequest,
)
from mollie import ClientSDK
from mollie.types.basemodel import Unset

logger = logging.getLogger(__name__)


def _nullable(value: Any) -> Any:
    """Convert Mollie SDK's OptionalNullable sentinel to plain None."""
    return None if isinstance(value, Unset) else value


def cents_to_amount(cents: int) -> Amount:
    """Convert euro cents to Mollie Amount.

    >>> cents_to_amount(1000)
    Amount(currency='EUR', value='10.00')
    >>> cents_to_amount(999)
    Amount(currency='EUR', value='9.99')
    """
    return Amount(currency="EUR", value=f"{cents / 100:.2f}")


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------


@dataclass
class FirstPaymentResult:
    payment_id: str
    checkout_url: str
    payload: dict[str, Any] | None = None


@dataclass
class PaymentInfo:
    status: str
    metadata: dict[str, Any] | None
    mandate_id: str | None
    subscription_id: str | None
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


class PaymentProvider(Protocol):
    def ensure_customer(
        self, email: str, name: str | None = None, *, idempotency_key: str | None = None,
    ) -> str: ...

    def create_first_payment(
        self,
        customer_id: str,
        amount_cents: int,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> FirstPaymentResult: ...

    def get_payment(self, payment_id: str) -> PaymentInfo: ...

    def create_subscription(
        self,
        customer_id: str,
        mandate_id: str,
        amount_cents: int,
        interval: str,
        start_date: str,
        description: str,
        webhook_url: str,
        metadata: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> str: ...

    def cancel_subscription(self, customer_id: str, subscription_id: str) -> None: ...


# ---------------------------------------------------------------------------
# Real implementation
# ---------------------------------------------------------------------------


class MolliePaymentProvider(PaymentProvider):
    """Payment provider backed by the Mollie API via mollie-api-py SDK."""

    def __init__(self, api_key: str) -> None:
        self._client = ClientSDK(security=Security(api_key=api_key), debug_logger=logging.getLogger("mollie"))

    def ensure_customer(
        self, email: str, name: str | None = None, *, idempotency_key: str | None = None,
    ) -> str:
        response = self._client.customers.create(
            entity_customer=EntityCustomer(email=email, name=name),
            idempotency_key=idempotency_key,
        )
        return response.id

    def create_first_payment(
        self,
        customer_id: str,
        amount_cents: int,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> FirstPaymentResult:
        response = self._client.payments.create(
            idempotency_key=idempotency_key,
            payment_request=PaymentRequest(
                amount=cents_to_amount(amount_cents),
                description=description,
                redirect_url=redirect_url,
                webhook_url=webhook_url,
                customer_id=customer_id,
                sequence_type=SequenceType.FIRST,
                metadata=metadata,
            )
        )
        checkout_url = response.links.checkout.href if response.links.checkout else ""
        return FirstPaymentResult(
            payment_id=response.id,
            checkout_url=checkout_url,
            payload=response.model_dump(mode="json", by_alias=True),
        )

    def get_payment(self, payment_id: str) -> PaymentInfo:
        response = self._client.payments.get(payment_id=payment_id)
        payload = response.model_dump(mode="json", by_alias=True)
        logger.info(f"Pulled payment info from Mollie for id={payment_id}:\n{json.dumps(payload, indent=2)}")

        return PaymentInfo(
            status=response.status.value,
            metadata=payload.get("metadata"),
            mandate_id=_nullable(response.mandate_id),
            subscription_id=_nullable(response.subscription_id),
            payload=payload,
        )

    def create_subscription(
        self,
        customer_id: str,
        mandate_id: str,
        amount_cents: int,
        interval: str,
        start_date: str,
        description: str,
        webhook_url: str,
        metadata: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> str:
        response = self._client.subscriptions.create(
            customer_id=customer_id,
            idempotency_key=idempotency_key,
            subscription_request=SubscriptionRequest(
                amount=cents_to_amount(amount_cents),
                interval=interval,
                start_date=start_date,
                description=description,
                mandate_id=mandate_id,
                webhook_url=webhook_url,
                metadata=metadata,
            ),
        )
        return response.id

    def cancel_subscription(self, customer_id: str, subscription_id: str) -> None:
        self._client.subscriptions.cancel(
            customer_id=customer_id,
            subscription_id=subscription_id,
        )


# ---------------------------------------------------------------------------
# Fake implementation (for tests)
# ---------------------------------------------------------------------------


class FakePaymentProvider(PaymentProvider):
    """In-memory fake for testing. State controllable from test code."""

    def __init__(self) -> None:
        self.customers: dict[str, str] = {}  # email -> customer_id
        self.payments: dict[str, dict[str, Any]] = {}  # payment_id -> data
        self.subscriptions: dict[str, dict[str, Any]] = {}  # sub_id -> data
        self._customer_counter = 0
        self._payment_counter = 0
        self._subscription_counter = 0
        self._next_payment_status = "paid"

    def ensure_customer(
        self, email: str, name: str | None = None, *, idempotency_key: str | None = None,
    ) -> str:
        if email in self.customers:
            return self.customers[email]
        self._customer_counter += 1
        customer_id = f"cst_fake_{self._customer_counter}"
        self.customers[email] = customer_id
        return customer_id

    def create_first_payment(
        self,
        customer_id: str,
        amount_cents: int,
        description: str,
        redirect_url: str,
        webhook_url: str,
        metadata: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> FirstPaymentResult:
        self._payment_counter += 1
        payment_id = f"tr_fake_{self._payment_counter}"
        self.payments[payment_id] = {
            "status": "open",
            "customer_id": customer_id,
            "amount_cents": amount_cents,
            "metadata": metadata,
            "mandate_id": None,
            "subscription_id": None,
            "sequence_type": "first",
        }
        return FirstPaymentResult(
            payment_id=payment_id,
            checkout_url=f"https://fake.mollie.com/checkout/{payment_id}",
            payload=self.payments[payment_id],
        )

    def get_payment(self, payment_id: str) -> PaymentInfo:
        payment = self.payments[payment_id]
        return PaymentInfo(
            status=self._next_payment_status,
            metadata=payment["metadata"],
            mandate_id=payment.get("mandate_id"),
            subscription_id=payment.get("subscription_id"),
            payload={"id": payment_id, **payment, "status": self._next_payment_status},
        )

    def create_subscription(
        self,
        customer_id: str,
        mandate_id: str,
        amount_cents: int,
        interval: str,
        start_date: str,
        description: str,
        webhook_url: str,
        metadata: dict[str, Any] | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> str:
        self._subscription_counter += 1
        sub_id = f"sub_fake_{self._subscription_counter}"
        self.subscriptions[sub_id] = {
            "customer_id": customer_id,
            "mandate_id": mandate_id,
            "amount_cents": amount_cents,
            "interval": interval,
            "start_date": start_date,
            "description": description,
            "metadata": metadata,
        }
        return sub_id

    def cancel_subscription(self, customer_id: str, subscription_id: str) -> None:
        if subscription_id in self.subscriptions:
            self.subscriptions[subscription_id]["status"] = "canceled"

    def simulate_paid(self, payment_id: str) -> None:
        """Helper: simulate a successful payment for webhook tests."""
        if payment_id in self.payments:
            self.payments[payment_id]["status"] = "paid"
            self.payments[payment_id]["mandate_id"] = f"mdt_fake_{self._payment_counter}"
        self._next_payment_status = "paid"
