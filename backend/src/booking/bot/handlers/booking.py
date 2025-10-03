from datetime import UTC, date, datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LabeledPrice
from aiogram.utils.keyboard import InlineKeyboardBuilder

from booking.bot.callbacks import (
    BookingCb,
    CategoryCb,
    ConfirmCb,
    DayCb,
    MasterCb,
    MenuCb,
    ServiceCb,
    SlotCb,
    WaitlistCb,
)
from booking.bot.context import BotContext
from booking.bot.ui import back_button, menu_button, show
from booking.domain.enums import (
    BookingSource,
    BookingStatus,
    PaymentMethod,
    PaymentProvider,
    PaymentStatus,
)
from booking.domain.policies import deposit_for, max_bonus_spend, stars_for
from booking.i18n import fmt_date, fmt_time
from booking.infra.db.models import Booking, Payment
from booking.services.availability import AvailabilityService
from booking.services.booking import BookingRequest
from booking.services.catalog import CatalogService
from booking.services.errors import DomainError, PolicyError, SlotUnavailableError
from booking.services.invoices import deposit_texts
from booking.services.waitlist import WaitlistService

router = Router(name="booking")


def _day(value: str) -> date:
    return datetime.strptime(value, "%Y%m%d").date()  # noqa: DTZ007 - a calendar date, no time


