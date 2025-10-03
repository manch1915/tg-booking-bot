from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from booking.bot.callbacks import MenuCb
from booking.bot.context import BotContext


async def show(
    target: CallbackQuery | Message, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Edit the message behind a button, or send a new one when editing is impossible."""
    if isinstance(target, Message):
        await target.answer(text, reply_markup=markup, disable_web_page_preview=True)
        return
    await target.answer()
    message = target.message
    if not isinstance(message, Message):
        return
    try:
        await message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
    except TelegramBadRequest as exc:
        if "not modified" in exc.message:
            return
        await message.answer(text, reply_markup=markup, disable_web_page_preview=True)


def menu_button(ctx: BotContext) -> InlineKeyboardButton:
    return InlineKeyboardButton(
        text=ctx.t("common.menu"), callback_data=MenuCb(action="home").pack()
    )


def back_button(ctx: BotContext, callback: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=ctx.t("common.back"), callback_data=callback)
