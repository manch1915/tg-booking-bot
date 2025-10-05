import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from booking.api import errors
from booking.api.routers import miniapp
from booking.api.routers.admin import auth as admin_auth
from booking.api.routers.admin import bookings as admin_bookings
from booking.api.routers.admin import catalog as admin_catalog
from booking.api.routers.admin import clients as admin_clients
from booking.api.routers.admin import reports as admin_reports
from booking.api.state import AppState
from booking.config import Settings, get_settings
from booking.infra.db.session import make_engine, make_sessionmaker
from booking.infra.payments.stripe import StripeRefunder
from booking.infra.telegram.gateway import AiogramInvoiceGateway
from booking.services.auth import TokenIssuer
from booking.services.clock import Clock, SystemClock

log = logging.getLogger(__name__)


def build_state(settings: Settings, clock: Clock | None = None) -> AppState:
    engine = make_engine(settings.database_url)
    state = AppState(
        settings=settings,
        engine=engine,
        sessions=make_sessionmaker(engine),
        tokens=TokenIssuer(settings.jwt_secret.get_secret_value(), settings.jwt_ttl_minutes),
        clock=clock or SystemClock(),
    )
    if settings.bot_token is not None:
        state.bot = Bot(
            settings.bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        state.gateway = AiogramInvoiceGateway(state.bot)
    if settings.stripe_secret_key is not None:
        state.card_refunder = StripeRefunder(settings.stripe_secret_key.get_secret_value())
    return state


def create_app(settings: Settings | None = None, state: AppState | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.booking = state or build_state(settings)
        yield
        current: AppState = app.state.booking
        if current.bot is not None:
            await current.bot.session.close()
        await current.engine.dispose()

    app = FastAPI(
        title="Brass & Blade booking API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    errors.install(app)
    app.include_router(miniapp.router)
    for module in (admin_auth, admin_bookings, admin_catalog, admin_clients, admin_reports):
        app.include_router(module.router)

    @app.get("/api/health", tags=["service"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
