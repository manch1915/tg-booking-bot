"""Back-office use cases: schedules, catalogue, clients and broadcasts."""

import secrets
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from sqlalchemy import Select, delete, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from booking.config import Settings
from booking.domain.enums import (
    BonusKind,
    BookingStatus,
    NotificationKind,
    Segment,
)
from booking.infra.db.models import (
    Booking,
    BreakRule,
    Broadcast,
    Client,
    Master,
    MasterService,
    Notification,
    Service,
    TimeOff,
    WorkingHours,
)
from booking.services.bonuses import BonusService
from booking.services.clients import new_referral_code
from booking.services.clock import Clock
from booking.services.errors import InvalidStateError, NotFoundError, PolicyError
from booking.services.notifications import NotificationScheduler


@dataclass(frozen=True, slots=True)
class DaySpan:
    weekday: int
    start: time
    end: time


@dataclass(frozen=True, slots=True)
class ServiceLink:
    service_id: int
    price: int | None = None
    duration_minutes: int | None = None


class ScheduleAdmin:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def master(self, master_id: int) -> Master:
        master = await self.session.scalar(
            select(Master)
            .where(Master.id == master_id)
            .options(
                selectinload(Master.hours),
                selectinload(Master.breaks),
                selectinload(Master.services),
            )
            .execution_options(populate_existing=True)
        )
        if master is None:
            raise NotFoundError("Master not found")
        return master

    async def masters(self) -> list[Master]:
        rows = await self.session.scalars(
            select(Master)
            .options(
                selectinload(Master.hours),
                selectinload(Master.breaks),
                selectinload(Master.services),
            )
            .order_by(Master.sort, Master.id)
        )
        return list(rows)

    async def set_schedule(
        self, master: Master, hours: list[DaySpan], breaks: list[DaySpan]
    ) -> Master:
        for span in [*hours, *breaks]:
            if not 0 <= span.weekday <= 6 or span.end <= span.start:
                raise PolicyError("Each interval must end after it starts")
        if len({h.weekday for h in hours}) != len(hours):
            raise PolicyError("One working interval per weekday")
        await self.session.execute(delete(WorkingHours).where(WorkingHours.master_id == master.id))
        await self.session.execute(delete(BreakRule).where(BreakRule.master_id == master.id))
        self.session.add_all(
            WorkingHours(master_id=master.id, weekday=h.weekday, start_time=h.start, end_time=h.end)
            for h in hours
        )
        self.session.add_all(
            BreakRule(master_id=master.id, weekday=b.weekday, start_time=b.start, end_time=b.end)
            for b in breaks
        )
        await self.session.flush()
        return await self.master(master.id)

    async def set_services(self, master: Master, links: list[ServiceLink]) -> Master:
        await self.session.execute(
            delete(MasterService).where(MasterService.master_id == master.id)
        )
        self.session.add_all(
            MasterService(
                master_id=master.id,
                service_id=link.service_id,
                price=link.price,
                duration_minutes=link.duration_minutes,
            )
            for link in links
        )
        await self.session.flush()
        return await self.master(master.id)

    async def add_time_off(
        self, master: Master, starts_at: datetime, ends_at: datetime, reason: str
    ) -> TimeOff:
        if ends_at <= starts_at:
            raise PolicyError("Time off must end after it starts")
        clash = await self.session.scalar(
            select(func.count(Booking.id)).where(
                Booking.master_id == master.id,
                Booking.status.in_([BookingStatus.CONFIRMED, BookingStatus.PENDING_PAYMENT]),
                Booking.starts_at < ends_at,
                Booking.ends_at > starts_at,
            )
        )
        if clash:
            raise InvalidStateError(
                "There are bookings in this period, move or cancel them first", bookings=int(clash)
            )
        off = TimeOff(master_id=master.id, starts_at=starts_at, ends_at=ends_at, reason=reason)
        self.session.add(off)
        await self.session.flush()
        return off

    async def time_off(self, start: datetime, end: datetime) -> list[TimeOff]:
        rows = await self.session.scalars(
            select(TimeOff)
            .where(TimeOff.starts_at < end, TimeOff.ends_at > start)
            .order_by(TimeOff.starts_at)
        )
        return list(rows)

    async def remove_time_off(self, time_off_id: int) -> None:
        await self.session.execute(delete(TimeOff).where(TimeOff.id == time_off_id))

    @staticmethod
    def new_link_token(master: Master) -> str:
        """Issues a fresh one-time link and unlinks the current Telegram account."""
        master.link_token = secrets.token_urlsafe(12)
        master.telegram_id = None
        return master.link_token


