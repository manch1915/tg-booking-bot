from datetime import date, datetime, time

from pydantic import BaseModel, Field

from booking.api.schemas import BookingOut, Localized, MasterOut
from booking.domain.enums import AdminRole, PaymentProvider, PaymentStatus, Segment


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=1, max_length=200)


class AdminOut(BaseModel):
    id: int
    email: str
    name: str
    role: AdminRole
    demo: bool


class ClientRef(BaseModel):
    id: int
    name: str
    phone: str | None
    in_telegram: bool


class PaymentOut(BaseModel):
    id: int
    provider: PaymentProvider
    purpose: str
    status: PaymentStatus
    amount: int
    currency: str
    amount_base: int
    paid_at: datetime | None


class AdminBookingOut(BookingOut):
    client: ClientRef
    comment: str
    created_at: datetime
    cancel_reason: str
    payments: list[PaymentOut]


class SpanOut(BaseModel):
    start: time
    end: time


class ShiftOut(BaseModel):
    day: date
    work: SpanOut | None
    breaks: list[SpanOut]


class TimeOffOut(BaseModel):
    id: int
    master_id: int
    starts_at: datetime
    ends_at: datetime
    reason: str


class JournalMaster(BaseModel):
    master: MasterOut
    shifts: list[ShiftOut]


class JournalOut(BaseModel):
    days: list[date]
    timezone: str
    masters: list[JournalMaster]
    time_off: list[TimeOffOut]
    bookings: list[AdminBookingOut]


class ManualBookingIn(BaseModel):
    client_id: int | None = None
    client_name: str = Field(default="", max_length=120)
    client_phone: str = Field(default="", max_length=32)
    service_id: int
    master_id: int
    starts_at: datetime
    comment: str = Field(default="", max_length=500)


class StatusIn(BaseModel):
    action: str = Field(pattern="^(complete|no_show|cancel)$")
    reason: str = Field(default="", max_length=200)


class AdminRescheduleIn(BaseModel):
    starts_at: datetime
    master_id: int | None = None


class DaySpanIn(BaseModel):
    weekday: int = Field(ge=0, le=6)
    start: time
    end: time


class ScheduleIn(BaseModel):
    hours: list[DaySpanIn]
    breaks: list[DaySpanIn] = []


class MasterServiceOut(BaseModel):
    service_id: int
    price: int | None
    duration_minutes: int | None


class AdminMasterOut(BaseModel):
    master: MasterOut
    is_active: bool
    telegram_linked: bool
    link_url: str | None
    hours: list[DaySpanIn]
    breaks: list[DaySpanIn]
    services: list[MasterServiceOut]


class MasterIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    name_en: str = Field(default="", max_length=80)
    title_ru: str = Field(default="", max_length=80)
    title_en: str = Field(default="", max_length=80)
    bio_ru: str = Field(default="", max_length=1000)
    bio_en: str = Field(default="", max_length=1000)
    color: str = Field(default="#1F4D3F", pattern="^#[0-9A-Fa-f]{6}$")
    photo_url: str = Field(default="", max_length=300)
    is_active: bool = True


class MasterServicesIn(BaseModel):
    services: list[MasterServiceOut]


class TimeOffIn(BaseModel):
    starts_at: datetime
    ends_at: datetime
    reason: str = Field(default="", max_length=120)


class AdminServiceOut(BaseModel):
    id: int
    category_id: int
    category: Localized
    name: Localized
    description: Localized
    duration_minutes: int
    price: int
    photo_url: str
    is_popular: bool
    is_active: bool
    masters: int


class ServiceIn(BaseModel):
    category_id: int
    name_ru: str = Field(min_length=1, max_length=120)
    name_en: str = Field(min_length=1, max_length=120)
    description_ru: str = Field(default="", max_length=1000)
    description_en: str = Field(default="", max_length=1000)
    duration_minutes: int = Field(ge=5, le=480)
    price: int = Field(ge=0, le=10_000_00)
    photo_url: str = Field(default="", max_length=300)
    is_popular: bool = False
    is_active: bool = True


class CategoryOutAdmin(BaseModel):
    id: int
    name: Localized


class AdminClientRow(BaseModel):
    id: int
    name: str
    phone: str | None
    language: str
    in_telegram: bool
    bonus_balance: int
    visits: int
    last_visit: datetime | None
    spent: int
    created_at: datetime


class ClientsPage(BaseModel):
    items: list[AdminClientRow]
    total: int


class BonusTxAdmin(BaseModel):
    kind: str
    amount: int
    comment: str
    created_at: datetime


class ClientDetail(BaseModel):
    client: AdminClientRow
    notes: str
    referral_code: str
    invited: int
    bookings: list[AdminBookingOut]
    bonuses: list[BonusTxAdmin]


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=2000)


class BonusAdjustIn(BaseModel):
    amount: int = Field(ge=-100_000, le=100_000)
    comment: str = Field(default="", max_length=200)


class AudienceIn(BaseModel):
    segment: Segment
    master_id: int | None = None


class AudienceOut(BaseModel):
    total: int
    reachable: int


class BroadcastIn(AudienceIn):
    text_ru: str = Field(default="", max_length=3500)
    text_en: str = Field(default="", max_length=3500)


class BroadcastOut(BaseModel):
    id: int
    segment: Segment
    segment_master_id: int | None
    text_ru: str
    text_en: str
    recipients: int
    delivered: int
    created_by: str
    created_at: datetime


class DayPoint(BaseModel):
    day: date
    revenue: int
    visits: int


class MasterReport(BaseModel):
    master_id: int
    revenue: int
    visits: int
    load: float
    rating: float | None
    reviews: int


class ServiceReport(BaseModel):
    service_id: int
    name: Localized
    visits: int
    revenue: int


class ReportOut(BaseModel):
    start: date
    end: date
    revenue: int
    visits: int
    average_check: int
    no_shows: int
    no_show_rate: float
    cancellations: int
    new_clients: int
    deposits: int
    tips_stars: int
    load: float
    by_day: list[DayPoint]
    by_master: list[MasterReport]
    by_service: list[ServiceReport]
    by_source: dict[str, int]
    by_method: dict[str, int]
    previous_revenue: int
    previous_visits: int


class ReviewRow(BaseModel):
    id: int
    rating: int
    comment: str
    client: str
    master_id: int
    service: Localized
    created_at: datetime


class WaitlistRow(BaseModel):
    id: int
    client: ClientRef
    service: Localized
    master_id: int | None
    day: date
    status: str
    created_at: datetime


class SettingsIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    tagline_ru: str = Field(default="", max_length=200)
    tagline_en: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=40)
    cancel_window_hours: int = Field(ge=0, le=72)
    deposit_percent: int = Field(ge=0, le=100)
    cashback_percent: int = Field(ge=0, le=50)
    max_bonus_share_percent: int = Field(ge=0, le=100)
    referral_bonus: int = Field(ge=0, le=100_00)
    welcome_bonus: int = Field(ge=0, le=100_00)
    hold_minutes: int = Field(ge=3, le=60)
    stars_enabled: bool
