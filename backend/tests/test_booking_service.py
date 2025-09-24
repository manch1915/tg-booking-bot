import asyncio
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from booking.config import Settings
from booking.domain.enums import (
    BonusKind,
    BookingSource,
    BookingStatus,
    NotificationKind,
    PaymentMethod,
    PaymentStatus,
    WaitlistStatus,
)
from booking.infra.db.models import (
    BonusTransaction,
    Booking,
    Client,
    Master,
    Notification,
    Service,
    WaitlistEntry,
)
from booking.services.availability import AvailabilityService, SlotOption
from booking.services.booking import BookingRequest, BookingService
from booking.services.clock import FixedClock
from booking.services.errors import PolicyError, SlotUnavailableError
from booking.services.payments import PaymentService
from booking.services.waitlist import WaitlistService

from .conftest import NOW


async def service_by_name(session: AsyncSession, name_en: str) -> Service:
    return (await session.scalars(select(Service).where(Service.name_en == name_en))).one()


async def master_by_name(session: AsyncSession, name_en: str) -> Master:
    return (await session.scalars(select(Master).where(Master.name_en == name_en))).one()


async def some_client(session: AsyncSession, offset: int = 0) -> Client:
    query = select(Client).order_by(Client.id).offset(offset).limit(1)
    return (await session.scalars(query)).one()


async def first_free_slot(
    session: AsyncSession, clock: FixedClock, service: Service, master: Master, after_days: int = 3
) -> SlotOption:
    availability = AvailabilityService(session, clock)
    for offset in range(after_days, 14):
        day = (NOW + timedelta(days=offset)).date()
        slots = await availability.day_slots(service.id, day, master_id=master.id)
        if slots:
            return slots[0]
    raise AssertionError("No free slot in the demo data")


async def test_slots_never_overlap_active_bookings(
    session: AsyncSession, clock: FixedClock
) -> None:
    service = await service_by_name(session, "Skin fade")
    availability = AvailabilityService(session, clock)
    day = NOW.date()
    for offset in range(3):
        slots = await availability.day_slots(service.id, day + timedelta(days=offset))
        for slot in slots:
            assert slot.starts_at >= NOW + timedelta(minutes=60)
            for master_id in slot.master_ids:
                end = slot.starts_at + timedelta(minutes=60)
                clash = await session.scalar(
                    select(func.count(Booking.id)).where(
                        Booking.master_id == master_id,
                        Booking.status.in_(["pending_payment", "confirmed"]),
                        Booking.starts_at < end,
                        Booking.ends_at > slot.starts_at,
                    )
                )
                assert clash == 0


async def test_calendar_covers_horizon(session: AsyncSession, clock: FixedClock) -> None:
    service = await service_by_name(session, "Classic haircut")
    days = await AvailabilityService(session, clock).calendar(service.id)
    assert len(days) == 14
    assert days[0].day == date(2026, 10, 19)
    assert any(d.slots > 0 for d in days)


async def test_book_on_site_confirms_and_schedules_reminders(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Classic haircut")
    master = await master_by_name(session, "Ani Grigoryan")
    slot = await first_free_slot(session, clock, service, master)
    client = await some_client(session)

    booking = await bookings.create(
        client,
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            source=BookingSource.ADMIN,
        ),
    )
    assert booking.status is BookingStatus.CONFIRMED
    assert booking.ends_at - booking.starts_at == timedelta(minutes=45)
    kinds = set(
        await session.scalars(
            select(Notification.kind).where(Notification.booking_id == booking.id)
        )
    )
    assert {
        NotificationKind.BOOKING_CONFIRMED,
        NotificationKind.REMINDER_DAY,
        NotificationKind.REMINDER_SOON,
        NotificationKind.REVIEW_REQUEST,
        NotificationKind.MASTER_NEW_BOOKING,
    } <= kinds