class ClientAdmin:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock

    def segment_query(self, segment: Segment, master_id: int | None = None) -> Select[Client]:
        now = self.clock.now()
        query = select(Client).where(Client.is_demo_guest.is_(False))
        visits = select(Booking.id).where(
            Booking.client_id == Client.id, Booking.status == BookingStatus.COMPLETED
        )
        match segment:
            case Segment.ALL:
                return query
            case Segment.INACTIVE_30:
                recent = visits.where(Booking.starts_at > now - timedelta(days=30))
                return query.where(exists(visits), ~exists(recent))
            case Segment.NEW_CLIENTS:
                return query.where(Client.created_at > now - timedelta(days=30))
            case Segment.WITH_BONUSES:
                return query.where(Client.bonus_balance >= 500)
            case Segment.MASTER_REGULARS:
                if master_id is None:
                    raise PolicyError("Pick a barber for this segment")
                return query.where(exists(visits.where(Booking.master_id == master_id)))

    async def search(
        self, *, q: str = "", segment: Segment = Segment.ALL, limit: int = 50, offset: int = 0
    ) -> tuple[list[tuple[Client, int, datetime | None, int]], int]:
        base = self.segment_query(segment).subquery()
        stats = (
            select(
                Booking.client_id,
                func.count().filter(Booking.status == BookingStatus.COMPLETED).label("visits"),
                func.max(Booking.starts_at)
                .filter(Booking.status == BookingStatus.COMPLETED)
                .label("last_visit"),
                func.coalesce(
                    func.sum(Booking.price - Booking.bonus_spent).filter(
                        Booking.status == BookingStatus.COMPLETED
                    ),
                    0,
                ).label("spent"),
            )
            .group_by(Booking.client_id)
            .subquery()
        )
        query = (
            select(Client, stats.c.visits, stats.c.last_visit, stats.c.spent)
            .join(base, base.c.id == Client.id)
            .outerjoin(stats, stats.c.client_id == Client.id)
        )
        if q.strip():
            like = f"%{q.strip()}%"
            query = query.where(or_(Client.name.ilike(like), Client.phone.ilike(like)))
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.execute(
            query.order_by(stats.c.last_visit.desc().nulls_last(), Client.id)
            .limit(limit)
            .offset(offset)
        )
        return [(c, int(v or 0), lv, int(s or 0)) for c, v, lv, s in rows.all()], int(total or 0)

    async def find_or_create(self, name: str, phone: str) -> Client:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if digits:
            existing = await self.session.scalar(
                select(Client).where(func.regexp_replace(Client.phone, r"\D", "", "g") == digits)
            )
            if existing is not None:
                return existing
        client = Client(
            name=name.strip() or phone,
            phone=phone.strip() or None,
            referral_code=new_referral_code(),
        )
        self.session.add(client)
        await self.session.flush()
        return client

    async def adjust_bonus(self, client: Client, amount: int, comment: str) -> None:
        await BonusService(self.session).change(client, amount, BonusKind.MANUAL, comment=comment)


class BroadcastService:
    def __init__(self, session: AsyncSession, clock: Clock, settings: Settings) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.clients = ClientAdmin(session, clock)

    def _audience(self, segment: Segment, master_id: int | None) -> Select[Client]:
        return self.clients.segment_query(segment, master_id).where(
            Client.telegram_id.is_not(None), Client.marketing_opt_out.is_(False)
        )

    async def preview(self, segment: Segment, master_id: int | None) -> tuple[int, int]:
        everyone = await self.session.scalar(
            select(func.count()).select_from(
                self.clients.segment_query(segment, master_id).subquery()
            )
        )
        reachable = await self.session.scalar(
            select(func.count()).select_from(self._audience(segment, master_id).subquery())
        )
        return int(everyone or 0), int(reachable or 0)

    async def send(
        self,
        segment: Segment,
        master_id: int | None,
        text_ru: str,
        text_en: str,
        author: str,
    ) -> Broadcast:
        if not text_ru.strip() and not text_en.strip():
            raise PolicyError("The message is empty")
        broadcast = Broadcast(
            segment=segment,
            segment_master_id=master_id,
            text_ru=text_ru.strip() or text_en.strip(),
            text_en=text_en.strip() or text_ru.strip(),
            created_by=author,
        )
        self.session.add(broadcast)
        await self.session.flush()
        scheduler = NotificationScheduler(self.session, self.clock)
        recipients = list(await self.session.scalars(self._audience(segment, master_id)))
        for client in recipients:
            note = scheduler.enqueue(
                NotificationKind.BROADCAST, client_id=client.id, broadcast_id=broadcast.id
            )
            if note is not None and self.settings.demo_mode:
                # Visitors of the public demo must not be able to message real Telegram users.
                note.sent_at = self.clock.now()
                note.error = "demo"
        everyone, reachable = await self.preview(segment, master_id)
        # In the demo the whole segment counts as reached, since nothing is really sent.
        broadcast.recipients = everyone if self.settings.demo_mode else reachable
        await self.session.flush()
        return broadcast

    async def history(self) -> list[tuple[Broadcast, int]]:
        delivered = (
            select(Notification.broadcast_id, func.count().label("sent"))
            .where(Notification.sent_at.is_not(None), Notification.error.is_(None))
            .group_by(Notification.broadcast_id)
            .subquery()
        )
        rows = await self.session.execute(
            select(Broadcast, func.coalesce(delivered.c.sent, 0))
            .outerjoin(delivered, delivered.c.broadcast_id == Broadcast.id)
            .order_by(Broadcast.created_at.desc())
            .limit(50)
        )
        return [(b, int(sent)) for b, sent in rows.all()]


async def services_with_links(session: AsyncSession) -> list[Service]:
    rows = await session.scalars(
        select(Service)
        .options(selectinload(Service.masters), selectinload(Service.category))
        .order_by(Service.sort, Service.id)
    )
    return list(rows)
