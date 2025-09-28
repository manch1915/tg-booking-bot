from datetime import date, datetime
from zoneinfo import ZoneInfo

from booking.domain.enums import Language

MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip
WEEKDAYS_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
MONTHS_EN = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)  # fmt: skip
WEEKDAYS_EN = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SYMBOLS = {"USD": "$", "EUR": "€", "RUB": "₽", "AMD": "֏"}


def fmt_money(amount: int, currency: str) -> str:
    if currency == "XTR":
        return f"{amount} ⭐"
    units, cents = divmod(abs(amount), 100)
    sign = "-" if amount < 0 else ""
    value = f"{units:,}".replace(",", " ") + (f".{cents:02d}" if cents else "")
    symbol = SYMBOLS.get(currency)
    return f"{sign}{symbol}{value}" if symbol else f"{sign}{value} {currency}"


def fmt_date(day: date, lang: Language) -> str:
    if lang is Language.RU:
        return f"{WEEKDAYS_RU[day.weekday()]}, {day.day} {MONTHS_RU[day.month - 1]}"
    return f"{WEEKDAYS_EN[day.weekday()]}, {day.day} {MONTHS_EN[day.month - 1]}"


def fmt_time(moment: datetime, tz: ZoneInfo) -> str:
    return moment.astimezone(tz).strftime("%H:%M")


def fmt_datetime(moment: datetime, tz: ZoneInfo, lang: Language) -> str:
    local = moment.astimezone(tz)
    joiner = " в " if lang is Language.RU else " at "
    return f"{fmt_date(local.date(), lang)}{joiner}{local:%H:%M}"
