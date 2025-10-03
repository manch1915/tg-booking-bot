from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from zoneinfo import ZoneInfo

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession

from booking.config import Settings
from booking.domain.enums import Language
from booking.i18n import fmt_datetime, fmt_money, t
from booking.infra.db.models import Business, Client, Master, Service
from booking.services.booking import BookingService
from booking.services.business import business_tz
from booking.services.clients import ClientService
from booking.services.clock import Clock
from booking.services.payments import CardRefunder, InvoiceGateway, PaymentService


@dataclass
class BotDeps:
    """Long-lived things the dispatcher hands to every update."""

    settings: Settings
    clock: Clock
    gateway: InvoiceGateway | None = None
    card_refunder: CardRefunder | None = None


@dataclass
class BotContext:
    """Everything a handler needs for one update, inside one DB transaction."""

    session: AsyncSession
    deps: BotDeps
    bot: Bot
    business: Business
    client: Client
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def lang(self) -> Language:
        return self.client.language

    @property
    def is_ru(self) -> bool:
        return self.client.language is Language.RU

    @property
    def tz(self) -> ZoneInfo:
        return business_tz(self.business)

    @property
    def settings(self) -> Settings:
        return self.deps.settings

    @cached_property
    def payments(self) -> PaymentService:
        return PaymentService(
            self.session,
            self.deps.clock,
            self.deps.settings,
            self.deps.gateway,
            self.deps.card_refunder,
        )

    @cached_property
    def bookings(self) -> BookingService:
        return BookingService(self.session, self.deps.clock, self.payments)

    @cached_property
    def clients(self) -> ClientService:
        return ClientService(self.session, self.deps.clock)

    def t(self, key: str, **params: object) -> str:
        return t(self.lang, key, **params)

    def money(self, amount: int, currency: str | None = None) -> str:
        return fmt_money(amount, currency or self.business.currency)

    def when(self, moment: datetime) -> str:
        return fmt_datetime(moment, self.tz, self.lang)

    def service_name(self, service: Service) -> str:
        return service.name_ru if self.lang is Language.RU else service.name_en

    def master_name(self, master: Master | None) -> str:
        if master is None:
            return self.t("common.any_master")
        return master.name if self.lang is Language.RU else (master.name_en or master.name)

    @property
    def app_url(self) -> str | None:
        # Telegram only opens Mini Apps over https.
        url = f"{self.settings.public_url.rstrip('/')}/app/"
        return url if url.startswith("https://") else None
