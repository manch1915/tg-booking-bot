from datetime import date, datetime, time
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from booking.domain.enums import (
    AdminRole,
    BonusKind,
    BookingSource,
    BookingStatus,
    Language,
    NotificationKind,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    Segment,
    WaitlistStatus,
)

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def pg_enum(enum_cls: type[Any], name: str) -> Enum:
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e])


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Business(Base):
    __tablename__ = "business"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    tagline_ru: Mapped[str] = mapped_column(String(200), default="")
    tagline_en: Mapped[str] = mapped_column(String(200), default="")
    address: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    cover_url: Mapped[str] = mapped_column(String(300), default="")

    cancel_window_hours: Mapped[int] = mapped_column(SmallInteger, default=3)
    deposit_percent: Mapped[int] = mapped_column(SmallInteger, default=30)
    cashback_percent: Mapped[int] = mapped_column(SmallInteger, default=5)
    max_bonus_share_percent: Mapped[int] = mapped_column(SmallInteger, default=30)
    referral_bonus: Mapped[int] = mapped_column(Integer, default=500)
    welcome_bonus: Mapped[int] = mapped_column(Integer, default=300)
    slot_step_minutes: Mapped[int] = mapped_column(SmallInteger, default=15)
    booking_horizon_days: Mapped[int] = mapped_column(SmallInteger, default=14)
    min_lead_minutes: Mapped[int] = mapped_column(SmallInteger, default=60)
    hold_minutes: Mapped[int] = mapped_column(SmallInteger, default=10)
    stars_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ru: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80))
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)

    services: Mapped[list["Service"]] = relationship(
        back_populates="category", order_by="(Service.sort, Service.id)"
    )


class Service(Base):
    __tablename__ = "service"

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="RESTRICT"))
    name_ru: Mapped[str] = mapped_column(String(120))
    name_en: Mapped[str] = mapped_column(String(120))
    description_ru: Mapped[str] = mapped_column(Text, default="")
    description_en: Mapped[str] = mapped_column(Text, default="")
    duration_minutes: Mapped[int] = mapped_column(SmallInteger)
    price: Mapped[int] = mapped_column(Integer)
    photo_url: Mapped[str] = mapped_column(String(300), default="")
    is_popular: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)

    category: Mapped[Category] = relationship(back_populates="services")
    masters: Mapped[list["MasterService"]] = relationship(
        back_populates="service", cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="duration_positive"),
        CheckConstraint("price >= 0", name="price_non_negative"),
    )


class Master(Base):
    __tablename__ = "master"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    name_en: Mapped[str] = mapped_column(String(80), default="")
    title_ru: Mapped[str] = mapped_column(String(80), default="")
    title_en: Mapped[str] = mapped_column(String(80), default="")
    bio_ru: Mapped[str] = mapped_column(Text, default="")
    bio_en: Mapped[str] = mapped_column(Text, default="")
    photo_url: Mapped[str] = mapped_column(String(300), default="")
    color: Mapped[str] = mapped_column(String(7), default="#7A2E1F")
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    link_token: Mapped[str | None] = mapped_column(String(40), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(SmallInteger, default=0)

    services: Mapped[list["MasterService"]] = relationship(
        back_populates="master", cascade="all, delete-orphan"
    )
    hours: Mapped[list["WorkingHours"]] = relationship(
        back_populates="master", cascade="all, delete-orphan", order_by="WorkingHours.weekday"
    )
    breaks: Mapped[list["BreakRule"]] = relationship(
        back_populates="master", cascade="all, delete-orphan"
    )


class MasterService(Base):
    """Which services a master performs, with optional price and duration overrides."""

    __tablename__ = "master_service"

    master_id: Mapped[int] = mapped_column(
        ForeignKey("master.id", ondelete="CASCADE"), primary_key=True
    )
    service_id: Mapped[int] = mapped_column(
        ForeignKey("service.id", ondelete="CASCADE"), primary_key=True
    )
    price: Mapped[int | None] = mapped_column(Integer)
    duration_minutes: Mapped[int | None] = mapped_column(SmallInteger)

    master: Mapped[Master] = relationship(back_populates="services")
    service: Mapped[Service] = relationship(back_populates="masters")


class WorkingHours(Base):
    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("master.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    master: Mapped[Master] = relationship(back_populates="hours")

    __table_args__ = (
        UniqueConstraint("master_id", "weekday"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
    )


class BreakRule(Base):
    __tablename__ = "break_rule"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("master.id", ondelete="CASCADE"))
    weekday: Mapped[int] = mapped_column(SmallInteger)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    master: Mapped[Master] = relationship(back_populates="breaks")


class TimeOff(Base, TimestampMixin):
    __tablename__ = "time_off"

    id: Mapped[int] = mapped_column(primary_key=True)
    master_id: Mapped[int] = mapped_column(ForeignKey("master.id", ondelete="CASCADE"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(String(120), default="")

    master: Mapped[Master] = relationship()

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="time_off_order"),
        Index("ix_time_off_master_period", "master_id", "starts_at", "ends_at"),
    )


class Client(Base, TimestampMixin):
    __tablename__ = "client"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(32))
    language: Mapped[Language] = mapped_column(pg_enum(Language, "language"), default=Language.RU)
    referral_code: Mapped[str] = mapped_column(String(16), unique=True)
    referred_by_id: Mapped[int | None] = mapped_column(ForeignKey("client.id", ondelete="SET NULL"))
    bonus_balance: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    is_demo_guest: Mapped[bool] = mapped_column(Boolean, default=False)
    marketing_opt_out: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (CheckConstraint("bonus_balance >= 0", name="bonus_non_negative"),)


class Booking(Base, TimestampMixin):
    __tablename__ = "booking"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"))
    master_id: Mapped[int] = mapped_column(ForeignKey("master.id", ondelete="RESTRICT"))
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id", ondelete="RESTRICT"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[BookingStatus] = mapped_column(pg_enum(BookingStatus, "booking_status"))
    source: Mapped[BookingSource] = mapped_column(pg_enum(BookingSource, "booking_source"))
    payment_method: Mapped[PaymentMethod] = mapped_column(pg_enum(PaymentMethod, "payment_method"))
    price: Mapped[int] = mapped_column(Integer)
    deposit: Mapped[int] = mapped_column(Integer, default=0)
    bonus_spent: Mapped[int] = mapped_column(Integer, default=0)
    hold_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comment: Mapped[str] = mapped_column(Text, default="")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str] = mapped_column(String(200), default="")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped[Client] = relationship()
    master: Mapped[Master] = relationship()
    service: Mapped[Service] = relationship()
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="booking", order_by="Payment.id"
    )
    review: Mapped["Review | None"] = relationship(back_populates="booking")

    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="booking_order"),
        # The last line of defence against double booking: two active bookings of one master
        # can never overlap, whatever the application code does.
        ExcludeConstraint(
            ("master_id", "="),
            (func.tstzrange(text("starts_at"), text("ends_at"), "[)"), "&&"),
            name="booking_no_overlap",
            using="gist",
            where=text("status IN ('pending_payment', 'confirmed')"),
        ),
        Index("ix_booking_starts_at", "starts_at"),
        Index("ix_booking_client", "client_id", "starts_at"),
    )


