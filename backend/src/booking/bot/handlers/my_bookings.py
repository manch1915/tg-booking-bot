from datetime import UTC, datetime

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from booking.bot.callbacks import BookingCb, MenuCb, SlotCb
from booking.bot.context import BotContext
from booking.bot.handlers.booking import (
    after_booking_markup,
    confirmed_text,
    days_markup,
    send_deposit_invoice,
)
from booking.bot.ui import back_button, menu_button, show
from booking.domain.enums import ACTIVE_STATUSES, BookingStatus, PaymentStatus
from booking.domain.policies import change_policy
from booking.infra.db.models import Booking
from booking.services.errors import DomainError, NotFoundError, SlotUnavailableError

router = Router(name="my_bookings")


async def _own_booking(ctx: BotContext, booking_id: int) -> Booking | None:
    try:
        return await ctx.bookings.get_for_client(booking_id, ctx.client.id)
    except NotFoundError:
        return None


@router.callback_query(MenuCb.filter(F.action == "bookings"))
async def list_bookings(call: CallbackQuery, ctx: BotContext) -> None:
    now = ctx.deps.clock.now()
    upcoming = [
        b
        for b in await ctx.bookings.client_bookings(ctx.client.id)
        if b.status in ACTIVE_STATUSES and b.ends_at > now
    ]
    upcoming.sort(key=lambda b: b.starts_at)
    kb = InlineKeyboardBuilder()
    for booking in upcoming:
        kb.button(
            text=ctx.t(
                "bookings.line",
                when=ctx.when(booking.starts_at),
                service=ctx.service_name(booking.service),
            ),
            callback_data=BookingCb(id=booking.id, action="view"),
        )
    if not upcoming:
        kb.button(text=ctx.t("menu.book"), callback_data=MenuCb(action="book"))
    kb.adjust(1)
    kb.row(menu_button(ctx))
    text = ctx.t("bookings.upcoming") if upcoming else ctx.t("bookings.empty")
    await show(call, text, kb.as_markup())


async def _render_card(call: CallbackQuery, ctx: BotContext, booking: Booking) -> None:
    business = ctx.business
    policy = change_policy(
        starts_at=booking.starts_at,
        now=ctx.deps.clock.now(),
        window_hours=business.cancel_window_hours,
    )
    lines = [
        ctx.t(
            "bookings.card",
            service=ctx.service_name(booking.service),
            master=ctx.master_name(booking.master),
            when=ctx.when(booking.starts_at),
            price=ctx.money(booking.price),
            status=ctx.t(f"bookings.status.{booking.status.value}"),
        )
    ]
    paid = next((p for p in booking.payments if p.status is PaymentStatus.PAID), None)
    if paid is not None:
        lines.append(ctx.t("bookings.deposit_paid", amount=ctx.money(paid.amount, paid.currency)))
    if booking.status in ACTIVE_STATUSES:
        key = "bookings.deadline" if policy.refund_deposit else "bookings.deadline_passed"
        lines.append(ctx.t(key, deadline=ctx.when(policy.deadline)))

    kb = InlineKeyboardBuilder()
    if booking.status is BookingStatus.PENDING_PAYMENT:
        kb.button(text=ctx.t("bookings.pay"), callback_data=BookingCb(id=booking.id, action="pay"))
    if booking.status is BookingStatus.CONFIRMED and policy.can_reschedule:
        kb.button(
            text=ctx.t("bookings.reschedule"), callback_data=BookingCb(id=booking.id, action="move")
        )
    if booking.status in ACTIVE_STATUSES and policy.can_cancel:
        kb.button(
            text=ctx.t("bookings.cancel"), callback_data=BookingCb(id=booking.id, action="cancel")
        )
    kb.adjust(2)
    kb.row(back_button(ctx, MenuCb(action="bookings").pack()))
    await show(call, "\n".join(lines), kb.as_markup())


@router.callback_query(BookingCb.filter(F.action == "view"))
async def view(call: CallbackQuery, callback_data: BookingCb, ctx: BotContext) -> None:
    booking = await _own_booking(ctx, callback_data.id)
    if booking is None:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    await _render_card(call, ctx, booking)


@router.callback_query(BookingCb.filter(F.action == "keep"))
async def keep(call: CallbackQuery, ctx: BotContext) -> None:
    await call.answer(ctx.t("bookings.kept"))
    if isinstance(call.message, Message):
        await call.message.edit_reply_markup(reply_markup=None)


