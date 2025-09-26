import logging
import secrets
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from booking.config import Settings
from booking.domain.enums import (
    BookingStatus,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
)
from booking.domain.policies import stars_for
from booking.infra.db.models import Booking, Business, Client, Payment
from booking.services.clock import Clock
from booking.services.errors import NotFoundError, PaymentError

log = logging.getLogger(__name__)

STARS = "XTR"


class InvoiceGateway(Protocol):
    async def create_invoice_link(self, invoice: "Invoice") -> str: ...

    async def refund_stars(self, *, user_id: int, telegram_charge_id: str) -> None: ...


class CardRefunder(Protocol):
    async def refund(
        self, *, provider_charge_id: str, amount: int, idempotency_key: str
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class Invoice:
    title: str
    description: str
    payload: str
    currency: str
    amount: int
    provider_token: str | None
    photo_url: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentIntent:
    payment_id: int
    provider: PaymentProvider
    amount: int
    currency: str
    invoice_url: str | None


class PaymentService:
    def __init__(
        self,
        session: AsyncSession,
        clock: Clock,
        settings: Settings,
        gateway: InvoiceGateway | None = None,
        card_refunder: CardRefunder | None = None,
    ) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.gateway = gateway
        self.card_refunder = card_refunder

    def provider_for(self, method: PaymentMethod, client: Client) -> PaymentProvider:
        in_telegram = client.telegram_id is not None and self.gateway is not None
        if method is PaymentMethod.STARS and in_telegram:
            return PaymentProvider.STARS
        if method is PaymentMethod.CARD and in_telegram and self.settings.payment_provider_token:
            return PaymentProvider.TELEGRAM_CARD
        # Browser demo or no BotFather payment token: simulated checkout, nothing is charged.
        # Never outside demo mode, otherwise a booking could be confirmed without real money.
        if not self.settings.demo_mode:
            raise PaymentError("This payment method is not available")
        return PaymentProvider.DEMO

    def create_deposit(
        self, booking: Booking, client: Client, business: Business, method: PaymentMethod
    ) -> Payment:
        provider = self.provider_for(method, client)
        if method is PaymentMethod.STARS:
            amount = stars_for(
                booking.deposit, self.settings.stars_per_usd, self.settings.stars_fixed_price
            )
            currency = STARS
        else:
            amount, currency = booking.deposit, business.currency
        payment = Payment(
            booking=booking,
            provider=provider,
            purpose=PaymentPurpose.DEPOSIT,
            status=PaymentStatus.PENDING,
            amount=amount,
            currency=currency,
            amount_base=booking.deposit,
            payload=f"dep_{secrets.token_hex(12)}",
        )
        self.session.add(payment)
        return payment

    def invoice_for(self, payment: Payment, *, title: str, description: str) -> Invoice:
        token = None
        if payment.provider is PaymentProvider.TELEGRAM_CARD:
            token = self.settings.payment_provider_token
            assert token is not None
        return Invoice(
            title=title,
            description=description,
            payload=payment.payload,
            currency=payment.currency,
            amount=payment.amount,
            provider_token=token.get_secret_value() if token else None,
        )

    async def intent(self, payment: Payment, *, title: str, description: str) -> PaymentIntent:
        url = None
        if payment.provider is not PaymentProvider.DEMO:
            if self.gateway is None:
                raise PaymentError("Telegram payments are not configured")
            url = await self.gateway.create_invoice_link(
                self.invoice_for(payment, title=title, description=description)
            )
        return PaymentIntent(
            payment_id=payment.id,
            provider=payment.provider,
            amount=payment.amount,
            currency=payment.currency,
            invoice_url=url,
        )

    async def by_payload(self, payload: str) -> Payment:
        payment = await self.session.scalar(
            select(Payment)
            .where(Payment.payload == payload)
            .options(selectinload(Payment.booking))
            .with_for_update()
        )
        if payment is None:
            raise NotFoundError("Payment not found")
        return payment

    async def checkout_error(self, payload: str, currency: str, total: int) -> str | None:
        """Pre-checkout validation. Returns a reason to reject, or None if the payment may go."""
        try:
            payment = await self.by_payload(payload)
        except NotFoundError:
            return "unknown_payment"
        if payment.status is not PaymentStatus.PENDING:
            return "already_processed"
        if payment.currency != currency or payment.amount != total:
            return "amount_mismatch"
        booking = payment.booking
        expired = booking.hold_expires_at is not None and booking.hold_expires_at < self.clock.now()
        if booking.status is not BookingStatus.PENDING_PAYMENT or expired:
            return "hold_expired"
        return None

    def mark_paid(
        self, payment: Payment, *, telegram_charge_id: str | None, provider_charge_id: str | None
    ) -> None:
        payment.status = PaymentStatus.PAID
        payment.paid_at = self.clock.now()
        payment.telegram_charge_id = telegram_charge_id
        payment.provider_charge_id = provider_charge_id

    async def refund(self, payment: Payment, client: Client) -> PaymentStatus:
        if payment.status is not PaymentStatus.PAID:
            return payment.status
        match payment.provider:
            case PaymentProvider.DEMO:
                payment.status = PaymentStatus.REFUNDED
            case PaymentProvider.STARS:
                if self.gateway is None or client.telegram_id is None:
                    raise PaymentError("Cannot refund Stars without Telegram")
                assert payment.telegram_charge_id is not None
                await self.gateway.refund_stars(
                    user_id=client.telegram_id, telegram_charge_id=payment.telegram_charge_id
                )
                payment.status = PaymentStatus.REFUNDED
            case PaymentProvider.TELEGRAM_CARD:
                payment.status = await self._refund_card(payment)
        if payment.status is PaymentStatus.REFUNDED:
            payment.refunded_at = self.clock.now()
        return payment.status

    async def _refund_card(self, payment: Payment) -> PaymentStatus:
        # Bot API cannot refund provider payments; it goes through the provider's own API.
        if self.card_refunder is None or not payment.provider_charge_id:
            return PaymentStatus.REFUND_PENDING
        try:
            await self.card_refunder.refund(
                provider_charge_id=payment.provider_charge_id,
                amount=payment.amount,
                idempotency_key=f"refund-{payment.payload}",
            )
        except Exception:
            log.exception("Card refund failed for payment %s", payment.id)
            return PaymentStatus.REFUND_PENDING
        return PaymentStatus.REFUNDED