class Payment(Base, TimestampMixin):
    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"))
    provider: Mapped[PaymentProvider] = mapped_column(pg_enum(PaymentProvider, "payment_provider"))
    purpose: Mapped[PaymentPurpose] = mapped_column(pg_enum(PaymentPurpose, "payment_purpose"))
    status: Mapped[PaymentStatus] = mapped_column(pg_enum(PaymentStatus, "payment_status"))
    # Minor units of `currency`; for Stars this is the number of Stars.
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    # Amount in the business currency, so reports can add Stars and cards together.
    amount_base: Mapped[int] = mapped_column(Integer)
    payload: Mapped[str] = mapped_column(String(64), unique=True)
    telegram_charge_id: Mapped[str | None] = mapped_column(String(128))
    provider_charge_id: Mapped[str | None] = mapped_column(String(128))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    booking: Mapped[Booking] = relationship(back_populates="payments")


class BonusTransaction(Base, TimestampMixin):
    __tablename__ = "bonus_transaction"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"), index=True)
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("booking.id", ondelete="SET NULL"))
    kind: Mapped[BonusKind] = mapped_column(pg_enum(BonusKind, "bonus_kind"))
    amount: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str] = mapped_column(String(200), default="")

    booking: Mapped["Booking | None"] = relationship()


class Review(Base, TimestampMixin):
    __tablename__ = "review"

    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        ForeignKey("booking.id", ondelete="CASCADE"), unique=True
    )
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"))
    master_id: Mapped[int] = mapped_column(ForeignKey("master.id", ondelete="CASCADE"), index=True)
    rating: Mapped[int] = mapped_column(SmallInteger)
    comment: Mapped[str] = mapped_column(Text, default="")

    booking: Mapped[Booking] = relationship(back_populates="review")
    client: Mapped[Client] = relationship()

    __table_args__ = (CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),)


class WaitlistEntry(Base, TimestampMixin):
    __tablename__ = "waitlist_entry"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"))
    service_id: Mapped[int] = mapped_column(ForeignKey("service.id", ondelete="CASCADE"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("master.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    status: Mapped[WaitlistStatus] = mapped_column(pg_enum(WaitlistStatus, "waitlist_status"))
    notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    client: Mapped[Client] = relationship()
    service: Mapped[Service] = relationship()

    __table_args__ = (Index("ix_waitlist_day_status", "day", "status"),)


class Notification(Base, TimestampMixin):
    """Outbox of messages to send. The worker picks due rows with SKIP LOCKED."""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[NotificationKind] = mapped_column(pg_enum(NotificationKind, "notification_kind"))
    chat_id: Mapped[int | None] = mapped_column(BigInteger)
    client_id: Mapped[int | None] = mapped_column(ForeignKey("client.id", ondelete="CASCADE"))
    master_id: Mapped[int | None] = mapped_column(ForeignKey("master.id", ondelete="CASCADE"))
    booking_id: Mapped[int | None] = mapped_column(ForeignKey("booking.id", ondelete="CASCADE"))
    broadcast_id: Mapped[int | None] = mapped_column(ForeignKey("broadcast.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0)
    error: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        Index(
            "ix_notification_due",
            "send_at",
            postgresql_where=text("sent_at IS NULL AND cancelled_at IS NULL"),
        ),
    )


class Broadcast(Base, TimestampMixin):
    __tablename__ = "broadcast"

    id: Mapped[int] = mapped_column(primary_key=True)
    segment: Mapped[Segment] = mapped_column(pg_enum(Segment, "segment"))
    segment_master_id: Mapped[int | None] = mapped_column(
        ForeignKey("master.id", ondelete="SET NULL")
    )
    text_ru: Mapped[str] = mapped_column(Text)
    text_en: Mapped[str] = mapped_column(Text)
    recipients: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[str] = mapped_column(String(120), default="")


class AdminUser(Base, TimestampMixin):
    __tablename__ = "admin_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[AdminRole] = mapped_column(pg_enum(AdminRole, "admin_role"))
