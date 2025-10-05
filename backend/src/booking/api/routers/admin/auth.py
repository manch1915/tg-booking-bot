from fastapi import APIRouter, Response
from sqlalchemy import select

from booking.api.admin_schemas import AdminOut, LoginIn
from booking.api.deps import ADMIN_COOKIE, CurrentAdmin, Session, State
from booking.api.state import AppState
from booking.infra.db.models import AdminUser
from booking.services.auth import check_password
from booking.services.errors import AuthError, NotFoundError

router = APIRouter(prefix="/api/admin/auth", tags=["admin auth"])


def _admin_out(admin: AdminUser, state: AppState) -> AdminOut:
    demo = state.settings.demo_mode and admin.email == state.settings.demo_admin_email
    return AdminOut(id=admin.id, email=admin.email, name=admin.name, role=admin.role, demo=demo)


def _set_cookie(response: Response, state: AppState, admin: AdminUser) -> None:
    response.set_cookie(
        ADMIN_COOKIE,
        state.tokens.issue("admin", admin.id),
        max_age=state.settings.jwt_ttl_minutes * 60,
        httponly=True,
        samesite="lax",
        secure=state.settings.public_url.startswith("https://"),
        path="/api/admin",
    )


@router.post("/login")
async def login(body: LoginIn, response: Response, state: State, session: Session) -> AdminOut:
    admin = await session.scalar(select(AdminUser).where(AdminUser.email == body.email.lower()))
    if admin is None or not check_password(admin.password_hash, body.password):
        raise AuthError("Wrong email or password")
    _set_cookie(response, state, admin)
    return _admin_out(admin, state)


@router.post("/demo")
async def demo_login(response: Response, state: State, session: Session) -> AdminOut:
    if not state.settings.demo_mode:
        raise NotFoundError("Demo access is turned off")
    admin = await session.scalar(
        select(AdminUser).where(AdminUser.email == state.settings.demo_admin_email)
    )
    if admin is None:
        raise NotFoundError("Demo account is missing, run the seed")
    _set_cookie(response, state, admin)
    return _admin_out(admin, state)


@router.post("/logout", status_code=204)
async def logout(response: Response) -> None:
    response.delete_cookie(ADMIN_COOKIE, path="/api/admin")


@router.get("/me")
async def me(admin: CurrentAdmin, state: State) -> AdminOut:
    return _admin_out(admin, state)
