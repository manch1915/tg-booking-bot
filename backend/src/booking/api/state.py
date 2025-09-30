from dataclasses import dataclass

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from booking.config import Settings
from booking.services.auth import TokenIssuer
from booking.services.clock import Clock
from booking.services.payments import CardRefunder, InvoiceGateway


@dataclass
class AppState:
    settings: Settings
    engine: AsyncEngine
    sessions: async_sessionmaker[AsyncSession]
    tokens: TokenIssuer
    clock: Clock
    bot: Bot | None = None
    gateway: InvoiceGateway | None = None
    card_refunder: CardRefunder | None = None
