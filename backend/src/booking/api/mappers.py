from datetime import datetime

from booking.api.schemas import (
    BookingMasterRef,
    BookingOut,
    BookingServiceRef,
    BusinessOut,
    ClientOut,
    Localized,
    MasterOut,
    PaymentIntentOut,
    ReviewOut,
    ServiceOut,
)
from booking.config import Settings
from booking.domain.enums import ACTIVE_STATUSES, BookingStatus, PaymentPurpose, PaymentStatus
from booking.domain.policies import change_policy
from booking.infra.db.models import Booking, Business, Client, Master, Service
from booking.services.payments import PaymentIntent


def business_out(business: Business, settings: Settings) -> BusinessOut:
    return BusinessOut(
        name=business.name,
        tagline=Localized(ru=business.tagline_ru, en=business.tagline_en),
        address=business.address,
        phone=business.phone,
        timezone=business.timezone,
        currency=business.currency,
        cover_url=business.cover_url,
        cancel_window_hours=business.cancel_window_hours,
        deposit_percent=business.deposit_percent,
        cashback_percent=business.cashback_percent,
        max_bonus_share_percent=business.max_bonus_share_percent,
        referral_bonus=business.referral_bonus,
        welcome_bonus=business.welcome_bonus,
        hold_minutes=business.hold_minutes,
        stars_enabled=business.stars_enabled,
        stars_per_usd=settings.stars_per_usd,
        stars_fixed_price=settings.stars_fixed_price,
        bot_username=settings.bot_username,
        demo_mode=settings.demo_mode,
    )


def master_out(master: Master, rating: tuple[float, int] | None = None) -> MasterOut:
    avg, count = rating or (None, 0)
    return MasterOut(
        id=master.id,
        name=Localized(ru=master.name, en=master.name_en or master.name),
        title=Localized(ru=master.title_ru, en=master.title_en),
        bio=Localized(ru=master.bio_ru, en=master.bio_en),
        photo_url=master.photo_url,
        color=master.color,
        rating=round(avg, 2) if avg is not None else None,
        reviews=count,
    )


def service_out(service: Service) -> ServiceOut:
    links = [link for link in service.masters if link.master.is_active]
    prices = [link.price if link.price is not None else service.price for link in links]
    return ServiceOut(
        id=service.id,
        category_id=service.category_id,
        name=Localized(ru=service.name_ru, en=service.name_en),
        description=Localized(ru=service.description_ru, en=service.description_en),
        duration_minutes=service.duration_minutes,
        price=service.price,
        price_from=min(prices, default=service.price),
        photo_url=service.photo_url,
        is_popular=service.is_popular,
        master_ids=[link.master_id for link in links],
    )


def client_out(client: Client, settings: Settings, stats: dict[str, int]) -> ClientOut:
    return ClientOut(
        id=client.id,
        name=client.name,
        phone=client.phone,
        language=client.language,
        bonus_balance=client.bonus_balance,
        referral_code=client.referral_code,
        referral_link=f"https://t.me/{settings.bot_username}?start=ref_{client.referral_code}",
        visits=stats["visits"],
        invited=stats["invited"],
        is_demo_guest=client.is_demo_guest,
        in_telegram=client.telegram_id is not None,
    )


def booking_out(booking: Booking, business: Business, now: datetime) -> BookingOut:
    policy = change_policy(
        starts_at=booking.starts_at, now=now, window_hours=business.cancel_window_hours
    )
    deposits = [p for p in booking.payments if p.purpose is PaymentPurpose.DEPOSIT]
    settled = [p for p in deposits if p.status is not PaymentStatus.CANCELLED]
    pending = next((p for p in deposits if p.status is PaymentStatus.PENDING), None)
    active = booking.status in ACTIVE_STATUSES
    return BookingOut(
        id=booking.id,
        status=booking.status,
        source=booking.source,
        starts_at=booking.starts_at,
        ends_at=booking.ends_at,
        service=BookingServiceRef(
            id=booking.service.id,
            name=Localized(ru=booking.service.name_ru, en=booking.service.name_en),
            photo_url=booking.service.photo_url,
        ),
        master=BookingMasterRef(
            id=booking.master.id,
            name=Localized(
                ru=booking.master.name, en=booking.master.name_en or booking.master.name
            ),
            photo_url=booking.master.photo_url,
            color=booking.master.color,
        ),
        price=booking.price,
        deposit=booking.deposit,
        bonus_spent=booking.bonus_spent,
        payment_method=booking.payment_method,
        deposit_status=settled[-1].status if settled else None,
        pending_payment_id=pending.id if pending else None,
        hold_expires_at=booking.hold_expires_at,
        can_cancel=active and policy.can_cancel,
        can_reschedule=booking.status is BookingStatus.CONFIRMED and policy.can_reschedule,
        refund_deadline=policy.deadline,
        review=ReviewOut(rating=booking.review.rating, comment=booking.review.comment)
        if booking.review
        else None,
    )


def intent_out(intent: PaymentIntent) -> PaymentIntentOut:
    return PaymentIntentOut(
        payment_id=intent.payment_id,
        provider=intent.provider,
        amount=intent.amount,
        currency=intent.currency,
        invoice_url=intent.invoice_url,
    )
