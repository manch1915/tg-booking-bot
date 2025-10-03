from urllib.parse import quote, quote_plus

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from booking.bot.callbacks import MenuCb
from booking.bot.context import BotContext
from booking.bot.ui import menu_button, show
from booking.domain.enums import Language
from booking.infra.db.models import Master

router = Router(name="menu")


def menu_markup(ctx: BotContext) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if ctx.app_url:
        kb.button(text=ctx.t("menu.open_app"), web_app=WebAppInfo(url=ctx.app_url))
    kb.button(text=ctx.t("menu.book"), callback_data=MenuCb(action="book"))
    kb.button(text=ctx.t("menu.my_bookings"), callback_data=MenuCb(action="bookings"))
    kb.button(text=ctx.t("menu.bonuses"), callback_data=MenuCb(action="bonuses"))
    kb.button(text=ctx.t("menu.contacts"), callback_data=MenuCb(action="contacts"))
    kb.button(text=ctx.t("menu.language"), callback_data=MenuCb(action="lang"))
    kb.adjust(*([1] if ctx.app_url else []), 1, 2, 2)
    return kb.as_markup()


def welcome_text(ctx: BotContext) -> str:
    tagline = ctx.business.tagline_ru if ctx.lang is Language.RU else ctx.business.tagline_en
    return ctx.t("menu.welcome", name=ctx.business.name, tagline=tagline)


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("master_")))
async def link_master(message: Message, command: CommandObject, ctx: BotContext) -> None:
    token = (command.args or "").removeprefix("master_")
    master = await ctx.session.scalar(select(Master).where(Master.link_token == token))
    if master is None or message.from_user is None:
        await message.answer(ctx.t("master.bad_link"))
        return
    master.telegram_id = message.from_user.id
    await message.answer(ctx.t("master.linked", name=master.name))


@router.message(CommandStart())
async def start(message: Message, ctx: BotContext) -> None:
    await message.answer(welcome_text(ctx), reply_markup=menu_markup(ctx))


@router.message(Command("menu"))
async def menu_command(message: Message, ctx: BotContext) -> None:
    await message.answer(
        ctx.t("menu.welcome_back", name=ctx.client.name), reply_markup=menu_markup(ctx)
    )


@router.callback_query(MenuCb.filter(F.action == "home"))
async def home(call: CallbackQuery, ctx: BotContext) -> None:
    await show(call, welcome_text(ctx), menu_markup(ctx))


@router.callback_query(MenuCb.filter(F.action == "lang"))
async def switch_language(call: CallbackQuery, ctx: BotContext) -> None:
    ctx.client.language = Language.EN if ctx.lang is Language.RU else Language.RU
    await call.answer(ctx.t("lang.switched"))
    await show(call, welcome_text(ctx), menu_markup(ctx))


@router.callback_query(MenuCb.filter(F.action == "contacts"))
async def contacts(call: CallbackQuery, ctx: BotContext) -> None:
    business = ctx.business
    maps = f"https://maps.google.com/?q={quote_plus(business.name + ' ' + business.address)}"
    kb = InlineKeyboardBuilder()
    kb.button(text=ctx.t("contacts.map"), url=maps)
    kb.row(menu_button(ctx))
    text = ctx.t(
        "contacts.text", name=business.name, address=business.address, phone=business.phone
    )
    await show(call, text, kb.as_markup())


@router.callback_query(MenuCb.filter(F.action == "bonuses"))
async def bonuses(call: CallbackQuery, ctx: BotContext) -> None:
    business = ctx.business
    stats = await ctx.clients.stats(ctx.client)
    link = f"https://t.me/{ctx.settings.bot_username}?start=ref_{ctx.client.referral_code}"
    text = ctx.t(
        "bonuses.info",
        balance=ctx.money(ctx.client.bonus_balance),
        cashback=business.cashback_percent,
        share=business.max_bonus_share_percent,
        referral=ctx.money(business.referral_bonus),
        link=link,
        invited=stats["invited"],
    )
    # quote, not quote_plus: Telegram's share page does not turn "+" back into spaces.
    share_text = quote(ctx.t("bonuses.share_text", name=business.name))
    kb = InlineKeyboardBuilder()
    kb.button(
        text=ctx.t("bonuses.share"),
        url=f"https://t.me/share/url?url={quote(link)}&text={share_text}",
    )
    kb.row(menu_button(ctx))
    await show(call, text, kb.as_markup())
