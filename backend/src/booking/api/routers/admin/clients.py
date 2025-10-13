from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from booking.api.admin_schemas import (
    AudienceIn,
    AudienceOut,
    BonusAdjustIn,
    BonusTxAdmin,
    BroadcastIn,
    BroadcastOut,
    ClientDetail,
    ClientPatch,
    ClientsPage,
    ReviewRow,
    WaitlistRow,
)
from booking.api.deps import CurrentAdmin, Session, State
from booking.api.routers.admin.common import (
    admin_booking_out,
    client_ref,
    client_row,
    is_masked,
)
from booking.api.schemas import Localized
from booking.domain.enums import BookingStatus, Segment
from booking.infra.db.models import (
    BonusTransaction,
    Booking,
    Broadcast,
    Client,
    Review,
    WaitlistEntry,
)
from booking.services.admin import BroadcastService, ClientAdmin
from booking.services.booking import booking_options
from booking.services.business import load_business
from booking.services.errors import NotFoundError

router = APIRouter(prefix="/api/admin", tags=["admin clients"])


@router.get("/clients")
async def clients(
    _: CurrentAdmin,
    state: State,
    session: Session,
    q: str = "",
    segment: Segment = Segment.ALL,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=10, le=100)] = 30,
) -> ClientsPage:
    rows, total = await ClientAdmin(session, state.clock).search(
        q=q, segment=segment, limit=per_page, offset=(page - 1) * per_page
    )
    return ClientsPage(
        items=[client_row(*row, mask=state.settings.demo_mode) for row in rows], total=total
    )


async def _client_detail(session: Session, state: State, client: Client) -> ClientDetail:
    business = await load_business(session)
    bookings = list(
        await session.scalars(
            select(Booking)
            .where(Booking.client_id == client.id)
            .options(*booking_options())
            .order_by(Booking.starts_at.desc())
            .limit(50)
        )
    )
    completed = [b for b in bookings if b.status is BookingStatus.COMPLETED]
    bonuses = await session.scalars(
        select(BonusTransaction)
        .where(BonusTransaction.client_id == client.id)
        .order_by(BonusTransaction.created_at.desc())
        .limit(30)
    )
    invited = await session.scalar(
        select(func.count(Client.id)).where(Client.referred_by_id == client.id)
    )
    return ClientDetail(
        client=client_row(
            client,
            len(completed),
            completed[0].starts_at if completed else None,
            sum(b.price - b.bonus_spent for b in completed),
            mask=state.settings.demo_mode,
        ),
        notes="" if state.settings.demo_mode and client.telegram_id else client.notes,
        referral_code=client.referral_code,
        invited=int(invited or 0),
        bookings=[
            admin_booking_out(b, business, state.clock.now(), state.settings.demo_mode)
            for b in bookings
        ],
        bonuses=[
            BonusTxAdmin(
                kind=t.kind.value, amount=t.amount, comment=t.comment, created_at=t.created_at
            )
            for t in bonuses
        ],
    )


async def _client(session: Session, client_id: int) -> Client:
    client = await session.get(Client, client_id)
    if client is None:
        raise NotFoundError("Client not found")
    return client


@router.get("/clients/{client_id}")
async def client_detail(
    client_id: int, _: CurrentAdmin, state: State, session: Session
) -> ClientDetail:
    return await _client_detail(session, state, await _client(session, client_id))


@router.patch("/clients/{client_id}")
async def update_client(
    client_id: int, body: ClientPatch, _: CurrentAdmin, state: State, session: Session
) -> ClientDetail:
    client = await _client(session, client_id)
    for key, value in body.model_dump(exclude_none=True).items():
        setattr(client, key, value.strip() if isinstance(value, str) else value)
    await session.flush()
    return await _client_detail(session, state, client)


@router.post("/clients/{client_id}/bonus")
async def adjust_bonus(
    client_id: int, body: BonusAdjustIn, admin: CurrentAdmin, state: State, session: Session
) -> ClientDetail:
    client = await _client(session, client_id)
    await ClientAdmin(session, state.clock).adjust_bonus(
        client, body.amount, body.comment or admin.name
    )
    await session.flush()
    return await _client_detail(session, state, client)


@router.post("/broadcasts/preview")
async def preview(body: AudienceIn, _: CurrentAdmin, state: State, session: Session) -> AudienceOut:
    total, reachable = await BroadcastService(session, state.clock, state.settings).preview(
        body.segment, body.master_id
    )
    return AudienceOut(total=total, reachable=reachable)


def _broadcast_out(broadcast: Broadcast, delivered: int) -> BroadcastOut:
    return BroadcastOut(
        id=broadcast.id,
        segment=broadcast.segment,
        segment_master_id=broadcast.segment_master_id,
        text_ru=broadcast.text_ru,
        text_en=broadcast.text_en,
        recipients=broadcast.recipients,
        delivered=delivered,
        created_by=broadcast.created_by,
        created_at=broadcast.created_at,
    )


@router.get("/broadcasts")
async def broadcasts(_: CurrentAdmin, state: State, session: Session) -> list[BroadcastOut]:
    history = await BroadcastService(session, state.clock, state.settings).history()
    return [_broadcast_out(b, delivered) for b, delivered in history]


@router.post("/broadcasts", status_code=201)
async def send_broadcast(
    body: BroadcastIn, admin: CurrentAdmin, state: State, session: Session
) -> BroadcastOut:
    broadcast = await BroadcastService(session, state.clock, state.settings).send(
        body.segment, body.master_id, body.text_ru, body.text_en, admin.name
    )
    return _broadcast_out(broadcast, 0)


@router.get("/reviews")
async def reviews(_: CurrentAdmin, state: State, session: Session) -> list[ReviewRow]:
    rows = await session.scalars(
        select(Review)
        .options(
            selectinload(Review.client),
            selectinload(Review.booking).selectinload(Booking.service),
        )
        .order_by(Review.created_at.desc())
        .limit(100)
    )
    return [
        ReviewRow(
            id=r.id,
            rating=r.rating,
            comment="" if is_masked(r.client, state.settings.demo_mode) else r.comment,
            client=client_ref(r.client, state.settings.demo_mode).name,
            master_id=r.master_id,
            service=Localized(ru=r.booking.service.name_ru, en=r.booking.service.name_en),
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/waitlist")
async def waitlist(_: CurrentAdmin, state: State, session: Session) -> list[WaitlistRow]:
    rows = await session.scalars(
        select(WaitlistEntry)
        .options(selectinload(WaitlistEntry.client), selectinload(WaitlistEntry.service))
        .order_by(WaitlistEntry.day, WaitlistEntry.created_at)
        .limit(100)
    )
    return [
        WaitlistRow(
            id=w.id,
            client=client_ref(w.client, state.settings.demo_mode),
            service=Localized(ru=w.service.name_ru, en=w.service.name_en),
            master_id=w.master_id,
            day=w.day,
            status=w.status.value,
            created_at=w.created_at,
        )
        for w in rows
    ]
