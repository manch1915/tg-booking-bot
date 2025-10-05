from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import Date, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.availability import Interval, local_interval, subtract
from booking.domain.enums import BookingStatus, PaymentPurpose, PaymentStatus
from booking.infra.db.models import (
    Booking,
    BreakRule,
    Client,
    Master,
    Payment,
    Review,
    Service,
    TimeOff,
    WorkingHours,
)
from booking.services.business import business_tz, load_business

BUSY = (BookingStatus.CONFIRMED, BookingStatus.COMPLETED, BookingStatus.NO_SHOW)


@dataclass
class MasterStats:
    master_id: int
    revenue: int = 0
    visits: int = 0
    booked_minutes: int = 0
    working_minutes: int = 0
    rating: float | None = None
    reviews: int = 0

    @property
    def load(self) -> float:
        return round(self.booked_minutes / self.working_minutes, 3) if self.working_minutes else 0.0


@dataclass
class Report:
    start: date
    end: date
    revenue: int = 0
    visits: int = 0
    no_shows: int = 0
    cancellations: int = 0
    new_clients: int = 0
    deposits: int = 0
    tips_stars: int = 0
    load: float = 0.0
    by_day: list[tuple[date, int, int]] = field(default_factory=list)
    by_master: list[MasterStats] = field(default_factory=list)
    by_service: list[tuple[int, int, int]] = field(default_factory=list)
    by_source: dict[str, int] = field(default_factory=dict)
    by_method: dict[str, int] = field(default_factory=dict)

    @property
    def average_check(self) -> int:
        return self.revenue // self.visits if self.visits else 0

    @property
    def no_show_rate(self) -> float:
        total = self.visits + self.no_shows
        return round(self.no_shows / total, 3) if total else 0.0


class ReportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def build(self, start: date, end: date) -> Report:
        """Figures for local days start..end inclusive."""
        business = await load_business(self.session)
        tz = business_tz(business)
        lo = datetime.combine(start, time(0), tzinfo=tz)
        hi = datetime.combine(end + timedelta(days=1), time(0), tzinfo=tz)
        local_day = cast(func.timezone(business.timezone, Booking.starts_at), Date)
        in_range = (Booking.starts_at >= lo, Booking.starts_at < hi)
        completed = Booking.status == BookingStatus.COMPLETED
        paid = Booking.price - Booking.bonus_spent

        report = Report(start=start, end=end)
        totals = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(case((completed, paid), else_=0)), 0),
                    func.count().filter(completed),
                    func.count().filter(Booking.status == BookingStatus.NO_SHOW),
                    func.count().filter(Booking.status == BookingStatus.CANCELLED),
                ).where(*in_range)
            )
        ).one()
        report.revenue, report.visits, report.no_shows, report.cancellations = map(int, totals)

        days = await self.session.execute(
            select(local_day, func.sum(paid), func.count())
            .where(*in_range, completed)
            .group_by(local_day)
            .order_by(local_day)
        )
        revenue_by_day = {d: (int(r), int(c)) for d, r, c in days.all()}
        report.by_day = [(day, *revenue_by_day.get(day, (0, 0))) for day in _days(start, end)]

        services = await self.session.execute(
            select(Booking.service_id, func.count(), func.sum(paid))
            .where(*in_range, completed)
            .group_by(Booking.service_id)
            .order_by(func.sum(paid).desc())
        )
        report.by_service = [(sid, int(c), int(r)) for sid, c, r in services.all()]

        sources = await self.session.execute(
            select(Booking.source, func.count())
            .where(*in_range, Booking.status != BookingStatus.CANCELLED)
            .group_by(Booking.source)
        )
        report.by_source = {s.value: int(c) for s, c in sources.all()}

        methods = await self.session.execute(
            select(Booking.payment_method, func.count())
            .where(*in_range, Booking.status != BookingStatus.CANCELLED)
            .group_by(Booking.payment_method)
        )
        report.by_method = {m.value: int(c) for m, c in methods.all()}

        payments = await self.session.execute(
            select(Payment.purpose, func.sum(Payment.amount_base), func.sum(Payment.amount))
            .join(Booking, Booking.id == Payment.booking_id)
            .where(*in_range, Payment.status == PaymentStatus.PAID)
            .group_by(Payment.purpose)
        )
        for purpose, base, raw in payments.all():
            if purpose is PaymentPurpose.DEPOSIT:
                report.deposits = int(base)
            else:
                report.tips_stars = int(raw)

        report.new_clients = int(
            await self.session.scalar(
                select(func.count(Client.id)).where(
                    Client.created_at >= lo, Client.created_at < hi, Client.is_demo_guest.is_(False)
                )
            )
            or 0
        )
        report.by_master = await self._masters(start, end, lo, hi)
        working = sum(m.working_minutes for m in report.by_master)
        booked = sum(m.booked_minutes for m in report.by_master)
        report.load = round(booked / working, 3) if working else 0.0
        return report

    async def _masters(
        self, start: date, end: date, lo: datetime, hi: datetime
    ) -> list[MasterStats]:
        business = await load_business(self.session)
        tz = business_tz(business)
        masters = list(await self.session.scalars(select(Master).order_by(Master.sort)))
        stats = {m.id: MasterStats(master_id=m.id) for m in masters}

        rows = await self.session.execute(
            select(
                Booking.master_id,
                func.coalesce(
                    func.sum(
                        case(
                            (
                                Booking.status == BookingStatus.COMPLETED,
                                Booking.price - Booking.bonus_spent,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.count().filter(Booking.status == BookingStatus.COMPLETED),
                func.coalesce(
                    func.sum(func.extract("epoch", Booking.ends_at - Booking.starts_at) / 60), 0
                ),
            )
            .where(Booking.starts_at >= lo, Booking.starts_at < hi, Booking.status.in_(BUSY))
            .group_by(Booking.master_id)
        )
        for master_id, revenue, visits, minutes in rows.all():
            stats[master_id].revenue = int(revenue)
            stats[master_id].visits = int(visits)
            stats[master_id].booked_minutes = int(minutes)

        hours: dict[int, dict[int, tuple[time, time]]] = defaultdict(dict)
        for h in await self.session.scalars(select(WorkingHours)):
            hours[h.master_id][h.weekday] = (h.start_time, h.end_time)
        breaks: dict[int, dict[int, list[tuple[time, time]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for b in await self.session.scalars(select(BreakRule)):
            breaks[b.master_id][b.weekday].append((b.start_time, b.end_time))
        offs: dict[int, list[Interval]] = defaultdict(list)
        for off in await self.session.scalars(
            select(TimeOff).where(TimeOff.starts_at < hi, TimeOff.ends_at > lo)
        ):
            offs[off.master_id].append(Interval(off.starts_at, off.ends_at))

        for master in masters:
            total = 0
            for day in _days(start, end):
                span = hours[master.id].get(day.weekday())
                if span is None:
                    continue
                cuts = [local_interval(day, b, tz) for b in breaks[master.id][day.weekday()]]
                free = subtract(local_interval(day, span, tz), cuts + offs[master.id])
                total += sum(int((p.end - p.start).total_seconds() // 60) for p in free)
            stats[master.id].working_minutes = total

        ratings = await self.session.execute(
            select(Review.master_id, func.avg(Review.rating), func.count()).group_by(
                Review.master_id
            )
        )
        for master_id, avg, count in ratings.all():
            stats[master_id].rating = round(float(avg), 2)
            stats[master_id].reviews = int(count)
        return [stats[m.id] for m in masters]

    async def service_names(self) -> dict[int, tuple[str, str]]:
        rows = await self.session.execute(select(Service.id, Service.name_ru, Service.name_en))
        return {sid: (ru, en) for sid, ru, en in rows.all()}


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
