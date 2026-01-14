import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from booking.bot.context import BotDeps
from booking.bot.handlers import booking, menu, my_bookings, payments, reviews
from booking.bot.middlewares import ContextMiddleware
from booking.domain.enums import Language
from booking.i18n import t

log = logging.getLogger(__name__)


def build_dispatcher(
    sessions: async_sessionmaker[AsyncSession],
    deps: BotDeps,
    storage: BaseStorage | None = None,
) -> Dispatcher:
    dp = Dispatcher(storage=storage or MemoryStorage())
    middleware = ContextMiddleware(sessions, deps)
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    dp.pre_checkout_query.outer_middleware(middleware)
    # Order matters: payments and reviews catch specific updates before the generic menu.
    dp.include_routers(
        payments.router,
        reviews.router,
        my_bookings.router,
        booking.router,
        menu.router,
    )
    return dp


async def _sync_profile(bot: Bot, lang: Language, code: str | None) -> None:
    name = t(lang, "profile.name")
    if (await bot.get_my_name(language_code=code)).name != name:
        await bot.set_my_name(name=name, language_code=code)
    short = t(lang, "profile.short")
    current_short = await bot.get_my_short_description(language_code=code)
    if current_short.short_description != short:
        await bot.set_my_short_description(short_description=short, language_code=code)
    description = t(lang, "profile.description")
    if (await bot.get_my_description(language_code=code)).description != description:
        await bot.set_my_description(description=description, language_code=code)


async def configure_bot(bot: Bot, public_url: str) -> None:
    for lang in Language:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description=t(lang, "menu.book")),
                BotCommand(command="menu", description=t(lang, "common.menu")),
                BotCommand(command="paysupport", description=t(lang, "menu.contacts")),
            ],
            language_code=lang.value,
        )
    # The profile without a language code is what users of any other language see.
    profiles = [(Language.EN, None), *((lang, lang.value) for lang in Language)]
    for lang, code in profiles:
        try:
            await _sync_profile(bot, lang, code)
        except TelegramAPIError as exc:
            # setMyName is heavily rate-limited; a stale name must not stop the bot.
            log.warning("Could not update the bot profile for %s: %s", code or "default", exc)
    app_url = f"{public_url.rstrip('/')}/app/"
    if app_url.startswith("https://"):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text=t(Language.RU, "menu.app_button"), web_app=WebAppInfo(url=app_url)
            )
        )