@router.callback_query(BookingCb.filter(F.action == "cancel"))
async def ask_cancel(call: CallbackQuery, callback_data: BookingCb, ctx: BotContext) -> None:
    booking = await _own_booking(ctx, callback_data.id)
    if booking is None or booking.status not in ACTIVE_STATUSES:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    policy = change_policy(
        starts_at=booking.starts_at,
        now=ctx.deps.clock.now(),
        window_hours=ctx.business.cancel_window_hours,
    )
    paid = next((p for p in booking.payments if p.status is PaymentStatus.PAID), None)
    if paid is not None and not policy.refund_deposit:
        text = ctx.t(
            "bookings.cancel_confirm_late",
            hours=ctx.business.cancel_window_hours,
            amount=ctx.money(paid.amount, paid.currency),
        )
    else:
        text = ctx.t("bookings.cancel_confirm", when=ctx.when(booking.starts_at))
    kb = InlineKeyboardBuilder()
    kb.button(
        text=ctx.t("bookings.cancel_yes"),
        callback_data=BookingCb(id=booking.id, action="cancel_yes"),
    )
    kb.button(
        text=ctx.t("bookings.cancel_no"), callback_data=BookingCb(id=booking.id, action="view")
    )
    kb.adjust(2)
    await show(call, text, kb.as_markup())


@router.callback_query(BookingCb.filter(F.action == "cancel_yes"))
async def do_cancel(call: CallbackQuery, callback_data: BookingCb, ctx: BotContext) -> None:
    booking = await _own_booking(ctx, callback_data.id)
    if booking is None:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    try:
        result = await ctx.bookings.cancel(booking, by_client=True, reason="client")
    except DomainError:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    key = {
        PaymentStatus.REFUNDED: "bookings.cancelled_refund",
        PaymentStatus.REFUND_PENDING: "bookings.cancelled_refund_pending",
    }.get(result.refund or PaymentStatus.CANCELLED, "bookings.cancelled")
    kb = InlineKeyboardBuilder()
    kb.button(text=ctx.t("menu.book"), callback_data=MenuCb(action="book"))
    kb.row(menu_button(ctx))
    await show(call, ctx.t(key), kb.as_markup())


@router.callback_query(BookingCb.filter(F.action == "move"))
async def choose_new_day(call: CallbackQuery, callback_data: BookingCb, ctx: BotContext) -> None:
    booking = await _own_booking(ctx, callback_data.id)
    if booking is None or booking.status is not BookingStatus.CONFIRMED:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    policy = change_policy(
        starts_at=booking.starts_at,
        now=ctx.deps.clock.now(),
        window_hours=ctx.business.cancel_window_hours,
    )
    if not policy.can_reschedule:
        await call.answer(
            ctx.t(
                "bookings.too_late_reschedule",
                hours=ctx.business.cancel_window_hours,
                phone=ctx.business.phone,
            ),
            show_alert=True,
        )
        return
    markup = await days_markup(
        ctx,
        booking.service_id,
        booking.master_id,
        booking.id,
        BookingCb(id=booking.id, action="view").pack(),
    )
    await show(call, ctx.t("bookings.choose_new_day"), markup)


@router.callback_query(SlotCb.filter(F.booking_id > 0))
async def do_reschedule(call: CallbackQuery, callback_data: SlotCb, ctx: BotContext) -> None:
    booking = await _own_booking(ctx, callback_data.booking_id)
    if booking is None:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    try:
        moved = await ctx.bookings.reschedule(
            booking,
            datetime.fromtimestamp(callback_data.ts, tz=UTC),
            master_id=callback_data.master_id or None,
            by_client=True,
        )
    except SlotUnavailableError:
        await call.answer(ctx.t("book.slot_taken"), show_alert=True)
        return
    except DomainError:
        await call.answer(ctx.t("errors.generic"), show_alert=True)
        return
    await show(
        call,
        ctx.t("bookings.rescheduled", when=ctx.when(moved.starts_at)),
        after_booking_markup(ctx),
    )


@router.callback_query(BookingCb.filter(F.action == "pay"))
async def pay(call: CallbackQuery, callback_data: BookingCb, ctx: BotContext, bot: Bot) -> None:
    booking = await _own_booking(ctx, callback_data.id)
    pending = (
        next((p for p in booking.payments if p.status is PaymentStatus.PENDING), None)
        if booking
        else None
    )
    if booking is None or pending is None or booking.status is not BookingStatus.PENDING_PAYMENT:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    await call.answer()
    await send_deposit_invoice(ctx, bot, booking, pending)


@router.callback_query(BookingCb.filter(F.action == "demopay"))
async def demo_pay(call: CallbackQuery, callback_data: BookingCb, ctx: BotContext) -> None:
    booking = await _own_booking(ctx, callback_data.id)
    pending = (
        next((p for p in booking.payments if p.status is PaymentStatus.PENDING), None)
        if booking
        else None
    )
    if booking is None or pending is None:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    try:
        outcome = await ctx.bookings.complete_demo_payment(pending.id, ctx.client)
    except DomainError:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    text = (
        confirmed_text(ctx, outcome.booking)
        if outcome.confirmed
        else ctx.t("book.payment_late_refunded")
    )
    await show(call, text, after_booking_markup(ctx))