async def test_online_booking_requires_deposit(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Beard trim")
    master = await master_by_name(session, "Mark Avetisyan")
    slot = await first_free_slot(session, clock, service, master)
    with pytest.raises(PolicyError):
        await bookings.create(
            await some_client(session),
            BookingRequest(service_id=service.id, master_id=master.id, starts_at=slot.starts_at),
        )


async def test_deposit_flow_with_demo_payment(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Skin fade")
    master = await master_by_name(session, "Artur Sargsyan")
    slot = await first_free_slot(session, clock, service, master)
    client = await some_client(session, 3)

    booking = await bookings.create(
        client,
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            payment_method=PaymentMethod.CARD,
        ),
    )
    assert booking.status is BookingStatus.PENDING_PAYMENT
    assert booking.price == 3800  # senior barber charges more than the base price
    assert booking.deposit == 1200
    assert booking.hold_expires_at == NOW + timedelta(minutes=10)
    payment = booking.payments[0]
    assert payment.status is PaymentStatus.PENDING

    outcome = await bookings.complete_demo_payment(payment.id, client)
    assert outcome.confirmed
    assert outcome.booking.status is BookingStatus.CONFIRMED
    assert outcome.booking.payments[0].status is PaymentStatus.PAID


async def test_bonus_spend_is_capped_and_returned_on_expiry(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Classic haircut")
    master = await master_by_name(session, "Davit Melkonyan")
    slot = await first_free_slot(session, clock, service, master)
    client = (
        await session.scalars(select(Client).order_by(Client.bonus_balance.desc()).limit(1))
    ).one()
    balance = client.bonus_balance

    booking = await bookings.create(
        client,
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            payment_method=PaymentMethod.STARS,
            use_bonus=True,
        ),
    )
    assert booking.bonus_spent == min(balance, booking.price * 30 // 100)
    assert client.bonus_balance == balance - booking.bonus_spent

    clock.moment = NOW + timedelta(minutes=11)
    assert await bookings.expire_holds() >= 1
    await session.refresh(booking)
    await session.refresh(client)
    assert booking.status is BookingStatus.CANCELLED
    assert client.bonus_balance == balance


async def test_same_slot_twice_is_rejected(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Buzz cut")
    master = await master_by_name(session, "Mark Avetisyan")
    slot = await first_free_slot(session, clock, service, master)
    request = BookingRequest(
        service_id=service.id,
        master_id=master.id,
        starts_at=slot.starts_at,
        source=BookingSource.ADMIN,
    )
    await bookings.create(await some_client(session, 1), request)
    with pytest.raises(SlotUnavailableError):
        await bookings.create(await some_client(session, 2), request)


async def test_exclusion_constraint_blocks_overlap_written_directly(session: AsyncSession) -> None:
    existing = (
        await session.scalars(
            select(Booking).where(Booking.status == BookingStatus.CONFIRMED).limit(1)
        )
    ).one()
    clash = Booking(
        client_id=existing.client_id,
        master_id=existing.master_id,
        service_id=existing.service_id,
        starts_at=existing.starts_at + timedelta(minutes=10),
        ends_at=existing.ends_at + timedelta(minutes=10),
        status=BookingStatus.CONFIRMED,
        source=BookingSource.ADMIN,
        payment_method=PaymentMethod.ON_SITE,
        price=1000,
    )
    session.add(clash)
    with pytest.raises(IntegrityError, match="booking_no_overlap"):
        await session.flush()


async def test_cancel_in_time_refunds_late_cancel_keeps_deposit(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Beard trim")
    master = await master_by_name(session, "Davit Melkonyan")
    client = await some_client(session, 5)
    created = []
    for _ in range(2):
        slot = await first_free_slot(session, clock, service, master)
        booking = await bookings.create(
            client,
            BookingRequest(
                service_id=service.id,
                master_id=master.id,
                starts_at=slot.starts_at,
                payment_method=PaymentMethod.CARD,
            ),
        )
        await bookings.complete_demo_payment(booking.payments[0].id, client)
        created.append(await bookings.get(booking.id))

    early, late = created
    result = await bookings.cancel(early, by_client=True)
    assert result.refund is PaymentStatus.REFUNDED
    assert not result.late

    clock.moment = late.starts_at - timedelta(hours=1)
    result = await bookings.cancel(late, by_client=True)
    assert result.late
    assert result.refund is None
    assert late.payments[0].status is PaymentStatus.PAID


async def test_client_cannot_move_visit_after_deadline(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Classic haircut")
    master = await master_by_name(session, "Ani Grigoryan")
    slot = await first_free_slot(session, clock, service, master)
    booking = await bookings.create(
        await some_client(session, 7),
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            source=BookingSource.ADMIN,
        ),
    )
    clock.moment = booking.starts_at - timedelta(hours=2)
    with pytest.raises(PolicyError):
        await bookings.reschedule(booking, booking.starts_at + timedelta(hours=1), by_client=True)


async def test_reschedule_moves_reminders(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Classic haircut")
    master = await master_by_name(session, "Artur Sargsyan")
    slot = await first_free_slot(session, clock, service, master)
    booking = await bookings.create(
        await some_client(session, 8),
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            source=BookingSource.ADMIN,
        ),
    )
    later = await first_free_slot(session, clock, service, master, after_days=6)
    moved = await bookings.reschedule(booking, later.starts_at, by_client=True)
    assert moved.starts_at == later.starts_at

    reminders = list(
        await session.scalars(
            select(Notification).where(
                Notification.booking_id == booking.id,
                Notification.kind == NotificationKind.REMINDER_SOON,
                Notification.cancelled_at.is_(None),
            )
        )
    )
    assert [r.send_at for r in reminders] == [later.starts_at - timedelta(hours=2)]


async def test_cancel_notifies_waitlist(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    service = await service_by_name(session, "Skin fade")
    master = await master_by_name(session, "Artur Sargsyan")
    slot = await first_free_slot(session, clock, service, master)
    booking = await bookings.create(
        await some_client(session, 9),
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            source=BookingSource.ADMIN,
        ),
    )
    waiting = await some_client(session, 10)
    entry = await WaitlistService(session, clock).join(
        waiting.id, service.id, slot.starts_at.date(), master.id
    )

    await bookings.cancel(booking, by_client=False)
    assert entry.status is WaitlistStatus.NOTIFIED
    sent = await session.scalar(
        select(func.count(Notification.id)).where(
            Notification.kind == NotificationKind.WAITLIST_SLOT,
            Notification.client_id == waiting.id,
        )
    )
    assert sent == 1
    assert (await session.get(WaitlistEntry, entry.id)) is entry


async def test_completed_visit_pays_cashback_and_referral(
    session: AsyncSession, clock: FixedClock, bookings: BookingService
) -> None:
    referrer = await some_client(session, 11)
    friend = Client(name="Новый друг", referral_code="testfrnd", referred_by_id=referrer.id)
    session.add(friend)
    await session.flush()
    service = await service_by_name(session, "Classic haircut")
    master = await master_by_name(session, "Ani Grigoryan")
    slot = await first_free_slot(session, clock, service, master)
    booking = await bookings.create(
        friend,
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            source=BookingSource.ADMIN,
        ),
    )
    referrer_before = referrer.bonus_balance
    clock.moment = booking.ends_at + timedelta(hours=1)

    assert await bookings.complete_finished() >= 1
    await session.refresh(friend)
    await session.refresh(referrer)
    assert friend.bonus_balance == 2800 * 5 // 100
    assert referrer.bonus_balance == referrer_before + 500
    kinds = set(
        await session.scalars(
            select(BonusTransaction.kind).where(BonusTransaction.booking_id == booking.id)
        )
    )
    assert kinds == {BonusKind.CASHBACK, BonusKind.REFERRAL}


async def test_concurrent_bookings_of_one_slot(
    engine: AsyncEngine, settings: Settings, clock: FixedClock
) -> None:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        service = await service_by_name(session, "Kids haircut")
        master = await master_by_name(session, "Ani Grigoryan")
        slot = await first_free_slot(session, clock, service, master, after_days=8)
        client_ids = [c.id for c in (await session.scalars(select(Client).limit(12))).all()]

    async def attempt(client_id: int) -> int | None:
        async with factory() as session, session.begin():
            service_layer = BookingService(session, clock, PaymentService(session, clock, settings))
            client = await session.get(Client, client_id)
            assert client is not None
            try:
                booking = await service_layer.create(
                    client,
                    BookingRequest(
                        service_id=service.id,
                        master_id=master.id,
                        starts_at=slot.starts_at,
                        source=BookingSource.ADMIN,
                    ),
                )
            except SlotUnavailableError:
                return None
            return booking.id

    results = await asyncio.gather(*(attempt(cid) for cid in client_ids))
    winners = [r for r in results if r is not None]
    try:
        assert len(winners) == 1
    finally:
        async with factory() as session, session.begin():
            for booking_id in winners:
                booking = await session.get(Booking, booking_id)
                if booking is not None:
                    await session.delete(booking)
