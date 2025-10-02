"""Callback payloads shared by the bot handlers and the notification worker."""

from aiogram.filters.callback_data import CallbackData


class MenuCb(CallbackData, prefix="m"):
    action: str


class CategoryCb(CallbackData, prefix="c"):
    id: int


class ServiceCb(CallbackData, prefix="s"):
    id: int


class MasterCb(CallbackData, prefix="ms"):
    service_id: int
    master_id: int  # 0 means "any free barber"


class DayCb(CallbackData, prefix="d"):
    service_id: int
    master_id: int
    day: str  # YYYYMMDD
    booking_id: int = 0  # set when moving an existing booking


class DaysPageCb(CallbackData, prefix="dp"):
    service_id: int
    master_id: int
    booking_id: int = 0


class SlotCb(CallbackData, prefix="t"):
    service_id: int
    master_id: int
    ts: int
    booking_id: int = 0


class ConfirmCb(CallbackData, prefix="cf"):
    action: str  # bonus | card | stars | site


class BookingCb(CallbackData, prefix="b"):
    id: int
    action: str  # view | cancel | cancel_yes | move | pay | keep


class ReviewCb(CallbackData, prefix="r"):
    booking_id: int
    rating: int


class TipCb(CallbackData, prefix="tip"):
    booking_id: int
    amount: int


class WaitlistCb(CallbackData, prefix="w"):
    service_id: int
    master_id: int
    day: str
