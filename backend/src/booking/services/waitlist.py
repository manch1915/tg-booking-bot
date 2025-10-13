from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.enums import NotificationKind, WaitlistStatus
from booking.infra.db.models import WaitlistEntry
from booking.services.business import business_tz, load_business
from booking.services.clock import Clock
from booking.services.notifications import NotificationScheduler


class WaitlistService:
    def __init__(self, session: AsyncSession, clock: Clock, *, notify_clients: bool = True) -> None:
        self.session = session
        self.clock = clock
        self.notifications = NotificationScheduler(session, clock, notify_clients=notify_clients)

    async def join(
        self, client_id: int, service_id: int, day: date, master_id: int | None = None
    ) -> WaitlistEntry:
        existing = await self.session.scalar(
            select(WaitlistEntry).where(
                WaitlistEntry.client_id == client_id,
                WaitlistEntry.service_id == service_id,
                WaitlistEntry.day == day,
                WaitlistEntry.status == WaitlistStatus.WAITING,
            )
        )
        if existing is not None:
            existing.master_id = master_id
            return existing
        entry = WaitlistEntry(
            client_id=client_id,
            service_id=service_id,
            master_id=master_id,
            day=day,
            status=WaitlistStatus.WAITING,
        )
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def slot_freed(self, service_id: int, master_id: int, starts_at: datetime) -> int:
        """Tell everyone waiting for that day at once; whoever books first gets the slot."""
        business = await load_business(self.session)
        day = starts_at.astimezone(business_tz(business)).date()
        rows = await self.session.scalars(
            select(WaitlistEntry)
            .where(
                WaitlistEntry.day == day,
                WaitlistEntry.status == WaitlistStatus.WAITING,
                or_(WaitlistEntry.master_id.is_(None), WaitlistEntry.master_id == master_id),
            )
            .with_for_update(skip_locked=True)
        )
        entries = list(rows)
        for entry in entries:
            entry.status = WaitlistStatus.NOTIFIED
            entry.notified_at = self.clock.now()
            self.notifications.enqueue(
                NotificationKind.WAITLIST_SLOT,
                client_id=entry.client_id,
                payload={
                    "service_id": entry.service_id,
                    "master_id": master_id,
                    "starts_at": starts_at.isoformat(),
                    "day": day.isoformat(),
                },
            )
        return len(entries)

    async def expire_past(self) -> None:
        business = await load_business(self.session)
        today = self.clock.now().astimezone(business_tz(business)).date()
        for entry in await self.session.scalars(
            select(WaitlistEntry).where(
                WaitlistEntry.day < today, WaitlistEntry.status == WaitlistStatus.WAITING
            )
        ):
            entry.status = WaitlistStatus.EXPIRED
