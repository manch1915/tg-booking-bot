"""Drives the real dispatcher with fake updates and records what the bot sends back."""

import itertools
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import (
    AnswerPreCheckoutQuery,
    EditMessageText,
    SendInvoice,
    SendMessage,
    TelegramMethod,
)
from aiogram.methods.base import TelegramType
from aiogram.types import (
    CallbackQuery,
    Chat,
    InlineKeyboardMarkup,
    Message,
    PreCheckoutQuery,
    SuccessfulPayment,
    Update,
    User,
)

_ids = itertools.count(1)


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def close(self) -> None:
        return None

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - signature of BaseSession
    ) -> TelegramType:
        self.calls.append(method)
        if isinstance(method, SendMessage | EditMessageText | SendInvoice):
            chat_id = int(getattr(method, "chat_id", None) or 1)
            text = getattr(method, "text", None) or getattr(method, "title", "")
            markup = (
                method.reply_markup
                if isinstance(method.reply_markup, InlineKeyboardMarkup)
                else None
            )
            return Message(  # type: ignore[return-value]
                message_id=next(_ids),
                date=datetime.now(UTC),
                chat=Chat(id=chat_id, type="private"),
                text=text,
                reply_markup=markup,
            )
        # Answers, markup edits and everything else just report success.
        return True  # type: ignore[return-value]

    def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        raise NotImplementedError


class TelegramUser:
    def __init__(self, dp: Dispatcher, bot: Bot, session: RecordingSession, user_id: int) -> None:
        self.dp = dp
        self.bot = bot
        self.session = session
        self.user = User(id=user_id, is_bot=False, first_name="Ruben", language_code="en")
        self.chat = Chat(id=user_id, type="private")

    def _message(self, **fields: Any) -> Message:
        return Message(
            message_id=next(_ids),
            date=datetime.now(UTC),
            chat=self.chat,
            from_user=self.user,
            **fields,
        )

    async def send(self, text: str) -> None:
        await self.dp.feed_update(
            self.bot, Update(update_id=next(_ids), message=self._message(text=text))
        )

    def last_markup(self) -> InlineKeyboardMarkup:
        for call in reversed(self.session.calls):
            markup = getattr(call, "reply_markup", None)
            if isinstance(markup, InlineKeyboardMarkup):
                return markup
        raise AssertionError("The bot has not sent any buttons yet")

    def last_text(self) -> str:
        for call in reversed(self.session.calls):
            if isinstance(call, SendMessage | EditMessageText) and call.text:
                return call.text
        raise AssertionError("No text sent")

    def buttons(self) -> list[str]:
        return [b.text for row in self.last_markup().inline_keyboard for b in row]

    async def click(self, contains: str = "", index: int | None = None) -> None:
        buttons = [b for row in self.last_markup().inline_keyboard for b in row if b.callback_data]
        if index is not None:
            button = buttons[index]
        else:
            button = next(b for b in buttons if contains in b.text)
        query = CallbackQuery(
            id=str(next(_ids)),
            from_user=self.user,
            chat_instance="test",
            data=button.callback_data,
            message=self._message(text="..."),
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), callback_query=query))

    def invoices(self) -> list[SendInvoice]:
        return [c for c in self.session.calls if isinstance(c, SendInvoice)]

    async def pay(self, invoice: SendInvoice) -> bool:
        query = PreCheckoutQuery(
            id=str(next(_ids)),
            from_user=self.user,
            currency=invoice.currency,
            total_amount=invoice.prices[0].amount,
            invoice_payload=invoice.payload,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(_ids), pre_checkout_query=query))
        answer = next(
            c for c in reversed(self.session.calls) if isinstance(c, AnswerPreCheckoutQuery)
        )
        if not answer.ok:
            return False
        paid = SuccessfulPayment(
            currency=invoice.currency,
            total_amount=invoice.prices[0].amount,
            invoice_payload=invoice.payload,
            telegram_payment_charge_id=f"tg_{next(_ids)}",
            provider_payment_charge_id="",
        )
        await self.dp.feed_update(
            self.bot, Update(update_id=next(_ids), message=self._message(successful_payment=paid))
        )
        return True
