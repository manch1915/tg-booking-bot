import logging
from datetime import date, timedelta

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from booking.config import Settings
from booking.infra.db.models import Client
from booking.infra.db.session import transaction
from booking.seed import seed
from booking.services.booking import BookingService
from booking.services.business import business_tz, load_business
from booking.services.clock import Clock
from booking.services.messaging import Messenger
from booking.services.payments import CardRefunder, InvoiceGateway, PaymentService
from booking.services.waitlist import WaitlistService
from booking.worker.dispatcher import NotificationDispatcher

log = logging.getLogger(__name__)

DEMO_GUEST_TTL = timedelta(hours=24)
DEMO_RESET_HOUR = 4


class Jobs:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        settings: Settings,
        clock: Clock,
        messenger: Messenger,
        gateway: InvoiceGateway | None = None,
        card_refunder: CardRefunder | None = None,
    ) -> None:
        self.sessions = sessions
        self.settings = settings
        self.clock = clock
        self.messenger = messenger
        self.gateway = gateway
        self.card_refunder = card_refunder
        self.last_reset: date | None = None

    def _bookings(self, session: AsyncSession) -> BookingService:
        payments = PaymentService(
            session, self.clock, self.settings, self.gateway, self.card_refunder
        )
        return BookingService(session, self.clock, payments)

    async def tick(self) -> None:
        for job in (self.housekeeping, self.notifications, self.demo_maintenance):
            try:
                await job()
            except Exception:
                log.exception("Job %s failed", job.__name__)

    async def housekeeping(self) -> None:
        async with transaction(self.sessions) as session:
            bookings = self._bookings(session)
            expired = await bookings.expire_holds()
            done = await bookings.complete_finished()
            await WaitlistService(session, self.clock).expire_past()
        if expired or done:
            log.info("Released %s holds, closed %s visits", expired, done)

    async def notifications(self) -> None:
        while True:
            async with transaction(self.sessions) as session:
                dispatcher = NotificationDispatcher(
                    session, self.clock, self.settings, self.messenger
                )
                batch = await dispatcher.dispatch_due(limit=50)
            if batch < 50:
                return

    async def demo_maintenance(self) -> None:
        if not self.settings.demo_mode:
            return
        async with transaction(self.sessions) as session:
            await session.execute(
                delete(Client).where(
                    Client.is_demo_guest, Client.created_at < self.clock.now() - DEMO_GUEST_TTL
                )
            )
            local = self.clock.now().astimezone(business_tz(await load_business(session)))
            due = local.hour == DEMO_RESET_HOUR and self.last_reset != local.date()
            if due:
                # Fresh schedule every night so the demo always shows the next two weeks.
                await seed(session, self.settings, now=self.clock.now())
                self.last_reset = local.date()
                log.info("Demo data reset")
