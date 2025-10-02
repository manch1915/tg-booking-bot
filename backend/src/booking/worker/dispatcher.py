import logging
from datetime import datetime, timedelta
from urllib.parse import quote_plus

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from booking.bot.callbacks import BookingCb, DayCb, MenuCb, ReviewCb
from booking.config import Settings
from booking.domain.enums import BookingStatus, Language, NotificationKind
from booking.domain.policies import cashback_for
from booking.i18n import fmt_date, fmt_datetime, fmt_money, fmt_time, t
from booking.infra.db.models import Booking, Broadcast, Business, Client, Master, Notification
from booking.services.business import business_tz, load_business
from booking.services.clock import Clock
from booking.services.messaging import Button, DeliveryError, Messenger, OutgoingMessage

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5


class NotReadyError(Exception):
    """The notification is not ready to go yet (e.g. the visit is not closed)."""


class NotificationDispatcher:
    def __init__(
        self, session: AsyncSession, clock: Clock, settings: Settings, messenger: Messenger
    ) -> None:
        self.session = session
        self.clock = clock
        self.settings = settings
        self.messenger = messenger

    async def dispatch_due(self, limit: int = 50) -> int:
        now = self.clock.now()
        rows = await self.session.scalars(
            select(Notification)
            .where(
                Notification.sent_at.is_(None),
                Notification.cancelled_at.is_(None),
                Notification.send_at <= now,
            )
            .order_by(Notification.send_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        due = list(rows)
        business = await load_business(self.session) if due else None
        sent = 0
        for notification in due:
            assert business is not None
            sent += await self._deliver(notification, business)
        await self.session.flush()
        return sent

    async def _deliver(self, notification: Notification, business: Business) -> int:
        try:
            message = await self.render(notification, business)
        except NotReadyError:
            notification.send_at = self.clock.now() + timedelta(minutes=10)
            return 0
        if message is None:
            notification.sent_at = self.clock.now()
            notification.error = "skipped"
            return 0
        try:
            await self.messenger.send(message)
        except DeliveryError as exc:
            notification.attempts += 1
            notification.error = str(exc)[:300]
            if exc.permanent or notification.attempts >= MAX_ATTEMPTS:
                notification.sent_at = self.clock.now()
            else:
                delay = exc.retry_after or 60 * notification.attempts
                notification.send_at = self.clock.now() + timedelta(seconds=delay)
            return 0
        notification.sent_at = self.clock.now()
        notification.error = None
        return 1

    async def render(
        self, notification: Notification, business: Business
    ) -> OutgoingMessage | None:
        kind = notification.kind
        booking = await self._booking(notification.booking_id)
        if kind is NotificationKind.BROADCAST:
            return await self._broadcast(notification)
        if kind in MASTER_KINDS:
            master = await self.session.get(Master, notification.master_id)
            if master is None or master.telegram_id is None or booking is None:
                return None
            return self._master_message(notification, master, booking, business)

        client = await self.session.get(Client, notification.client_id)
        if client is None or client.telegram_id is None:
            return None
        if booking is not None and not self._still_relevant(kind, booking):
            return None
        return await self._client_message(notification, client, booking, business)

    def _still_relevant(self, kind: NotificationKind, booking: Booking) -> bool:
        if kind in {NotificationKind.REMINDER_DAY, NotificationKind.REMINDER_SOON}:
            return booking.status is BookingStatus.CONFIRMED
        if kind is NotificationKind.REVIEW_REQUEST:
            if booking.status is BookingStatus.CONFIRMED:
                raise NotReadyError
            return booking.status is BookingStatus.COMPLETED and booking.review is None
        return True

    async def _client_message(
        self,
        notification: Notification,
        client: Client,
        booking: Booking | None,
        business: Business,
    ) -> OutgoingMessage | None:
        lang = client.language
        tz = business_tz(business)
        kind = notification.kind
        assert client.telegram_id is not None
        chat = client.telegram_id
        app_url = f"{self.settings.public_url.rstrip('/')}/app/"
        ctx = self._booking_ctx(booking, business, lang) if booking else {}

        if kind is NotificationKind.BOOKING_CONFIRMED:
            text = t(lang, "notify.booking_confirmed", **ctx)
            buttons = [[Button(t(lang, "menu.my_bookings"), MenuCb(action="bookings").pack())]]
        elif kind is NotificationKind.REMINDER_DAY and booking:
            deadline = booking.starts_at - timedelta(hours=business.cancel_window_hours)
            text = t(lang, "notify.reminder_day", deadline=fmt_datetime(deadline, tz, lang), **ctx)
            buttons = [
                [Button(t(lang, "notify.keep"), BookingCb(id=booking.id, action="keep").pack())],
                [
                    Button(
                        t(lang, "bookings.reschedule"),
                        BookingCb(id=booking.id, action="move").pack(),
                    ),
                    Button(
                        t(lang, "bookings.cancel"), BookingCb(id=booking.id, action="cancel").pack()
                    ),
                ],
            ]
        elif kind is NotificationKind.REMINDER_SOON and booking:
            text = t(lang, "notify.reminder_soon", time=fmt_time(booking.starts_at, tz), **ctx)
            maps = (
                f"https://maps.google.com/?q={quote_plus(business.name + ' ' + business.address)}"
            )
            buttons = [[Button(t(lang, "contacts.map"), url=maps)]]
        elif kind is NotificationKind.REVIEW_REQUEST and booking:
            cashback = cashback_for(booking.price - booking.bonus_spent, business.cashback_percent)
            text = t(
                lang,
                "notify.review_request",
                cashback=fmt_money(cashback, business.currency),
                **ctx,
            )
            buttons = [
                [
                    Button("★" * n, ReviewCb(booking_id=booking.id, rating=n).pack())
                    for n in (1, 2, 3)
                ],
                [Button("★" * n, ReviewCb(booking_id=booking.id, rating=n).pack()) for n in (4, 5)],
            ]
        elif kind is NotificationKind.BOOKING_CANCELLED and booking:
            text = t(lang, "notify.booking_cancelled", **ctx)
            buttons = [[Button(t(lang, "menu.book"), MenuCb(action="book").pack())]]
        elif kind is NotificationKind.BOOKING_RESCHEDULED and booking:
            text = t(lang, "notify.booking_rescheduled", **ctx)
            buttons = [[Button(t(lang, "menu.my_bookings"), MenuCb(action="bookings").pack())]]
        elif kind is NotificationKind.WAITLIST_SLOT:
            payload = notification.payload
            day = datetime.fromisoformat(payload["day"]).date()
            master = await self._master_name(payload.get("master_id"), lang)
            text = t(lang, "notify.waitlist_slot", date=fmt_date(day, lang), master=master)
            buttons = [
                [
                    Button(
                        t(lang, "notify.open_booking"),
                        DayCb(
                            service_id=payload["service_id"],
                            master_id=0,
                            day=day.strftime("%Y%m%d"),
                        ).pack(),
                    ),
                    Button(t(lang, "menu.open_app"), web_app=app_url),
                ]
            ]
        elif kind is NotificationKind.BONUS_ACCRUED:
            payload = notification.payload
            text = t(
                lang,
                "notify.bonus_accrued",
                friend=payload.get("friend", ""),
                amount=fmt_money(int(payload.get("amount", 0)), business.currency),
            )
            buttons = [[Button(t(lang, "menu.bonuses"), MenuCb(action="bonuses").pack())]]
        else:
            return None
        return OutgoingMessage(chat_id=chat, text=text, buttons=buttons)

    def _master_message(
        self, notification: Notification, master: Master, booking: Booking, business: Business
    ) -> OutgoingMessage:
        # Barbers get messages in Russian: the shop works in Russian.
        lang = Language.RU
        tz = business_tz(business)
        ctx = self._booking_ctx(booking, business, lang)
        ctx["client"] = booking.client.name
        ctx["phone"] = booking.client.phone or ""
        key = {
            NotificationKind.MASTER_NEW_BOOKING: "notify.master_new_booking",
            NotificationKind.MASTER_CANCELLED: "notify.master_cancelled",
            NotificationKind.MASTER_RESCHEDULED: "notify.master_rescheduled",
        }[notification.kind]
        previous = notification.payload.get("previous_start")
        if previous:
            ctx["previous"] = fmt_datetime(datetime.fromisoformat(previous), tz, lang)
        assert master.telegram_id is not None
        return OutgoingMessage(chat_id=master.telegram_id, text=t(lang, key, **ctx))

    async def _broadcast(self, notification: Notification) -> OutgoingMessage | None:
        client = await self.session.get(Client, notification.client_id)
        broadcast = await self.session.get(Broadcast, notification.broadcast_id)
        if client is None or client.telegram_id is None or broadcast is None:
            return None
        if client.marketing_opt_out:
            return None
        lang = client.language
        text = broadcast.text_ru if lang is Language.RU else broadcast.text_en
        app_url = f"{self.settings.public_url.rstrip('/')}/app/"
        return OutgoingMessage(
            chat_id=client.telegram_id,
            text=text,
            buttons=[[Button(t(lang, "menu.book"), web_app=app_url)]],
        )

    def _booking_ctx(self, booking: Booking, business: Business, lang: Language) -> dict[str, str]:
        tz = business_tz(business)
        ru = lang is Language.RU
        return {
            "service": booking.service.name_ru if ru else booking.service.name_en,
            "master": booking.master.name if ru else booking.master.name_en,
            "when": fmt_datetime(booking.starts_at, tz, lang),
            "address": business.address,
            "price": fmt_money(booking.price, business.currency),
        }

    async def _master_name(self, master_id: int | None, lang: Language) -> str:
        master = await self.session.get(Master, master_id) if master_id else None
        if master is None:
            return t(lang, "common.any_master")
        return master.name if lang is Language.RU else master.name_en

    async def _booking(self, booking_id: int | None) -> Booking | None:
        if booking_id is None:
            return None
        return await self.session.scalar(
            select(Booking)
            .where(Booking.id == booking_id)
            .options(
                selectinload(Booking.client),
                selectinload(Booking.master),
                selectinload(Booking.service),
                selectinload(Booking.review),
            )
        )


MASTER_KINDS = {
    NotificationKind.MASTER_NEW_BOOKING,
    NotificationKind.MASTER_CANCELLED,
    NotificationKind.MASTER_RESCHEDULED,
}
