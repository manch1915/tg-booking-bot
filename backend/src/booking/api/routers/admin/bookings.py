import csv
import io
from datetime import date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from booking.api import mappers
from booking.api.admin_schemas import (
    AdminBookingOut,
    AdminRescheduleIn,
    JournalMaster,
    JournalOut,
    ManualBookingIn,
    ShiftOut,
    SpanOut,
    StatusIn,
    TimeOffOut,
)
from booking.api.deps import AdminBookings, CurrentAdmin, Session, State
from booking.api.routers.admin.common import admin_booking_out, client_ref
from booking.domain.enums import BookingSource, BookingStatus, PaymentMethod
from booking.infra.db.models import Booking, Client
from booking.services.admin import ClientAdmin, ScheduleAdmin
from booking.services.booking import BookingRequest, booking_options
from booking.services.business import business_tz, load_business
from booking.services.catalog import CatalogService
from booking.services.errors import NotFoundError, PolicyError

router = APIRouter(prefix="/api/admin", tags=["admin bookings"])

FORMULA_STARTS = frozenset("=+-@\t\r")


@router.get("/journal")
async def journal(
    _: CurrentAdmin,
    state: State,
    session: Session,
    start: date,
    days: Annotated[int, Query(ge=1, le=7)] = 1,
) -> JournalOut:
    business = await load_business(session)
    tz = business_tz(business)
    span = [start + timedelta(days=i) for i in range(days)]
    lo = datetime.combine(start, time(0), tzinfo=tz)
    hi = lo + timedelta(days=days)

    schedule = ScheduleAdmin(session)
    ratings = await CatalogService(session).ratings()
    masters = [m for m in await schedule.masters() if m.is_active]
    journal_masters = []
    for master in masters:
        hours = {h.weekday: h for h in master.hours}
        shifts = []
        for day in span:
            work = hours.get(day.weekday())
            breaks = [b for b in master.breaks if b.weekday == day.weekday()]
            shifts.append(
                ShiftOut(
                    day=day,
                    work=SpanOut(start=work.start_time, end=work.end_time) if work else None,
                    breaks=[SpanOut(start=b.start_time, end=b.end_time) for b in breaks],
                )
            )
        journal_masters.append(
            JournalMaster(master=mappers.master_out(master, ratings.get(master.id)), shifts=shifts)
        )

    rows = await session.scalars(
        select(Booking)
        .where(Booking.starts_at < hi, Booking.ends_at > lo)
        .options(*booking_options())
        .order_by(Booking.starts_at)
    )
    now = state.clock.now()
    return JournalOut(
        days=span,
        timezone=business.timezone,
        masters=journal_masters,
        time_off=[
            TimeOffOut(
                id=o.id,
                master_id=o.master_id,
                starts_at=o.starts_at,
                ends_at=o.ends_at,
                reason=o.reason,
            )
            for o in await schedule.time_off(lo, hi)
        ],
        bookings=[admin_booking_out(b, business, now, state.settings.demo_mode) for b in rows],
    )


@router.get("/bookings")
async def list_bookings(
    _: CurrentAdmin,
    state: State,
    session: Session,
    start: date,
    end: date,
    status: BookingStatus | None = None,
    master_id: int | None = None,
) -> list[AdminBookingOut]:
    business = await load_business(session)
    return [
        admin_booking_out(b, business, state.clock.now(), state.settings.demo_mode)
        for b in await _bookings_between(session, start, end, status, master_id)
    ]


@router.get("/bookings.csv")
async def export_bookings(
    _: CurrentAdmin,
    state: State,
    session: Session,
    start: date,
    end: date,
    status: BookingStatus | None = None,
    master_id: int | None = None,
) -> StreamingResponse:
    business = await load_business(session)
    tz = business_tz(business)
    demo = state.settings.demo_mode
    buffer = io.StringIO()
    # BOM so Excel opens Cyrillic correctly.
    buffer.write("﻿")
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(
        [
            "id",
            "date",
            "time",
            "client",
            "phone",
            "service",
            "barber",
            "status",
            "source",
            "payment",
            "price",
            "bonus",
            "deposit",
        ]
    )
    for b in await _bookings_between(session, start, end, status, master_id):
        local = b.starts_at.astimezone(tz)
        writer.writerow(
            map(
                _cell,
                [
                    b.id,
                    local.date().isoformat(),
                    local.strftime("%H:%M"),
                    *_client_cells(b, demo),
                    b.service.name_ru,
                    b.master.name,
                    b.status.value,
                    b.source.value,
                    b.payment_method.value,
                    f"{b.price / 100:.2f}",
                    f"{b.bonus_spent / 100:.2f}",
                    f"{b.deposit / 100:.2f}",
                ],
            )
        )
    filename = f"bookings_{start.isoformat()}_{end.isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _client_cells(booking: Booking, mask: bool) -> list[str]:
    ref = client_ref(booking.client, mask)
    return [ref.name, ref.phone or ""]


