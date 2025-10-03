from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from booking.domain.enums import (
    ACTIVE_STATUSES,
    BonusKind,
    BookingSource,
    BookingStatus,
    NotificationKind,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)
from booking.domain.policies import cashback_for, change_policy, deposit_for, max_bonus_spend
from booking.infra.db.models import Booking, Business, Client, Payment
from booking.services.availability import AvailabilityService
from booking.services.bonuses import BonusService
from booking.services.business import business_tz, load_business
from booking.services.catalog import CatalogService, MasterOffer
from booking.services.clock import Clock
from booking.services.errors import (
    InvalidStateError,
    NotFoundError,
    PolicyError,
    SlotUnavailableError,
)
from booking.services.notifications import NotificationScheduler
from booking.services.payments import PaymentService
from booking.services.waitlist import WaitlistService

LOCK_NAMESPACE = 7_340_000


@dataclass(frozen=True, slots=True)
class BookingRequest:
    service_id: int
    starts_at: datetime
    master_id: int | None = None
    payment_method: PaymentMethod = PaymentMethod.ON_SITE
    use_bonus: bool = False
    source: BookingSource = BookingSource.MINIAPP
    comment: str = ""


@dataclass(frozen=True, slots=True)
class CancelResult:
    booking: Booking
    refund: PaymentStatus | None
    late: bool


@dataclass(frozen=True, slots=True)
class PaymentOutcome:
    booking: Booking
    confirmed: bool


def booking_options() -> tuple[ExecutableOption, ...]:
    return (
        selectinload(Booking.client),
        selectinload(Booking.master),
        selectinload(Booking.service),
        selectinload(Booking.payments),
        selectinload(Booking.review),
    )


