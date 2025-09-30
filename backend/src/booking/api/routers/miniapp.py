from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select

from booking.api import mappers
from booking.api.deps import Bookings, CurrentClient, Payments, Session, State
from booking.api.schemas import (
    AuthOut,
    BonusTxOut,
    BookingCreatedOut,
    BookingIn,
    BookingOut,
    BusinessOut,
    CancelOut,
    CatalogOut,
    CategoryOut,
    ClientOut,
    DayOut,
    DemoAuthIn,
    Localized,
    OfferOut,
    PaymentIntentOut,
    ProfileIn,
    RescheduleIn,
    ReviewIn,
    SlotOut,
    TelegramAuthIn,
    WaitlistIn,
)
from booking.domain.enums import BookingSource, BookingStatus, Language, PaymentStatus
from booking.i18n import fmt_datetime, t
from booking.infra.db.models import BonusTransaction, Booking, Client, Payment
from booking.services.auth import verify_init_data
from booking.services.availability import AvailabilityService
from booking.services.booking import BookingRequest
from booking.services.business import business_tz, load_business
from booking.services.catalog import CatalogService
from booking.services.clients import ClientService, TelegramProfile
from booking.services.errors import AuthError, NotFoundError
from booking.services.payments import PaymentIntent, PaymentService
from booking.services.reviews import ReviewService
from booking.services.waitlist import WaitlistService

router = APIRouter(prefix="/api/app", tags=["mini app"])


async def _client_out(state: State, session: Session, client: Client) -> ClientOut:
    stats = await ClientService(session, state.clock).stats(client)
    return mappers.client_out(client, state.settings, stats)


async def _booking_out(state: State, session: Session, booking: Booking) -> BookingOut:
    business = await load_business(session)
    return mappers.booking_out(booking, business, state.clock.now())


async def _payment_intent(
    session: Session, payments: PaymentService, booking: Booking, payment: Payment
) -> PaymentIntent:
    business = await load_business(session)
    lang = booking.client.language
    ru = lang is Language.RU
    master = booking.master.name if ru else booking.master.name_en
    service = booking.service.name_ru if ru else booking.service.name_en
    return await payments.intent(
        payment,
        title=t(lang, "invoice.title", service=service),
        description=t(
            lang,
            "invoice.description",
            master=master,
            when=fmt_datetime(booking.starts_at, business_tz(business), lang),
            hours=business.cancel_window_hours,
        ),
    )


@router.post("/auth/telegram")
async def auth_telegram(body: TelegramAuthIn, state: State, session: Session) -> AuthOut:
    if state.settings.bot_token is None:
        raise AuthError("Telegram login is not configured")
    data = verify_init_data(state.settings.bot_token.get_secret_value(), body.init_data)
    assert data.user is not None
    referral = None
    if data.start_param and data.start_param.startswith("ref_"):
        referral = data.start_param[4:]
    client, _ = await ClientService(session, state.clock).from_telegram(
        TelegramProfile(
            id=data.user.id,
            first_name=data.user.first_name,
            last_name=data.user.last_name,
            username=data.user.username,
            language_code=data.user.language_code,
        ),
        referral_code=referral,
    )
    token = state.tokens.issue("client", client.id)
    return AuthOut(token=token, client=await _client_out(state, session, client))


@router.post("/auth/demo")
async def auth_demo(body: DemoAuthIn, state: State, session: Session) -> AuthOut:
    if not state.settings.demo_mode:
        raise NotFoundError("Demo access is turned off")
    client = await ClientService(session, state.clock).create_demo_guest(body.language)
    token = state.tokens.issue("client", client.id)
    return AuthOut(token=token, client=await _client_out(state, session, client))


@router.get("/business")
async def business(state: State, session: Session) -> BusinessOut:
    return mappers.business_out(await load_business(session), state.settings)


@router.get("/catalog")
async def catalog(session: Session) -> CatalogOut:
    service = CatalogService(session)
    ratings = await service.ratings()
    categories = [
        CategoryOut(
            id=category.id,
            name=Localized(ru=category.name_ru, en=category.name_en),
            services=[mappers.service_out(s) for s in category.services if s.is_active],
        )
        for category in await service.categories()
    ]
    masters = [mappers.master_out(m, ratings.get(m.id)) for m in await service.masters()]
    return CatalogOut(categories=[c for c in categories if c.services], masters=masters)


@router.get("/services/{service_id}/offers")
async def offers(service_id: int, session: Session) -> list[OfferOut]:
    return [
        OfferOut(
            master=mappers.master_out(o.master, (o.rating, o.reviews) if o.rating else None),
            price=o.price,
            duration_minutes=o.duration_minutes,
        )
        for o in await CatalogService(session).offers(service_id)
    ]


@router.get("/availability/calendar")
async def calendar(
    state: State,
    session: Session,
    service_id: int,
    master_id: Annotated[int | None, Query()] = None,
) -> list[DayOut]:
    days = await AvailabilityService(session, state.clock).calendar(service_id, master_id=master_id)
    return [DayOut(day=d.day, slots=d.slots) for d in days]


@router.get("/availability/slots")
async def slots(
    state: State,
    session: Session,
    service_id: int,
    day: date,
    master_id: Annotated[int | None, Query()] = None,
    exclude_booking_id: Annotated[int | None, Query()] = None,
) -> list[SlotOut]:
    found = await AvailabilityService(session, state.clock).day_slots(
        service_id, day, master_id=master_id, exclude_booking_id=exclude_booking_id
    )
    return [SlotOut(starts_at=s.starts_at, master_ids=s.master_ids) for s in found]


