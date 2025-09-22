from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from booking.domain.availability import DaySchedule, Interval, free_slots, subtract

TZ = ZoneInfo("Asia/Yerevan")
DAY = date(2026, 10, 20)
EARLY = datetime(2026, 10, 1, tzinfo=TZ)


def at(hour: int, minute: int = 0, day: date = DAY) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)


def hhmm(slots: list[datetime]) -> list[str]:
    return [s.strftime("%H:%M") for s in slots]


def test_whole_day_on_step_grid() -> None:
    slots = free_slots(
        day=DAY,
        tz=TZ,
        schedule=DaySchedule(work=(time(10), time(12))),
        busy=[],
        duration=timedelta(minutes=45),
        step=timedelta(minutes=15),
        not_before=EARLY,
    )
    assert hhmm(slots) == ["10:00", "10:15", "10:30", "10:45", "11:00", "11:15"]


def test_breaks_and_bookings_are_cut_out() -> None:
    slots = free_slots(
        day=DAY,
        tz=TZ,
        schedule=DaySchedule(work=(time(10), time(14)), breaks=[(time(12), time(13))]),
        busy=[Interval(at(10, 30), at(11, 10))],
        duration=timedelta(minutes=30),
        step=timedelta(minutes=30),
        not_before=EARLY,
    )
    # 11:10 rounds up to 11:30 on the grid; nothing fits across the lunch break.
    assert hhmm(slots) == ["10:00", "11:30", "13:00", "13:30"]


def test_day_off_has_no_slots() -> None:
    slots = free_slots(
        day=DAY,
        tz=TZ,
        schedule=DaySchedule(work=None),
        busy=[],
        duration=timedelta(minutes=30),
        step=timedelta(minutes=15),
        not_before=EARLY,
    )
    assert slots == []


def test_not_before_skips_past_and_rounds_up() -> None:
    slots = free_slots(
        day=DAY,
        tz=TZ,
        schedule=DaySchedule(work=(time(10), time(12))),
        busy=[],
        duration=timedelta(minutes=60),
        step=timedelta(minutes=15),
        not_before=at(10, 7),
    )
    assert hhmm(slots) == ["10:15", "10:30", "10:45", "11:00"]


def test_time_off_covering_day_blocks_everything() -> None:
    vacation = Interval(at(0), at(0, day=DAY + timedelta(days=3)))
    slots = free_slots(
        day=DAY,
        tz=TZ,
        schedule=DaySchedule(work=(time(10), time(20))),
        busy=[vacation],
        duration=timedelta(minutes=30),
        step=timedelta(minutes=15),
        not_before=EARLY,
    )
    assert slots == []


def test_busy_given_in_utc_is_compared_correctly() -> None:
    utc_booking = Interval(at(11).astimezone(ZoneInfo("UTC")), at(12).astimezone(ZoneInfo("UTC")))
    slots = free_slots(
        day=DAY,
        tz=TZ,
        schedule=DaySchedule(work=(time(10), time(13))),
        busy=[utc_booking],
        duration=timedelta(minutes=60),
        step=timedelta(minutes=60),
        not_before=EARLY,
    )
    assert hhmm(slots) == ["10:00", "12:00"]


def test_subtract_splits_interval() -> None:
    base = Interval(at(10), at(18))
    pieces = subtract(base, [Interval(at(12), at(13)), Interval(at(15), at(16))])
    assert [(p.start.hour, p.end.hour) for p in pieces] == [(10, 12), (13, 15), (16, 18)]