class BookingService:
    def __init__(self, session: AsyncSession, clock: Clock, payments: PaymentService) -> None:
        self.session = session
        self.clock = clock
        self.payments = payments
        self.catalog = CatalogService(session)
        self.availability = AvailabilityService(session, clock)
        self.notifications = NotificationScheduler(session, clock)
        self.bonuses = BonusService(session)
        self.waitlist = WaitlistService(session, clock)

    async def get(self, booking_id: int) -> Booking:
        booking = await self.session.scalar(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(*booking_options())
            .execution_options(populate_existing=True)
        )
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    async def get_for_client(self, booking_id: int, client_id: int) -> Booking:
        booking = await self.get(booking_id)
        if booking.client_id != client_id:
            raise NotFoundError("Booking not found")
        return booking

    async def client_bookings(self, client_id: int) -> list[Booking]:
        rows = await self.session.scalars(
            select(Booking)
            .where(Booking.client_id == client_id, Booking.status != BookingStatus.CANCELLED)
            .options(*booking_options())
            .order_by(Booking.starts_at.desc())
        )
        return list(rows)

    async def create(
        self,
        client: Client,
        request: BookingRequest,
        *,
        strict: bool = True,
    ) -> Booking:
        business = await load_business(self.session)
        await self._check_method(business, request)
        if request.payment_method is not PaymentMethod.ON_SITE:
            self.payments.provider_for(request.payment_method, client)
        offer = await self._pick_offer(request, strict=strict)
        await self._lock_master(offer.master.id)
        await self._release_stale_holds(offer.master.id)
        if not await self.availability.is_free(offer, request.starts_at, strict_grid=strict):
            raise SlotUnavailableError("This time is no longer available")

        price = offer.price
        bonus = 0
        if request.use_bonus:
            bonus = max_bonus_spend(price, client.bonus_balance, business.max_bonus_share_percent)
        prepaid = request.payment_method is not PaymentMethod.ON_SITE
        deposit = min(deposit_for(price, business.deposit_percent), price - bonus) if prepaid else 0

        now = self.clock.now()
        booking = Booking(
            client_id=client.id,
            master_id=offer.master.id,
            service_id=request.service_id,
            starts_at=request.starts_at,
            ends_at=request.starts_at + timedelta(minutes=offer.duration_minutes),
            status=BookingStatus.PENDING_PAYMENT if deposit else BookingStatus.CONFIRMED,
            source=request.source,
            payment_method=request.payment_method if deposit else PaymentMethod.ON_SITE,
            price=price,
            deposit=deposit,
            bonus_spent=bonus,
            hold_expires_at=now + timedelta(minutes=business.hold_minutes) if deposit else None,
            comment=request.comment.strip()[:500],
        )
        await self._insert(booking)
        if bonus:
            await self.bonuses.change(client, -bonus, BonusKind.SPEND, booking_id=booking.id)
        if deposit:
            self.payments.create_deposit(booking, client, business, request.payment_method)
        else:
            self.notifications.booking_confirmed(
                booking, notify_client=request.source is not BookingSource.BOT
            )
        await self.session.flush()
        return await self.get(booking.id)

    async def confirm_payment(
        self,
        payload: str,
        *,
        telegram_charge_id: str | None = None,
        provider_charge_id: str | None = None,
        notify_client: bool = True,
    ) -> PaymentOutcome:
        payment = await self.payments.by_payload(payload)
        booking = await self.get(payment.booking_id)
        if payment.status is PaymentStatus.PAID:
            return PaymentOutcome(booking, booking.status is BookingStatus.CONFIRMED)

        self.payments.mark_paid(
            payment, telegram_charge_id=telegram_charge_id, provider_charge_id=provider_charge_id
        )
        # Money may arrive after the hold expired. Take the slot back if it is still free,
        # otherwise give the money back right away.
        lost_slot = booking.status is BookingStatus.CANCELLED and not await self._reactivate(
            booking
        )
        if lost_slot:
            await self.payments.refund(payment, booking.client)
            await self.session.flush()
            return PaymentOutcome(booking, confirmed=False)
        booking.status = BookingStatus.CONFIRMED
        booking.hold_expires_at = None
        self.notifications.booking_confirmed(booking, notify_client=notify_client)
        await self.session.flush()
        return PaymentOutcome(await self.get(booking.id), confirmed=True)

    async def complete_demo_payment(self, payment_id: int, client: Client) -> PaymentOutcome:
        if not self.payments.settings.demo_mode:
            raise NotFoundError("Payment not found")
        payment = await self.session.get(Payment, payment_id)
        if payment is None:
            raise NotFoundError("Payment not found")
        booking = await self.get_for_client(payment.booking_id, client.id)
        if payment.provider is not PaymentProvider.DEMO:
            raise InvalidStateError("This payment is processed by Telegram")
        return await self.confirm_payment(
            payment.payload, provider_charge_id=f"demo_{booking.id}", notify_client=False
        )

    async def cancel(self, booking: Booking, *, by_client: bool, reason: str = "") -> CancelResult:
        if booking.status not in ACTIVE_STATUSES:
            raise InvalidStateError("Booking is not active")
        business = await load_business(self.session)
        now = self.clock.now()
        decision = change_policy(
            starts_at=booking.starts_at, now=now, window_hours=business.cancel_window_hours
        )
        if by_client and not decision.can_cancel:
            raise PolicyError("The visit has already started")

        was_confirmed = booking.status is BookingStatus.CONFIRMED
        booking.status = BookingStatus.CANCELLED
        booking.cancelled_at = now
        booking.cancel_reason = reason[:200]
        booking.hold_expires_at = None

        refund = await self._settle_deposit(
            booking, refund=not by_client or decision.refund_deposit
        )
        await self._return_bonus(booking)
        if was_confirmed:
            await self.notifications.booking_cancelled(booking, notify_client=not by_client)
            if booking.starts_at > now:
                await self.waitlist.slot_freed(
                    booking.service_id, booking.master_id, booking.starts_at
                )
        await self.session.flush()
        return CancelResult(booking, refund, late=by_client and not decision.refund_deposit)

    async def reschedule(
        self,
        booking: Booking,
        starts_at: datetime,
        *,
        master_id: int | None = None,
        by_client: bool,
    ) -> Booking:
        if booking.status is not BookingStatus.CONFIRMED:
            raise InvalidStateError("Only confirmed bookings can be moved")
        business = await load_business(self.session)
        decision = change_policy(
            starts_at=booking.starts_at,
            now=self.clock.now(),
            window_hours=business.cancel_window_hours,
        )
        if by_client and not decision.can_reschedule:
            raise PolicyError("Too late to move the visit", hours=business.cancel_window_hours)

        target_master = master_id or booking.master_id
        offer = await self.catalog.offer(booking.service_id, target_master)
        for mid in sorted({booking.master_id, target_master}):
            await self._lock_master(mid)
        if not await self.availability.is_free(
            offer, starts_at, exclude_booking_id=booking.id, strict_grid=by_client
        ):
            raise SlotUnavailableError("This time is no longer available")

        previous_master, previous_start = booking.master_id, booking.starts_at
        booking.master_id = offer.master.id
        booking.starts_at = starts_at
        booking.ends_at = starts_at + timedelta(minutes=offer.duration_minutes)
        try:
            async with self.session.begin_nested():
                await self.session.flush()
        except IntegrityError as exc:
            raise SlotUnavailableError("This time is no longer available") from exc

        await self.notifications.booking_rescheduled(booking, previous_start)
        await self.waitlist.slot_freed(booking.service_id, previous_master, previous_start)
        await self.session.flush()
        return await self.get(booking.id)

    async def complete(self, booking: Booking) -> Booking:
        if booking.status is not BookingStatus.CONFIRMED:
            raise InvalidStateError("Only confirmed bookings can be completed")
        business = await load_business(self.session)
        booking.status = BookingStatus.COMPLETED
        booking.completed_at = self.clock.now()

        client = booking.client
        cashback = cashback_for(booking.price - booking.bonus_spent, business.cashback_percent)
        await self.bonuses.change(client, cashback, BonusKind.CASHBACK, booking_id=booking.id)
        await self._reward_referrer(client, business, booking)
        await self.session.flush()
        return booking

    async def mark_no_show(self, booking: Booking) -> Booking:
        if booking.status is not BookingStatus.CONFIRMED:
            raise InvalidStateError("Only confirmed bookings can be marked as no-show")
        booking.status = BookingStatus.NO_SHOW
        await self.notifications.cancel_pending(booking.id, [NotificationKind.REVIEW_REQUEST])
        await self.session.flush()
        return booking

    async def expire_holds(self) -> int:
        rows = await self.session.scalars(
            select(Booking)
            .where(
                Booking.status == BookingStatus.PENDING_PAYMENT,
                Booking.hold_expires_at < self.clock.now(),
            )
            .options(selectinload(Booking.payments), selectinload(Booking.client))
            .with_for_update(skip_locked=True, of=Booking)
        )
        expired = list(rows)
        for booking in expired:
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = self.clock.now()
            booking.cancel_reason = "hold_expired"
            await self._settle_deposit(booking, refund=True)
            await self._return_bonus(booking)
        await self.session.flush()
        return len(expired)

    async def complete_finished(self, grace: timedelta = timedelta(minutes=30)) -> int:
        """Visits that ended a while ago count as done unless staff marked a no-show."""
        rows = await self.session.scalars(
            select(Booking)
            .where(
                Booking.status == BookingStatus.CONFIRMED,
                Booking.ends_at < self.clock.now() - grace,
            )
            .options(selectinload(Booking.client))
            .with_for_update(skip_locked=True, of=Booking)
            .limit(200)
        )
        done = list(rows)
        for booking in done:
            await self.complete(booking)
        return len(done)

    async def suggest_master(self, service_id: int, starts_at: datetime) -> MasterOffer:
        """The barber that "any free barber" would get at this time."""
        return await self._pick_offer(
            BookingRequest(service_id=service_id, starts_at=starts_at), strict=True
        )

    async def _check_method(self, business: Business, request: BookingRequest) -> None:
        if request.payment_method is PaymentMethod.STARS and not business.stars_enabled:
            raise PolicyError("Stars payments are turned off")
        prepay_required = business.deposit_percent > 0 and request.source is not BookingSource.ADMIN
        if prepay_required and request.payment_method is PaymentMethod.ON_SITE:
            raise PolicyError("A deposit is required to book online")

    async def _pick_offer(self, request: BookingRequest, *, strict: bool) -> MasterOffer:
        if request.master_id is not None:
            return await self.catalog.offer(request.service_id, request.master_id)

        business = await load_business(self.session)
        local_day = request.starts_at.astimezone(business_tz(business)).date()
        slots = await self.availability.day_slots(request.service_id, local_day)
        candidates = next((s.master_ids for s in slots if s.starts_at == request.starts_at), [])
        if not candidates:
            raise SlotUnavailableError("Nobody is free at this time")
        master_id = await self._least_busy(candidates, local_day, business)
        return await self.catalog.offer(request.service_id, master_id)

    async def _least_busy(self, master_ids: list[int], day: date, business: Business) -> int:
        start = datetime.combine(day, time(0), tzinfo=business_tz(business))
        rows = await self.session.execute(
            select(Booking.master_id, func.count(Booking.id))
            .where(
                Booking.master_id.in_(master_ids),
                Booking.status.in_(ACTIVE_STATUSES),
                Booking.starts_at >= start,
                Booking.starts_at < start + timedelta(days=1),
            )
            .group_by(Booking.master_id)
        )
        load: dict[int, int] = dict(rows.all())
        return min(master_ids, key=lambda mid: (load.get(mid, 0), mid))

    async def _lock_master(self, master_id: int) -> None:
        # Serialises bookings per master inside the transaction. The exclusion constraint
        # still guards the data if someone writes around this service.
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_NAMESPACE + master_id}
        )

    async def _release_stale_holds(self, master_id: int) -> None:
        rows = await self.session.scalars(
            select(Booking)
            .where(
                Booking.master_id == master_id,
                Booking.status == BookingStatus.PENDING_PAYMENT,
                Booking.hold_expires_at < self.clock.now(),
            )
            .options(selectinload(Booking.payments), selectinload(Booking.client))
        )
        for booking in rows:
            booking.status = BookingStatus.CANCELLED
            booking.cancelled_at = self.clock.now()
            booking.cancel_reason = "hold_expired"
            await self._settle_deposit(booking, refund=True)
            await self._return_bonus(booking)
        await self.session.flush()

    async def _insert(self, booking: Booking) -> None:
        try:
            async with self.session.begin_nested():
                self.session.add(booking)
                await self.session.flush()
        except IntegrityError as exc:
            raise SlotUnavailableError("This time is no longer available") from exc

    async def _reactivate(self, booking: Booking) -> bool:
        try:
            async with self.session.begin_nested():
                booking.status = BookingStatus.CONFIRMED
                booking.cancelled_at = None
                booking.cancel_reason = ""
                await self.session.flush()
        except IntegrityError:
            booking.status = BookingStatus.CANCELLED
            return False
        if booking.bonus_spent:
            # Bonuses were returned when the hold expired; take them again.
            try:
                await self.bonuses.change(
                    booking.client, -booking.bonus_spent, BonusKind.SPEND, booking_id=booking.id
                )
            except PolicyError:
                booking.bonus_spent = 0
        return True

    async def _settle_deposit(self, booking: Booking, *, refund: bool) -> PaymentStatus | None:
        result = None
        for payment in booking.payments:
            if payment.status is PaymentStatus.PENDING:
                payment.status = PaymentStatus.CANCELLED
            elif payment.status is PaymentStatus.PAID and refund:
                result = await self.payments.refund(payment, booking.client)
        return result

    async def _return_bonus(self, booking: Booking) -> None:
        if booking.bonus_spent:
            await self.bonuses.change(
                booking.client, booking.bonus_spent, BonusKind.RETURN, booking_id=booking.id
            )

    async def _reward_referrer(self, client: Client, business: Business, booking: Booking) -> None:
        if client.referred_by_id is None or not business.referral_bonus:
            return
        completed = await self.session.scalar(
            select(func.count(Booking.id)).where(
                Booking.client_id == client.id, Booking.status == BookingStatus.COMPLETED
            )
        )
        if completed != 1:
            return
        referrer = await self.session.get(Client, client.referred_by_id)
        if referrer is None:
            return
        await self.bonuses.change(
            referrer,
            business.referral_bonus,
            BonusKind.REFERRAL,
            booking_id=booking.id,
            comment=client.name,
        )
        self.notifications.enqueue(
            NotificationKind.BONUS_ACCRUED,
            client_id=referrer.id,
            payload={"amount": business.referral_bonus, "friend": client.name},
        )
