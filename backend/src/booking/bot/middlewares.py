from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery, TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from booking.bot.context import BotContext, BotDeps
from booking.services.business import load_business
from booking.services.clients import ClientService, TelegramProfile

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


def _referral(event: TelegramObject) -> str | None:
    if isinstance(event, Message) and event.text and event.text.startswith("/start ref_"):
        return event.text.split("ref_", 1)[1].strip()[:16] or None
    return None


def _user(event: TelegramObject) -> User | None:
    if isinstance(event, Message | CallbackQuery | PreCheckoutQuery):
        return event.from_user
    return None


class ContextMiddleware(BaseMiddleware):
    """Opens a transaction per update and resolves the client who sent it."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], deps: BotDeps) -> None:
        self.sessions = sessions
        self.deps = deps

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = _user(event)
        if user is None or user.is_bot:
            return await handler(event, data)
        bot: Bot = data["bot"]
        async with self.sessions() as session, session.begin():
            client, created = await ClientService(session, self.deps.clock).from_telegram(
                TelegramProfile(
                    id=user.id,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    username=user.username,
                    language_code=user.language_code,
                ),
                referral_code=_referral(event),
            )
            ctx = BotContext(
                session=session,
                deps=self.deps,
                bot=bot,
                business=await load_business(session),
                client=client,
            )
            ctx.extra["created"] = created
            data["ctx"] = ctx
            return await handler(event, data)
