import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage

from booking.bot.app import build_dispatcher, configure_bot
from booking.bot.context import BotDeps
from booking.config import get_settings
from booking.infra.db.session import make_engine, make_sessionmaker
from booking.infra.payments.stripe import StripeRefunder
from booking.infra.telegram.gateway import AiogramInvoiceGateway
from booking.services.clock import SystemClock

log = logging.getLogger("booking.bot")


async def run() -> None:
    settings = get_settings()
    if settings.bot_token is None:
        raise SystemExit("BOT_TOKEN is not set, the bot has nothing to do")
    bot = Bot(
        settings.bot_token.get_secret_value(),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    engine = make_engine(settings.database_url)
    deps = BotDeps(
        settings=settings,
        clock=SystemClock(),
        gateway=AiogramInvoiceGateway(bot),
        card_refunder=StripeRefunder(settings.stripe_secret_key.get_secret_value())
        if settings.stripe_secret_key
        else None,
    )
    storage = RedisStorage.from_url(settings.redis_url)
    dp = build_dispatcher(make_sessionmaker(engine), deps, storage)
    await configure_bot(bot, settings.public_url)
    log.info("Bot started")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await storage.close()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(run())


if __name__ == "__main__":
    main()