def _cell(value: object) -> str:
    # Client names come from Telegram; a leading "=" must not turn into an Excel formula.
    text = str(value)
    return f"'{text}" if text[:1] in FORMULA_STARTS else text


async def _bookings_between(
    session: Session,
    start: date,
    end: date,
    status: BookingStatus | None,
    master_id: int | None,
) -> list[Booking]:
    if (end - start).days > 366 or end < start:
        raise PolicyError("Pick a period of up to one year")
    business = await load_business(session)
    tz = business_tz(business)
    lo = datetime.combine(start, time(0), tzinfo=tz)
    hi = datetime.combine(end + timedelta(days=1), time(0), tzinfo=tz)
    query = (
        select(Booking)
        .where(Booking.starts_at >= lo, Booking.starts_at < hi)
        .options(*booking_options())
        .order_by(Booking.starts_at)
    )
    if status is not None:
        query = query.where(Booking.status == status)
    if master_id is not None:
        query = query.where(Booking.master_id == master_id)
    return list(await session.scalars(query))


@router.get("/bookings/{booking_id}")
async def booking_detail(
    booking_id: int, _: CurrentAdmin, state: State, session: Session, bookings: AdminBookings
) -> AdminBookingOut:
    business = await load_business(session)
    return admin_booking_out(
        await bookings.get(booking_id), business, state.clock.now(), state.settings.demo_mode
    )


@router.post("/bookings", status_code=201)
async def manual_booking(
    body: ManualBookingIn, _: CurrentAdmin, state: State, session: Session, bookings: AdminBookings
) -> AdminBookingOut:
    clients = ClientAdmin(session, state.clock)
    if body.client_id is not None:
        client = await session.get(Client, body.client_id)
        if client is None:
            raise NotFoundError("Client not found")
    elif body.client_phone.strip() or body.client_name.strip():
        client = await clients.find_or_create(body.client_name, body.client_phone)
    else:
        raise PolicyError("Add a client name or phone")
    booking = await bookings.create(
        client,
        BookingRequest(
            service_id=body.service_id,
            master_id=body.master_id,
            starts_at=body.starts_at,
            payment_method=PaymentMethod.ON_SITE,
            source=BookingSource.ADMIN,
            comment=body.comment,
        ),
        strict=False,
    )
    business = await load_business(session)
    return admin_booking_out(booking, business, state.clock.now(), state.settings.demo_mode)


@router.post("/bookings/{booking_id}/status")
async def change_status(
    booking_id: int,
    body: StatusIn,
    _: CurrentAdmin,
    state: State,
    session: Session,
    bookings: AdminBookings,
) -> AdminBookingOut:
    booking = await bookings.get(booking_id)
    match body.action:
        case "complete":
            await bookings.complete(booking)
        case "no_show":
            await bookings.mark_no_show(booking)
        case _:
            await bookings.cancel(booking, by_client=False, reason=body.reason or "shop")
    business = await load_business(session)
    return admin_booking_out(
        await bookings.get(booking_id), business, state.clock.now(), state.settings.demo_mode
    )


@router.post("/bookings/{booking_id}/reschedule")
async def reschedule(
    booking_id: int,
    body: AdminRescheduleIn,
    _: CurrentAdmin,
    state: State,
    session: Session,
    bookings: AdminBookings,
) -> AdminBookingOut:
    booking = await bookings.get(booking_id)
    moved = await bookings.reschedule(
        booking, body.starts_at, master_id=body.master_id, by_client=False
    )
    business = await load_business(session)
    return admin_booking_out(moved, business, state.clock.now(), state.settings.demo_mode)
