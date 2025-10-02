import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from booking.services.messaging import Button, DeliveryError, OutgoingMessage

log = logging.getLogger(__name__)

# Telegram allows about 30 messages per second for a bot; stay below it.
SEND_INTERVAL = 1 / 25


def to_markup(rows: list[list[Button]]) -> InlineKeyboardMarkup | None:
    if not rows:
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=b.text,
                    callback_data=b.callback,
                    url=b.url,
                    web_app=WebAppInfo(url=b.web_app) if b.web_app else None,
                )
                for b in row
            ]
            for row in rows
        ]
    )


class TelegramMessenger:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(self, message: OutgoingMessage) -> None:
        try:
            await self.bot.send_message(
                chat_id=message.chat_id,
                text=message.text,
                reply_markup=to_markup(message.buttons),
                disable_web_page_preview=True,
            )
        except TelegramRetryAfter as exc:
            raise DeliveryError("flood", permanent=False, retry_after=exc.retry_after) from exc
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            raise DeliveryError(exc.message, permanent=True) from exc
        except TelegramNetworkError as exc:
            raise DeliveryError(str(exc), permanent=False) from exc
        await asyncio.sleep(SEND_INTERVAL)


class LogMessenger:
    """Used when no bot token is set: messages go to the log instead of Telegram."""

    async def send(self, message: OutgoingMessage) -> None:
        log.info("[to %s] %s", message.chat_id, message.text.replace("\n", " | "))