@router.callback_query(MenuCb.filter(F.action == "book"))
async def categories(call: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    await state.clear()
    kb = InlineKeyboardBuilder()
    for category in await CatalogService(ctx.session).categories():
        name = category.name_ru if ctx.is_ru else category.name_en
        kb.button(text=name, callback_data=CategoryCb(id=category.id))
    kb.adjust(2)
    kb.row(menu_button(ctx))
    await show(call, ctx.t("book.choose_category"), kb.as_markup())


@router.callback_query(CategoryCb.filter())
async def services(call: CallbackQuery, callback_data: CategoryCb, ctx: BotContext) -> None:
    catalog = CatalogService(ctx.session)
    category = next((c for c in await catalog.categories() if c.id == callback_data.id), None)
    if category is None:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    kb = InlineKeyboardBuilder()
    for service in category.services:
        if not service.is_active:
            continue
        prices = [link.price or service.price for link in service.masters]
        kb.button(
            text=ctx.t(
                "book.service_line",
                name=ctx.service_name(service),
                price=ctx.t(
                    "common.from_price", price=ctx.money(min(prices, default=service.price))
                ),
                duration=ctx.t("common.minutes", n=service.duration_minutes),
            ),
            callback_data=ServiceCb(id=service.id),
        )
    kb.adjust(1)
    kb.row(back_button(ctx, MenuCb(action="book").pack()))
    name = category.name_ru if ctx.is_ru else category.name_en
    await show(call, ctx.t("book.choose_service", category=name), kb.as_markup())


@router.callback_query(ServiceCb.filter())
async def masters(call: CallbackQuery, callback_data: ServiceCb, ctx: BotContext) -> None:
    catalog = CatalogService(ctx.session)
    service = await catalog.service(callback_data.id)
    offers = await catalog.offers(service.id)
    kb = InlineKeyboardBuilder()
    cheapest = ctx.t(
        "common.from_price", price=ctx.money(min((o.price for o in offers), default=service.price))
    )
    kb.button(
        text=f"{ctx.t('common.any_master')} · {cheapest}",
        callback_data=MasterCb(service_id=service.id, master_id=0),
    )
    for offer in offers:
        key = "book.master_line_rated" if offer.rating else "book.master_line"
        kb.button(
            text=ctx.t(
                key,
                name=ctx.master_name(offer.master),
                price=ctx.money(offer.price),
                rating=f"{offer.rating:.1f}" if offer.rating else "",
            ),
            callback_data=MasterCb(service_id=service.id, master_id=offer.master.id),
        )
    kb.adjust(1)
    kb.row(back_button(ctx, CategoryCb(id=service.category_id).pack()))
    description = service.description_ru if ctx.is_ru else service.description_en
    text = ctx.t("book.choose_master", service=ctx.service_name(service), description=description)
    await show(call, text, kb.as_markup())


async def days_markup(
    ctx: BotContext, service_id: int, master_id: int, booking_id: int, back: str
) -> InlineKeyboardMarkup | None:
    availability = AvailabilityService(ctx.session, ctx.deps.clock)
    days = await availability.calendar(service_id, master_id=master_id or None)
    open_days = [d for d in days if d.slots]
    if not open_days:
        return None
    kb = InlineKeyboardBuilder()
    for info in open_days:
        kb.button(
            text=ctx.t("book.day_line", date=fmt_date(info.day, ctx.lang), count=info.slots),
            callback_data=DayCb(
                service_id=service_id,
                master_id=master_id,
                day=info.day.strftime("%Y%m%d"),
                booking_id=booking_id,
            ),
        )
    kb.adjust(2)
    kb.row(back_button(ctx, back))
    return kb.as_markup()


@router.callback_query(MasterCb.filter())
async def days(call: CallbackQuery, callback_data: MasterCb, ctx: BotContext) -> None:
    catalog = CatalogService(ctx.session)
    service = await catalog.service(callback_data.service_id)
    master = await catalog.master(callback_data.master_id) if callback_data.master_id else None
    markup = await days_markup(
        ctx, service.id, callback_data.master_id, 0, ServiceCb(id=service.id).pack()
    )
    if markup is None:
        kb = InlineKeyboardBuilder()
        kb.row(back_button(ctx, ServiceCb(id=service.id).pack()))
        await show(call, ctx.t("book.no_days"), kb.as_markup())
        return
    text = ctx.t(
        "book.choose_day", service=ctx.service_name(service), master=ctx.master_name(master)
    )
    await show(call, text, markup)


@router.callback_query(DayCb.filter())
async def times(call: CallbackQuery, callback_data: DayCb, ctx: BotContext) -> None:
    catalog = CatalogService(ctx.session)
    service = await catalog.service(callback_data.service_id)
    master = await catalog.master(callback_data.master_id) if callback_data.master_id else None
    day = _day(callback_data.day)
    slots = await AvailabilityService(ctx.session, ctx.deps.clock).day_slots(
        service.id,
        day,
        master_id=callback_data.master_id or None,
        exclude_booking_id=callback_data.booking_id or None,
    )
    if callback_data.booking_id:
        back = BookingCb(id=callback_data.booking_id, action="move").pack()
    else:
        back = MasterCb(service_id=service.id, master_id=callback_data.master_id).pack()

    kb = InlineKeyboardBuilder()
    for slot in slots:
        kb.button(
            text=fmt_time(slot.starts_at, ctx.tz),
            callback_data=SlotCb(
                service_id=service.id,
                master_id=callback_data.master_id,
                ts=int(slot.starts_at.timestamp()),
                booking_id=callback_data.booking_id,
            ),
        )
    kb.adjust(4)
    if not slots:
        kb.row()
        kb.button(
            text=ctx.t("book.waitlist_join"),
            callback_data=WaitlistCb(
                service_id=service.id, master_id=callback_data.master_id, day=callback_data.day
            ),
        )
    kb.row(back_button(ctx, back))
    key = "book.choose_time" if slots else "book.no_time"
    text = ctx.t(
        key,
        date=fmt_date(day, ctx.lang),
        service=ctx.service_name(service),
        master=ctx.master_name(master),
    )
    if not slots:
        text = f"<b>{fmt_date(day, ctx.lang)}</b>\n{text}"
    await show(call, text, kb.as_markup())


@router.callback_query(WaitlistCb.filter())
async def waitlist(call: CallbackQuery, callback_data: WaitlistCb, ctx: BotContext) -> None:
    day = _day(callback_data.day)
    await WaitlistService(ctx.session, ctx.deps.clock).join(
        ctx.client.id, callback_data.service_id, day, callback_data.master_id or None
    )
    kb = InlineKeyboardBuilder()
    kb.row(menu_button(ctx))
    await show(call, ctx.t("book.waitlist_done", date=fmt_date(day, ctx.lang)), kb.as_markup())


@router.callback_query(SlotCb.filter(F.booking_id == 0))
async def pick_slot(
    call: CallbackQuery, callback_data: SlotCb, ctx: BotContext, state: FSMContext
) -> None:
    starts_at = datetime.fromtimestamp(callback_data.ts, tz=UTC)
    master_id = callback_data.master_id
    try:
        if not master_id:
            master_id = (
                await ctx.bookings.suggest_master(callback_data.service_id, starts_at)
            ).master.id
    except SlotUnavailableError:
        await call.answer(ctx.t("book.slot_taken"), show_alert=True)
        return
    await state.set_data(
        {
            "service_id": callback_data.service_id,
            "master_id": master_id,
            "ts": callback_data.ts,
            "use_bonus": False,
        }
    )
    await _summary(call, ctx, state)


async def _summary(call: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    if not data:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    catalog = CatalogService(ctx.session)
    service = await catalog.service(data["service_id"])
    offer = await catalog.offer(service.id, data["master_id"])
    starts_at = datetime.fromtimestamp(data["ts"], tz=UTC)
    business = ctx.business
    bonus = (
        max_bonus_spend(offer.price, ctx.client.bonus_balance, business.max_bonus_share_percent)
        if data["use_bonus"]
        else 0
    )
    deposit = min(deposit_for(offer.price, business.deposit_percent), offer.price - bonus)
    lines = [
        ctx.t(
            "book.summary",
            service=ctx.service_name(service),
            master=ctx.master_name(offer.master),
            when=ctx.when(starts_at),
            price=ctx.money(offer.price),
        )
    ]
    if bonus:
        lines.append(ctx.t("book.summary_bonus", amount=ctx.money(bonus)))
    if deposit:
        lines.append(ctx.t("book.summary_deposit", deposit=ctx.money(deposit)))
    deadline = starts_at.timestamp() - business.cancel_window_hours * 3600
    lines.append(
        ctx.t("book.summary_rules", deadline=ctx.when(datetime.fromtimestamp(deadline, tz=UTC)))
    )

    kb = InlineKeyboardBuilder()
    available_bonus = max_bonus_spend(
        offer.price, ctx.client.bonus_balance, business.max_bonus_share_percent
    )
    if available_bonus:
        key = "book.bonus_used" if data["use_bonus"] else "book.use_bonus"
        kb.button(
            text=ctx.t(key, amount=ctx.money(available_bonus)),
            callback_data=ConfirmCb(action="bonus"),
        )
    if deposit:
        kb.button(
            text=ctx.t("book.pay_card", amount=ctx.money(deposit)),
            callback_data=ConfirmCb(action="card"),
        )
        if business.stars_enabled:
            stars = stars_for(deposit, ctx.settings.stars_per_usd, ctx.settings.stars_fixed_price)
            kb.button(
                text=ctx.t("book.pay_stars", amount=ctx.money(stars, "XTR")),
                callback_data=ConfirmCb(action="stars"),
            )
    else:
        kb.button(text=ctx.t("book.confirm_on_site"), callback_data=ConfirmCb(action="site"))
    kb.adjust(1)
    day = starts_at.astimezone(ctx.tz).strftime("%Y%m%d")
    kb.row(
        back_button(
            ctx, DayCb(service_id=data["service_id"], master_id=data["master_id"], day=day).pack()
        )
    )
    await show(call, "\n".join(lines), kb.as_markup())


@router.callback_query(ConfirmCb.filter(F.action == "bonus"))
async def toggle_bonus(call: CallbackQuery, ctx: BotContext, state: FSMContext) -> None:
    data = await state.get_data()
    if data:
        await state.update_data(use_bonus=not data.get("use_bonus", False))
    await _summary(call, ctx, state)


@router.callback_query(ConfirmCb.filter())
async def confirm(
    call: CallbackQuery, callback_data: ConfirmCb, ctx: BotContext, state: FSMContext, bot: Bot
) -> None:
    data = await state.get_data()
    if not data:
        await call.answer(ctx.t("errors.expired"), show_alert=True)
        return
    method = {
        "card": PaymentMethod.CARD,
        "stars": PaymentMethod.STARS,
        "site": PaymentMethod.ON_SITE,
    }[callback_data.action]
    starts_at = datetime.fromtimestamp(data["ts"], tz=UTC)
    try:
        booking = await ctx.bookings.create(
            ctx.client,
            BookingRequest(
                service_id=data["service_id"],
                master_id=data["master_id"],
                starts_at=starts_at,
                payment_method=method,
                use_bonus=data["use_bonus"],
                source=BookingSource.BOT,
            ),
        )
    except SlotUnavailableError:
        kb = InlineKeyboardBuilder()
        day = starts_at.astimezone(ctx.tz).strftime("%Y%m%d")
        kb.row(
            back_button(
                ctx,
                DayCb(service_id=data["service_id"], master_id=data["master_id"], day=day).pack(),
            )
        )
        await show(call, ctx.t("book.slot_taken"), kb.as_markup())
        return
    except (PolicyError, DomainError):
        await call.answer(ctx.t("errors.generic"), show_alert=True)
        return
    await state.clear()

    if booking.status is BookingStatus.CONFIRMED:
        await show(call, confirmed_text(ctx, booking), after_booking_markup(ctx))
        return
    await show(call, ctx.t("book.hold_note", minutes=ctx.business.hold_minutes))
    pending = next(p for p in booking.payments if p.status is PaymentStatus.PENDING)
    await send_deposit_invoice(ctx, bot, booking, pending)


def confirmed_text(ctx: BotContext, booking: Booking) -> str:
    return ctx.t(
        "book.confirmed",
        service=ctx.service_name(booking.service),
        master=ctx.master_name(booking.master),
        when=ctx.when(booking.starts_at),
        address=ctx.business.address,
    )


def after_booking_markup(ctx: BotContext) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=ctx.t("menu.my_bookings"), callback_data=MenuCb(action="bookings"))
    kb.row(menu_button(ctx))
    return kb.as_markup()


async def send_deposit_invoice(
    ctx: BotContext, bot: Bot, booking: Booking, payment: Payment
) -> None:
    assert ctx.client.telegram_id is not None
    if payment.provider is PaymentProvider.DEMO:
        # No BotFather payment token: a button that simulates a successful test payment.
        kb = InlineKeyboardBuilder()
        kb.button(
            text=f"{ctx.t('bookings.pay')} · {ctx.money(payment.amount, payment.currency)} (demo)",
            callback_data=BookingCb(id=booking.id, action="demopay"),
        )
        await bot.send_message(
            ctx.client.telegram_id,
            ctx.t("book.hold_note", minutes=ctx.business.hold_minutes),
            reply_markup=kb.as_markup(),
        )
        return
    title, description = deposit_texts(booking, ctx.business, ctx.lang)
    invoice = ctx.payments.invoice_for(payment, title=title, description=description)
    await bot.send_invoice(
        chat_id=ctx.client.telegram_id,
        title=invoice.title[:32],
        description=invoice.description[:255],
        payload=invoice.payload,
        currency=invoice.currency,
        prices=[LabeledPrice(label=ctx.t("invoice.label"), amount=invoice.amount)],
        provider_token=invoice.provider_token,
    )
