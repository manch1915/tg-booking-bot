from enum import StrEnum


class BookingStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


# Statuses that occupy the master's time. Mirrors the WHERE clause of the exclusion constraint.
ACTIVE_STATUSES = (BookingStatus.PENDING_PAYMENT, BookingStatus.CONFIRMED)


class BookingSource(StrEnum):
    BOT = "bot"
    MINIAPP = "miniapp"
    ADMIN = "admin"


class PaymentMethod(StrEnum):
    CARD = "card"
    STARS = "stars"
    ON_SITE = "on_site"


class PaymentProvider(StrEnum):
    TELEGRAM_CARD = "telegram_card"
    STARS = "stars"
    DEMO = "demo"


class PaymentPurpose(StrEnum):
    DEPOSIT = "deposit"
    TIP = "tip"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    REFUNDED = "refunded"
    REFUND_PENDING = "refund_pending"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BonusKind(StrEnum):
    CASHBACK = "cashback"
    REFERRAL = "referral"
    SPEND = "spend"
    RETURN = "return"
    MANUAL = "manual"
    WELCOME = "welcome"


class NotificationKind(StrEnum):
    BOOKING_CONFIRMED = "booking_confirmed"
    REMINDER_DAY = "reminder_day"
    REMINDER_SOON = "reminder_soon"
    REVIEW_REQUEST = "review_request"
    BOOKING_CANCELLED = "booking_cancelled"
    BOOKING_RESCHEDULED = "booking_rescheduled"
    MASTER_NEW_BOOKING = "master_new_booking"
    MASTER_CANCELLED = "master_cancelled"
    MASTER_RESCHEDULED = "master_rescheduled"
    WAITLIST_SLOT = "waitlist_slot"
    BONUS_ACCRUED = "bonus_accrued"
    BROADCAST = "broadcast"


class WaitlistStatus(StrEnum):
    WAITING = "waiting"
    NOTIFIED = "notified"
    BOOKED = "booked"
    EXPIRED = "expired"


class AdminRole(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"


class Segment(StrEnum):
    ALL = "all"
    INACTIVE_30 = "inactive_30"
    NEW_CLIENTS = "new_clients"
    WITH_BONUSES = "with_bonuses"
    MASTER_REGULARS = "master_regulars"


class Language(StrEnum):
    RU = "ru"
    EN = "en"
