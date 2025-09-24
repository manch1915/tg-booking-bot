from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.availability import DaySchedule, Interval, free_slots
from booking.domain.enums import ACTIVE_STATUSES
from booking.infra.db.models import Booking, BreakRule, Business, TimeOff, WorkingHours
from booking.services.business import business_tz, load_business
from booking.services.catalog import CatalogService, MasterOffer
from booking.services.clock import Clock


@dataclass(frozen=True, slots=True)
class SlotOption:
    starts_at: datetime
    master_ids: list[int]


@dataclass(frozen=True, slots=True)
class DayInfo:
    day: date
    slots: int


@dataclass(slots=True)
class _MasterCalendar:
    hours: dict[int, tuple[time, time]] = field(default_factory=dict)
    breaks: dict[int, list[tuple[time, time]]] = field(default_factory=lambda: defaultdict(list))
    busy: list[Interval] = field(default_factory=list)

    def schedule(self, day: date) -> DaySchedule:
        weekday = day.weekday()
        return DaySchedule(work=self.hours.get(weekday), breaks=self.breaks.get(weekday, []))


class AvailabilityService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.catalog = CatalogService(session)

    async def day_slots(
        self,
        service_id: int,
        day: date,
        *,
        master_id: int | None = None,
        exclude_booking_id: int | None = None,
    ) -> list[SlotOption]:
        business = await load_business(self.session)
        if not self._in_horizon(business, day):
            return []
        offers = await self._offers(service_id, master_id)
        tz = business_tz(business)
        calendars = await self._load(offers, tz, day, day, exclude_booking_id)

        by_start: dict[datetime, list[int]] = defaultdict(list)
        for offer in offers:
            for start in self._slots_for(business, tz, calendars[offer.master.id], offer, day):
                by_start[start].append(offer.master.id)
        return [SlotOption(start, ids) for start, ids in sorted(by_start.items())]

    async def calendar(
        self, service_id: int, *, master_id: int | None = None, days: int | None = None
    ) -> list[DayInfo]:
        business = await load_business(self.session)
        tz = business_tz(business)
        today = self.clock.now().astimezone(tz).date()
        span = days or business.booking_horizon_days
        last = today + timedelta(days=span - 1)
        offers = await self._offers(service_id, master_id)
        calendars = await self._load(offers, tz, today, last, None)

        result = []
        for offset in range(span):
            day = today + timedelta(days=offset)
            starts: set[datetime] = set()
            for offer in offers:
                starts.update(self._slots_for(business, tz, calendars[offer.master.id], offer, day))
            result.append(DayInfo(day=day, slots=len(starts)))
        return result

    async def is_free(
        self,
        offer: MasterOffer,
        starts_at: datetime,
        *,
        exclude_booking_id: int | None = None,
        strict_grid: bool = True,
    ) -> bool:
        business = await load_business(self.session)
        tz = business_tz(business)
        day = starts_at.astimezone(tz).date()
        calendars = await self._load([offer], tz, day, day, exclude_booking_id)
        calendar = calendars[offer.master.id]
        if strict_grid:
            if not self._in_horizon(business, day):
                return False
            return starts_at in self._slots_for(business, tz, calendar, offer, day)

        # Staff may book off-grid (a walk-in at 13:05) but still not over another booking.
        wanted = Interval(starts_at, starts_at + timedelta(minutes=offer.duration_minutes))
        return not any(wanted.overlaps(b) for b in calendar.busy)

    def _in_horizon(self, business: Business, day: date) -> bool:
        today = self.clock.now().astimezone(business_tz(business)).date()
        return today <= day < today + timedelta(days=business.booking_horizon_days)

    async def _offers(self, service_id: int, master_id: int | None) -> list[MasterOffer]:
        offers = await self.catalog.offers(service_id)
        if master_id is not None:
            offers = [o for o in offers if o.master.id == master_id]
        return offers

    def _slots_for(
        self,
        business: Business,
        tz: ZoneInfo,
        calendar: _MasterCalendar,
        offer: MasterOffer,
        day: date,
    ) -> list[datetime]:
        return free_slots(
            day=day,
            tz=tz,
            schedule=calendar.schedule(day),
            busy=calendar.busy,
            duration=timedelta(minutes=offer.duration_minutes),
            step=timedelta(minutes=business.slot_step_minutes),
            not_before=self.clock.now() + timedelta(minutes=business.min_lead_minutes),
        )

    async def _load(
        self,
        offers: list[MasterOffer],
        tz: ZoneInfo,
        first: date,
        last: date,
        exclude_booking_id: int | None,
    ) -> dict[int, _MasterCalendar]:
        master_ids = [o.master.id for o in offers]
        calendars = {mid: _MasterCalendar() for mid in master_ids}
        if not master_ids:
            return calendars

        range_start = datetime.combine(first, time(0), tzinfo=tz)
        range_end = datetime.combine(last + timedelta(days=1), time(0), tzinfo=tz)

        for hours in await self.session.scalars(
            select(WorkingHours).where(WorkingHours.master_id.in_(master_ids))
        ):
            calendars[hours.master_id].hours[hours.weekday] = (hours.start_time, hours.end_time)

        for rule in await self.session.scalars(
            select(BreakRule).where(BreakRule.master_id.in_(master_ids))
        ):
            calendars[rule.master_id].breaks[rule.weekday].append((rule.start_time, rule.end_time))

        for off in await self.session.scalars(
            select(TimeOff).where(
                TimeOff.master_id.in_(master_ids),
                TimeOff.starts_at < range_end,
                TimeOff.ends_at > range_start,
            )
        ):
            calendars[off.master_id].busy.append(Interval(off.starts_at, off.ends_at))

        bookings = select(Booking).where(
            Booking.master_id.in_(master_ids),
            Booking.status.in_(ACTIVE_STATUSES),
            Booking.starts_at < range_end,
            Booking.ends_at > range_start,
        )
        if exclude_booking_id is not None:
            bookings = bookings.where(Booking.id != exclude_booking_id)
        for booking in await self.session.scalars(bookings):
            calendars[booking.master_id].busy.append(Interval(booking.starts_at, booking.ends_at))

        return calendars
