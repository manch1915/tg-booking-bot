from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from booking.config import Settings
from booking.domain.enums import BookingSource, Language, NotificationKind
from booking.infra.db.models import Booking, Client, Master, Notification
from booking.services.booking import BookingRequest, BookingService
from booking.services.clock import FixedClock
from booking.services.messaging import DeliveryError, OutgoingMessage
from booking.worker.dispatcher import NotificationDispatcher

from .test_booking_service import first_free_slot, master_by_name, service_by_name


class FakeMessenger:
    def __init__(self, fail: DeliveryError | None = None) -> None:
        self.sent: list[OutgoingMessage] = []
        self.fail = fail

    async def send(self, message: OutgoingMessage) -> None:
        if self.fail is not None:
            raise self.fail
        self.sent.append(message)


async def telegram_client(session: AsyncSession, tg_id: int, lang: Language) -> Client:
    client = Client(
        name="Арсен Тест", telegram_id=tg_id, referral_code=f"t{tg_id}"[-8:], language=lang
    )
    session.add(client)
    await session.flush()
    return client


async def book(
    session: AsyncSession, clock: FixedClock, bookings: BookingService, client: Client
) -> Booking:
    service = await service_by_name(session, "Classic haircut")
    master = await master_by_name(session, "Artur Sargsyan")
    slot = await first_free_slot(session, clock, service, master)
    return await bookings.create(
        client,
        BookingRequest(
            service_id=service.id,
            master_id=master.id,
            starts_at=slot.starts_at,
            source=BookingSource.ADMIN,
        ),
    )


async def silence_backlog(session: AsyncSession, clock: FixedClock) -> None:
    await session.execute(
        update(Notification).where(Notification.sent_at.is_(None)).values(sent_at=clock.now())
    )


async def test_client_and_master_get_messages(
    session: AsyncSession, clock: FixedClock, settings: Settings, bookings: BookingService
) -> None:
    await silence_backlog(session, clock)
    client = await telegram_client(session, 5550001, Language.EN)
    master = await master_by_name(session, "Artur Sargsyan")
    master.telegram_id = 7770001
    booking = await book(session, clock, bookings, client)

    messenger = FakeMessenger()
    dispatcher = NotificationDispatcher(session, clock, settings, messenger)
    assert await dispatcher.dispatch_due() == 2
    to_client, to_master = sorted(messenger.sent, key=lambda m: m.chat_id)
    assert "Booking confirmed" in to_client.text
    assert "Classic haircut" in to_client.text
    assert "Новая запись" in to_master.text
    assert client.name in to_master.text

    clock.moment = booking.starts_at - timedelta(hours=2)
    messenger.sent.clear()
    assert await dispatcher.dispatch_due() == 2  # day-before and two-hours reminders
    texts = " ".join(m.text for m in messenger.sent)
    assert "See you tomorrow" in texts
    assert "in 2 hours" in texts


async def test_reminders_of_cancelled_booking_are_dropped(
    session: AsyncSession, clock: FixedClock, settings: Settings, bookings: BookingService
) -> None:
    await silence_backlog(session, clock)
    client = await telegram_client(session, 5550002, Language.RU)
    booking = await book(session, clock, bookings, client)
    await bookings.cancel(booking, by_client=True)

    clock.moment = booking.starts_at + timedelta(hours=3)
    messenger = FakeMessenger()
    await NotificationDispatcher(session, clock, settings, messenger).dispatch_due()
    kinds_sent = {m.text.splitlines()[0] for m in messenger.sent}
    assert not any("Завтра" in k or "Через 2 часа" in k for k in kinds_sent)


async def test_review_request_waits_until_visit_is_closed(
    session: AsyncSession, clock: FixedClock, settings: Settings, bookings: BookingService
) -> None:
    await silence_backlog(session, clock)
    client = await telegram_client(session, 5550003, Language.RU)
    booking = await book(session, clock, bookings, client)

    clock.moment = booking.ends_at + timedelta(hours=1, minutes=1)
    messenger = FakeMessenger()
    dispatcher = NotificationDispatcher(session, clock, settings, messenger)
    await dispatcher.dispatch_due()
    request = (
        await session.scalars(
            select(Notification).where(
                Notification.booking_id == booking.id,
                Notification.kind == NotificationKind.REVIEW_REQUEST,
            )
        )
    ).one()
    assert request.sent_at is None  # still confirmed, so it is postponed

    await bookings.complete(booking)
    clock.moment += timedelta(minutes=11)
    await dispatcher.dispatch_due()
    assert any("Оцените" in m.text for m in messenger.sent)
    assert len(messenger.sent[-1].buttons[0]) == 3


async def test_temporary_failure_is_retried_and_blocked_bot_is_not(
    session: AsyncSession, clock: FixedClock, settings: Settings, bookings: BookingService
) -> None:
    await silence_backlog(session, clock)
    client = await telegram_client(session, 5550004, Language.RU)
    await book(session, clock, bookings, client)
    for master in await session.scalars(select(Master)):
        master.telegram_id = None

    flaky = FakeMessenger(DeliveryError("timeout", permanent=False))
    await NotificationDispatcher(session, clock, settings, flaky).dispatch_due()
    pending = (
        await session.scalars(
            select(Notification).where(
                Notification.client_id == client.id,
                Notification.kind == NotificationKind.BOOKING_CONFIRMED,
            )
        )
    ).one()
    assert pending.sent_at is None
    assert pending.attempts == 1
    assert pending.send_at > clock.now()

    clock.moment = pending.send_at
    blocked = FakeMessenger(DeliveryError("bot was blocked by the user", permanent=True))
    await NotificationDispatcher(session, clock, settings, blocked).dispatch_due()
    assert pending.sent_at is not None
    assert pending.error == "bot was blocked by the user"
