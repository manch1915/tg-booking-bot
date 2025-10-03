from booking.domain.enums import Language
from booking.i18n import fmt_datetime, t
from booking.infra.db.models import Booking, Business
from booking.services.business import business_tz


def deposit_texts(booking: Booking, business: Business, lang: Language) -> tuple[str, str]:
    ru = lang is Language.RU
    service = booking.service.name_ru if ru else booking.service.name_en
    master = booking.master.name if ru else (booking.master.name_en or booking.master.name)
    title = t(lang, "invoice.title", service=service)
    description = t(
        lang,
        "invoice.description",
        master=master,
        when=fmt_datetime(booking.starts_at, business_tz(business), lang),
        hours=business.cancel_window_hours,
    )
    return title, description
