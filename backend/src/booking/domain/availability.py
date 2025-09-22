"""Free slot calculation. Pure functions over aware datetimes, no I/O."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class Interval:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Interval bounds must be timezone-aware")

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True, slots=True)
class DaySchedule:
    """A master's working pattern for one local calendar day."""

    work: tuple[time, time] | None
    breaks: Sequence[tuple[time, time]] = ()


def local_interval(day: date, span: tuple[time, time], tz: ZoneInfo) -> Interval:
    start = datetime.combine(day, span[0], tzinfo=tz)
    end_day = day if span[1] > span[0] else day + timedelta(days=1)
    end = datetime.combine(end_day, span[1], tzinfo=tz)
    return Interval(start, end)


def subtract(base: Interval, cuts: Iterable[Interval]) -> list[Interval]:
    free = [base]
    for cut in sorted(cuts, key=lambda c: c.start):
        next_free: list[Interval] = []
        for piece in free:
            if not piece.overlaps(cut):
                next_free.append(piece)
                continue
            if piece.start < cut.start:
                next_free.append(Interval(piece.start, cut.start))
            if cut.end < piece.end:
                next_free.append(Interval(cut.end, piece.end))
        free = next_free
    return free


def _first_aligned(moment: datetime, anchor: datetime, step: timedelta) -> datetime:
    offset = moment - anchor
    steps = -(-offset // step)  # ceil division for timedelta
    return anchor + steps * step


def free_slots(
    *,
    day: date,
    tz: ZoneInfo,
    schedule: DaySchedule,
    busy: Iterable[Interval],
    duration: timedelta,
    step: timedelta,
    not_before: datetime,
) -> list[datetime]:
    """Start times (aware, in `tz`) where a service of `duration` fits.

    `busy` holds bookings and time off. Slots are aligned to `step` from local midnight,
    so the grid stays the same when a booking ends at an odd minute.
    """
    if schedule.work is None or duration <= timedelta(0):
        return []

    workday = local_interval(day, schedule.work, tz)
    cuts = [local_interval(day, b, tz) for b in schedule.breaks]
    cuts.extend(b for b in busy if b.overlaps(workday))

    anchor = datetime.combine(day, time(0), tzinfo=tz)
    slots: list[datetime] = []
    for window in subtract(workday, cuts):
        start = _first_aligned(max(window.start, not_before), anchor, step)
        while start + duration <= window.end:
            slots.append(start.astimezone(tz))
            start += step
    return slots
