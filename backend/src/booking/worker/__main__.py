import asyncio
import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from booking.config import get_settings
from booking.infra.db.session import make_engine, make_sessionmaker
from booking.infra.payments.stripe import StripeRefunder
from booking.infra.telegram.gateway import AiogramInvoiceGateway
from booking.infra.telegram.messenger import LogMessenger, TelegramMessenger
from booking.services.clock import SystemClock
from booking.services.messaging import Messenger
from booking.worker.jobs import Jobs

log = logging.getLogger("booking.worker")
TICK_SECONDS = 15


async def run() -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    bot = None
    messenger: Messenger = LogMessenger()
    if settings.bot_token is not None:
        bot = Bot(
            settings.bot_token.get_secret_value(),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        messenger = TelegramMessenger(bot)
    jobs = Jobs(
        make_sessionmaker(engine),
        settings,
        SystemClock(),
        messenger,
        gateway=AiogramInvoiceGateway(bot) if bot else None,
        card_refunder=StripeRefunder(settings.stripe_secret_key.get_secret_value())
        if settings.stripe_secret_key
        else None,
    )
    log.info("Worker started")
    try:
        while True:
            await jobs.tick()
            await asyncio.sleep(TICK_SECONDS)
    finally:
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(level=get_settings().log_level)
    asyncio.run(run())


if __name__ == "__main__":
    main()
