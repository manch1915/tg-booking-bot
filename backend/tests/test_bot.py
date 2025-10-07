import pytest
from aiogram import Bot, Dispatcher
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from booking.bot.app import build_dispatcher
from booking.bot.context import BotDeps
from booking.config import Settings
from booking.domain.enums import BookingSource, BookingStatus, PaymentStatus
from booking.infra.db.models import Booking, Client, Master
from booking.infra.db.session import make_sessionmaker
from booking.services.clock import FixedClock
from booking.services.payments import Invoice

from .bot_harness import RecordingSession, TelegramUser
from .conftest import NOW

MARK = "Mark Avetisyan"


class FakeGateway:
    def __init__(self) -> None:
        self.refunds: list[str] = []

    async def create_invoice_link(self, invoice: Invoice) -> str:
        return f"https://t.me/$invoice_{invoice.payload}"

    async def refund_stars(self, *, user_id: int, telegram_charge_id: str) -> None:
        self.refunds.append(telegram_charge_id)


@pytest.fixture(scope="module")
def gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture(scope="module")
def dispatcher(engine: AsyncEngine, settings: Settings, gateway: FakeGateway) -> Dispatcher:
    deps = BotDeps(settings=settings, clock=FixedClock(NOW), gateway=gateway)
    return build_dispatcher(make_sessionmaker(engine), deps)


@pytest.fixture
def telegram() -> tuple[Bot, RecordingSession]:
    session = RecordingSession()
    return Bot("42:TEST", session=session), session


def user(dispatcher: Dispatcher, telegram: tuple[Bot, RecordingSession], uid: int) -> TelegramUser:
    bot, session = telegram
    return TelegramUser(dispatcher, bot, session, uid)


async def test_start_registers_client_with_welcome_bonus(
    dispatcher: Dispatcher, telegram: tuple[Bot, RecordingSession], engine: AsyncEngine
) -> None:
    ruben = user(dispatcher, telegram, 9100001)
    await ruben.send("/start")
    assert "Brass &amp; Blade" in ruben.last_text() or "Brass & Blade" in ruben.last_text()
    assert "Book a visit" in ruben.buttons()

    async with make_sessionmaker(engine)() as session:
        client = await session.scalar(select(Client).where(Client.telegram_id == 9100001))
        assert client is not None
        assert client.bonus_balance == 300
        assert client.language.value == "en"


async def test_booking_paid_with_stars_end_to_end(
    dispatcher: Dispatcher,
    telegram: tuple[Bot, RecordingSession],
    engine: AsyncEngine,
    gateway: FakeGateway,
) -> None:
    ruben = user(dispatcher, telegram, 9100002)
    await ruben.send("/start")
    await ruben.click("Book a visit")
    await ruben.click("Beard")
    await ruben.click("Beard trim")
    assert any("Any barber" in b for b in ruben.buttons())
    await ruben.click("Davit")
    await ruben.click(index=2)  # third day with free time
    await ruben.click(index=0)  # first free slot
    assert "Check your booking" in ruben.last_text()
    await ruben.click("Use bonuses")
    assert any(b.startswith("✓") for b in ruben.buttons())
    await ruben.click("Stars")

    invoice = ruben.invoices()[-1]
    assert invoice.currency == "XTR"
    assert invoice.provider_token is None
    assert await ruben.pay(invoice)
    assert "You're booked" in ruben.last_text()

    async with make_sessionmaker(engine)() as session:
        client = await session.scalar(select(Client).where(Client.telegram_id == 9100002))
        assert client is not None
        booking = (
            await session.scalars(select(Booking).where(Booking.client_id == client.id))
        ).one()
        await session.refresh(booking, ["payments", "master"])
        assert booking.status is BookingStatus.CONFIRMED
        assert booking.source is BookingSource.BOT
        assert booking.master.name_en == "Davit Melkonyan"
        assert booking.bonus_spent > 0
        assert booking.payments[0].status is PaymentStatus.PAID
        booking_id = booking.id

    # The client changes their mind in time: Stars go back through refundStarPayment.
    await ruben.click("My bookings")
    await ruben.click("·")
    await ruben.click("Cancel")
    await ruben.click("Yes, cancel")
    assert "deposit is on its way back" in ruben.last_text()
    assert gateway.refunds

    async with make_sessionmaker(engine)() as session:
        cancelled = await session.get(Booking, booking_id)
        assert cancelled is not None
        assert cancelled.status is BookingStatus.CANCELLED


async def test_master_links_telegram_with_deep_link(
    dispatcher: Dispatcher, telegram: tuple[Bot, RecordingSession], engine: AsyncEngine
) -> None:
    async with make_sessionmaker(engine)() as session:
        master = (
            await session.scalars(select(Master).where(Master.name_en == "Mark Avetisyan"))
        ).one()
        token = master.link_token
    mark = user(dispatcher, telegram, 9100003)
    await mark.send(f"/start master_{token}")
    assert "Марк" in mark.last_text()
    async with make_sessionmaker(engine)() as session:
        master = (
            await session.scalars(select(Master).where(Master.name_en == "Mark Avetisyan"))
        ).one()
        assert master.telegram_id == 9100003
        assert master.link_token is None
        master.telegram_id = None
        master.link_token = token
        await session.commit()

    # The same link does not work twice.
    intruder = user(dispatcher, telegram, 9100099)
    await intruder.send("/start master_")
    assert "not valid" in intruder.last_text()


async def test_expired_hold_rejects_checkout(
    dispatcher: Dispatcher, telegram: tuple[Bot, RecordingSession], engine: AsyncEngine
) -> None:
    ruben = user(dispatcher, telegram, 9100004)
    await ruben.send("/start")
    await ruben.click("Book a visit")
    await ruben.click("Haircuts")
    await ruben.click("Buzz cut")
    await ruben.click("Any barber")
    await ruben.click(index=4)
    await ruben.click(index=1)
    await ruben.click("Stars")
    invoice = ruben.invoices()[-1]

    async with make_sessionmaker(engine)() as session, session.begin():
        client = await session.scalar(select(Client).where(Client.telegram_id == 9100004))
        assert client is not None
        booking = (
            await session.scalars(select(Booking).where(Booking.client_id == client.id))
        ).one()
        booking.hold_expires_at = NOW.replace(year=2020)

    assert not await ruben.pay(invoice)
