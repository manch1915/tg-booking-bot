import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery

from booking.bot.context import BotContext
from booking.bot.handlers.booking import after_booking_markup, confirmed_text
from booking.domain.enums import PaymentPurpose

router = Router(name="payments")
log = logging.getLogger(__name__)


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, ctx: BotContext) -> None:
    # Telegram waits only 10 seconds for this answer, so it stays a quick DB check.
    reason = await ctx.payments.checkout_error(
        query.invoice_payload, query.currency, query.total_amount
    )
    if reason is None:
        await query.answer(ok=True)
        return
    log.info("Rejected checkout %s: %s", query.invoice_payload, reason)
    message = ctx.t("book.slot_taken") if reason == "hold_expired" else ctx.t("errors.generic")
    await query.answer(ok=False, error_message=message)


@router.message(F.successful_payment)
async def successful_payment(message: Message, ctx: BotContext) -> None:
    paid = message.successful_payment
    assert paid is not None
    payment = await ctx.payments.by_payload(paid.invoice_payload)

    if payment.purpose is PaymentPurpose.TIP:
        ctx.payments.mark_paid(
            payment,
            telegram_charge_id=paid.telegram_payment_charge_id,
            provider_charge_id=paid.provider_payment_charge_id,
        )
        booking = await ctx.bookings.get(payment.booking_id)
        await message.answer(ctx.t("review.tip_thanks", master=ctx.master_name(booking.master)))
        return

    outcome = await ctx.bookings.confirm_payment(
        paid.invoice_payload,
        telegram_charge_id=paid.telegram_payment_charge_id,
        provider_charge_id=paid.provider_payment_charge_id,
        notify_client=False,
    )
    if outcome.confirmed:
        await message.answer(
            confirmed_text(ctx, outcome.booking), reply_markup=after_booking_markup(ctx)
        )
    else:
        await message.answer(ctx.t("book.payment_late_refunded"))


@router.message(Command("paysupport"))
async def pay_support(message: Message, ctx: BotContext) -> None:
    # Telegram requires a /paysupport command for bots that accept payments.
    await message.answer(
        ctx.t(
            "contacts.text",
            name=ctx.business.name,
            address=ctx.business.address,
            phone=ctx.business.phone,
        )
    )
