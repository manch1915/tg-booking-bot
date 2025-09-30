from datetime import date, datetime

from pydantic import BaseModel, Field

from booking.domain.enums import (
    BookingSource,
    BookingStatus,
    Language,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)


class Localized(BaseModel):
    ru: str
    en: str


class BusinessOut(BaseModel):
    name: str
    tagline: Localized
    address: str
    phone: str
    timezone: str
    currency: str
    cover_url: str
    cancel_window_hours: int
    deposit_percent: int
    cashback_percent: int
    max_bonus_share_percent: int
    referral_bonus: int
    welcome_bonus: int
    hold_minutes: int
    stars_enabled: bool
    stars_per_usd: int
    stars_fixed_price: int | None
    bot_username: str
    demo_mode: bool


class MasterOut(BaseModel):
    id: int
    name: Localized
    title: Localized
    bio: Localized
    photo_url: str
    color: str
    rating: float | None = None
    reviews: int = 0


class ServiceOut(BaseModel):
    id: int
    category_id: int
    name: Localized
    description: Localized
    duration_minutes: int
    price: int
    price_from: int
    photo_url: str
    is_popular: bool
    master_ids: list[int]


class CategoryOut(BaseModel):
    id: int
    name: Localized
    services: list[ServiceOut]


class CatalogOut(BaseModel):
    categories: list[CategoryOut]
    masters: list[MasterOut]


class OfferOut(BaseModel):
    master: MasterOut
    price: int
    duration_minutes: int


class DayOut(BaseModel):
    day: date
    slots: int


class SlotOut(BaseModel):
    starts_at: datetime
    master_ids: list[int]


class ClientOut(BaseModel):
    id: int
    name: str
    phone: str | None
    language: Language
    bonus_balance: int
    referral_code: str
    referral_link: str
    visits: int
    invited: int
    is_demo_guest: bool
    in_telegram: bool


class AuthOut(BaseModel):
    token: str
    client: ClientOut


class TelegramAuthIn(BaseModel):
    init_data: str = Field(min_length=10, max_length=4096)


class DemoAuthIn(BaseModel):
    language: Language = Language.RU


class ProfileIn(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    language: Language | None = None


class BookingIn(BaseModel):
    service_id: int
    master_id: int | None = None
    starts_at: datetime
    payment_method: PaymentMethod
    use_bonus: bool = False
    comment: str = Field(default="", max_length=500)


class RescheduleIn(BaseModel):
    starts_at: datetime
    master_id: int | None = None


class ReviewIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


class WaitlistIn(BaseModel):
    service_id: int
    day: date
    master_id: int | None = None


class PaymentIntentOut(BaseModel):
    payment_id: int
    provider: PaymentProvider
    amount: int
    currency: str
    invoice_url: str | None


class BookingServiceRef(BaseModel):
    id: int
    name: Localized
    photo_url: str


class BookingMasterRef(BaseModel):
    id: int
    name: Localized
    photo_url: str
    color: str


class ReviewOut(BaseModel):
    rating: int
    comment: str


class BookingOut(BaseModel):
    id: int
    status: BookingStatus
    source: BookingSource
    starts_at: datetime
    ends_at: datetime
    service: BookingServiceRef
    master: BookingMasterRef
    price: int
    deposit: int
    bonus_spent: int
    payment_method: PaymentMethod
    deposit_status: PaymentStatus | None
    pending_payment_id: int | None
    hold_expires_at: datetime | None
    can_cancel: bool
    can_reschedule: bool
    refund_deadline: datetime
    review: ReviewOut | None


class BookingCreatedOut(BaseModel):
    booking: BookingOut
    payment: PaymentIntentOut | None


class CancelOut(BaseModel):
    booking: BookingOut
    refund: PaymentStatus | None
    late: bool


class BonusTxOut(BaseModel):
    id: int
    kind: str
    amount: int
    comment: str
    created_at: datetime


class ErrorOut(BaseModel):
    error: str
    message: str
    details: dict[str, object] = {}
