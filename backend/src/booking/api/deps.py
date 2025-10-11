from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from booking.api.state import AppState
from booking.infra.db.models import AdminUser, Client
from booking.services.booking import BookingService
from booking.services.errors import AuthError
from booking.services.payments import PaymentService

ADMIN_COOKIE = "bb_admin"


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.booking
    return state


State = Annotated[AppState, Depends(get_state)]


async def get_session(state: State) -> AsyncIterator[AsyncSession]:
    # One transaction per request, committed before the response goes out.
    async with state.sessions() as session, session.begin():
        yield session


Session = Annotated[AsyncSession, Depends(get_session, scope="function")]


def get_payments(state: State, session: Session) -> PaymentService:
    return PaymentService(session, state.clock, state.settings, state.gateway, state.card_refunder)


Payments = Annotated[PaymentService, Depends(get_payments)]


def get_bookings(state: State, session: Session, payments: Payments) -> BookingService:
    return BookingService(session, state.clock, payments)


Bookings = Annotated[BookingService, Depends(get_bookings)]


def get_admin_bookings(state: State, session: Session, payments: Payments) -> BookingService:
    return BookingService(
        session, state.clock, payments, notify_clients=not state.settings.demo_mode
    )


AdminBookings = Annotated[BookingService, Depends(get_admin_bookings)]


async def current_client(
    state: State, session: Session, authorization: Annotated[str | None, Header()] = None
) -> Client:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Missing token")
    subject = state.tokens.verify(authorization[7:], "client")
    client = await session.get(Client, subject.id)
    if client is None:
        raise AuthError("Unknown client")
    return client


CurrentClient = Annotated[Client, Depends(current_client)]


async def current_admin(request: Request, state: State, session: Session) -> AdminUser:
    token = request.cookies.get(ADMIN_COOKIE)
    if not token:
        raise AuthError("Not signed in")
    subject = state.tokens.verify(token, "admin")
    admin = await session.get(AdminUser, subject.id)
    if admin is None:
        raise AuthError("Unknown admin")
    return admin


CurrentAdmin = Annotated[AdminUser, Depends(current_admin)]