@router.get("/me")
async def me(client: CurrentClient, state: State, session: Session) -> ClientOut:
    return await _client_out(state, session, client)


@router.patch("/me")
async def update_me(
    body: ProfileIn, client: CurrentClient, state: State, session: Session
) -> ClientOut:
    await ClientService(session, state.clock).update_profile(
        client, name=body.name, phone=body.phone, language=body.language
    )
    return await _client_out(state, session, client)


@router.get("/me/bonuses")
async def bonus_history(client: CurrentClient, session: Session) -> list[BonusTxOut]:
    rows = await session.scalars(
        select(BonusTransaction)
        .where(BonusTransaction.client_id == client.id)
        .order_by(BonusTransaction.created_at.desc(), BonusTransaction.id.desc())
        .limit(50)
    )
    return [
        BonusTxOut(
            id=tx.id,
            kind=tx.kind.value,
            amount=tx.amount,
            comment=tx.comment,
            created_at=tx.created_at,
        )
        for tx in rows
    ]


@router.get("/bookings")
async def my_bookings(
    client: CurrentClient, state: State, session: Session, bookings: Bookings
) -> list[BookingOut]:
    business = await load_business(session)
    now = state.clock.now()
    return [
        mappers.booking_out(b, business, now) for b in await bookings.client_bookings(client.id)
    ]


@router.post("/bookings", status_code=201)
async def create_booking(
    body: BookingIn,
    client: CurrentClient,
    state: State,
    session: Session,
    bookings: Bookings,
    payments: Payments,
) -> BookingCreatedOut:
    booking = await bookings.create(
        client,
        BookingRequest(
            service_id=body.service_id,
            master_id=body.master_id,
            starts_at=body.starts_at,
            payment_method=body.payment_method,
            use_bonus=body.use_bonus,
            source=BookingSource.MINIAPP,
            comment=body.comment,
        ),
    )
    intent = None
    pending = next((p for p in booking.payments if p.status is PaymentStatus.PENDING), None)
    if pending is not None:
        intent = mappers.intent_out(await _payment_intent(session, payments, booking, pending))
    return BookingCreatedOut(booking=await _booking_out(state, session, booking), payment=intent)


@router.get("/bookings/{booking_id}")
async def booking_detail(
    booking_id: int, client: CurrentClient, state: State, session: Session, bookings: Bookings
) -> BookingOut:
    booking = await bookings.get_for_client(booking_id, client.id)
    return await _booking_out(state, session, booking)


@router.post("/bookings/{booking_id}/pay")
async def pay_booking(
    booking_id: int, client: CurrentClient, session: Session, bookings: Bookings, payments: Payments
) -> PaymentIntentOut:
    booking = await bookings.get_for_client(booking_id, client.id)
    pending = next((p for p in booking.payments if p.status is PaymentStatus.PENDING), None)
    if booking.status is not BookingStatus.PENDING_PAYMENT or pending is None:
        raise NotFoundError("Nothing to pay for this booking")
    return mappers.intent_out(await _payment_intent(session, payments, booking, pending))


@router.post("/payments/{payment_id}/demo-confirm")
async def demo_confirm(
    payment_id: int, client: CurrentClient, state: State, session: Session, bookings: Bookings
) -> BookingOut:
    outcome = await bookings.complete_demo_payment(payment_id, client)
    return await _booking_out(state, session, outcome.booking)


@router.post("/bookings/{booking_id}/cancel")
async def cancel_booking(
    booking_id: int, client: CurrentClient, state: State, session: Session, bookings: Bookings
) -> CancelOut:
    booking = await bookings.get_for_client(booking_id, client.id)
    result = await bookings.cancel(booking, by_client=True, reason="client")
    return CancelOut(
        booking=await _booking_out(state, session, await bookings.get(booking.id)),
        refund=result.refund,
        late=result.late,
    )


@router.post("/bookings/{booking_id}/reschedule")
async def reschedule_booking(
    booking_id: int,
    body: RescheduleIn,
    client: CurrentClient,
    state: State,
    session: Session,
    bookings: Bookings,
) -> BookingOut:
    booking = await bookings.get_for_client(booking_id, client.id)
    moved = await bookings.reschedule(
        booking, body.starts_at, master_id=body.master_id, by_client=True
    )
    return await _booking_out(state, session, moved)


@router.post("/bookings/{booking_id}/review")
async def review_booking(
    booking_id: int,
    body: ReviewIn,
    client: CurrentClient,
    state: State,
    session: Session,
    bookings: Bookings,
) -> BookingOut:
    booking = await bookings.get_for_client(booking_id, client.id)
    await ReviewService(session, state.clock).leave(booking, body.rating, body.comment)
    return await _booking_out(state, session, await bookings.get(booking.id))


@router.post("/waitlist", status_code=201)
async def join_waitlist(
    body: WaitlistIn, client: CurrentClient, state: State, session: Session
) -> dict[str, int]:
    await CatalogService(session).service(body.service_id)
    entry = await WaitlistService(session, state.clock).join(
        client.id, body.service_id, body.day, body.master_id
    )
    return {"id": entry.id}
