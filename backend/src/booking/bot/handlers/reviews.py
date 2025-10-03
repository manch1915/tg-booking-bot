from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, LabeledPrice, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select

from booking.bot.callbacks import MenuCb, ReviewCb, TipCb
from booking.bot.context import BotContext
from booking.bot.ui import menu_button, show
from booking.domain.enums import ACTIVE_STATUSES, Language
from booking.i18n import fmt_date, fmt_time, t
from booking.infra.db.models import Booking, Master
from booking.services.errors import DomainError, NotFoundError
from booking.services.reviews import ReviewService

router = Router(name="reviews")

TIP_OPTIONS = (50, 100, 250)


class ReviewStates(StatesGroup):
    comment = State()


@router.callback_query(ReviewCb.filter())
async def rate(
    call: CallbackQuery, callback_data: ReviewCb, ctx: BotContext, state: FSMContext
) -> None:
    try:
        booking = await ctx.bookings.get_for_client(callback_data.booking_id, ctx.client.id)
        await ReviewService(ctx.session, ctx.deps.clock).leave(booking, callback_data.rating)
    except NotFoundError:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    except DomainError:
        await call.answer(ctx.t("review.already"), show_alert=True)
        return
    await state.set_state(ReviewStates.comment)
    await state.set_data({"booking_id": booking.id, "rating": callback_data.rating})
    kb = InlineKeyboardBuilder()
    kb.button(text=ctx.t("review.skip"), callback_data=MenuCb(action="review_skip"))
    stars = "★" * callback_data.rating + "☆" * (5 - callback_data.rating)
    await show(call, f"{stars}\n\n{ctx.t('review.ask_comment')}", kb.as_markup())


@router.message(ReviewStates.comment, F.text)
async def comment(message: Message, ctx: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    booking = await ctx.bookings.get_for_client(data["booking_id"], ctx.client.id)
    await ReviewService(ctx.session, ctx.deps.clock).leave(
        booking, data["rating"], message.text or ""
    )
    await _thank(message, ctx, booking, data["rating"])


@router.callback_query(MenuCb.filter(F.action == "review_skip"))
async def skip(call: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    await call.answer()
    if not data or not isinstance(call.message, Message):
        return
    booking = await ctx.bookings.get_for_client(data["booking_id"], ctx.client.id)
    await call.message.edit_reply_markup(reply_markup=None)
    await _thank(call.message, ctx, booking, data["rating"])


async def _thank(message: Message, ctx: BotContext, booking: Booking, rating: int) -> None:
    kb = InlineKeyboardBuilder()
    text = ctx.t("review.thanks")
    if rating >= 4 and ctx.business.stars_enabled:
        text += "\n" + ctx.t("review.tip_offer")
        for amount in TIP_OPTIONS:
            kb.button(
                text=ctx.t("review.tip_amount", amount=amount),
                callback_data=TipCb(booking_id=booking.id, amount=amount),
            )
        kb.adjust(len(TIP_OPTIONS))
    kb.row(menu_button(ctx))
    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(TipCb.filter())
async def tip(call: CallbackQuery, callback_data: TipCb, ctx: BotContext, bot: Bot) -> None:
    if callback_data.amount not in TIP_OPTIONS or ctx.client.telegram_id is None:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    booking = await ctx.bookings.get_for_client(callback_data.booking_id, ctx.client.id)
    payment = ctx.payments.create_tip(booking, callback_data.amount)
    await ctx.session.flush()
    await call.answer()
    master = ctx.master_name(booking.master)
    await bot.send_invoice(
        chat_id=ctx.client.telegram_id,
        title=ctx.t("invoice.tip_title"),
        description=ctx.t("invoice.tip_description", master=master),
        payload=payment.payload,
        currency="XTR",
        prices=[LabeledPrice(label=ctx.t("invoice.tip_title"), amount=payment.amount)],
    )


@router.message(Command("today"))
async def master_today(message: Message, ctx: BotContext) -> None:
    if message.from_user is None:
        return
    master = await ctx.session.scalar(
        select(Master).where(Master.telegram_id == message.from_user.id)
    )
    if master is None:
        return
    now = ctx.deps.clock.now().astimezone(ctx.tz)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rows = await ctx.session.scalars(
        select(Booking)
        .where(
            Booking.master_id == master.id,
            Booking.status.in_(ACTIVE_STATUSES),
            Booking.starts_at >= start,
            Booking.starts_at < start.replace(hour=23, minute=59),
        )
        .order_by(Booking.starts_at)
    )
    bookings = list(rows)
    lang = Language.RU
    if not bookings:
        await message.answer(t(lang, "master.today_empty"))
        return
    lines = [t(lang, "master.today_title", date=fmt_date(now.date(), lang))]
    for booking in bookings:
        await ctx.session.refresh(booking, ["client", "service"])
        lines.append(
            t(
                lang,
                "master.today_line",
                time=fmt_time(booking.starts_at, ctx.tz),
                service=booking.service.name_ru,
                client=booking.client.name,
            )
        )
    await message.answer("\n".join(lines))
