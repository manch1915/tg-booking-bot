from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from booking.domain.enums import Language
from booking.i18n import Raw, fmt_date, fmt_datetime, fmt_money, t
from booking.i18n.texts import keys


def test_locales_have_the_same_keys() -> None:
    assert keys(Language.RU) == keys(Language.EN)


def test_params_are_escaped_unless_raw() -> None:
    assert t("en", "bookings.line", when="<b>", service="x") == "&lt;b&gt; · x"
    assert t("en", "bookings.line", when=Raw("<b>y</b>"), service="x") == "<b>y</b> · x"


def test_money_format() -> None:
    assert fmt_money(2800, "USD") == "$28"
    assert fmt_money(1750, "USD") == "$17.50"
    assert fmt_money(550, "XTR") == "550 ⭐"
    assert fmt_money(-300, "USD") == "-$3"


def test_dates_in_both_languages() -> None:
    assert fmt_date(date(2026, 10, 22), Language.RU) == "чт, 22 октября"
    assert fmt_date(date(2026, 10, 22), Language.EN) == "Thu, 22 Oct"
    moment = datetime(2026, 10, 22, 10, 30, tzinfo=UTC)
    assert fmt_datetime(moment, ZoneInfo("Asia/Yerevan"), Language.RU) == "чт, 22 октября в 14:30"
