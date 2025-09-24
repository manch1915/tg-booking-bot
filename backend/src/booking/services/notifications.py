from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.enums import NotificationKind
from booking.infra.db.models import Booking, Notification
from booking.services.clock import Clock

REMINDER_DAY_BEFORE = timedelta(hours=24)
REMINDER_SOON_BEFORE = timedelta(hours=2)
REVIEW_AFTER_END = timedelta(hours=1)

CLIENT_VISIT_KINDS = (
    NotificationKind.REMINDER_DAY,
    NotificationKind.REMINDER_SOON,
    NotificationKind.REVIEW_REQUEST,
)


class NotificationScheduler:
    """Writes rows to the notification outbox; the worker delivers them."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock

    def enqueue(
        self,
        kind: NotificationKind,
        *,
        send_at: datetime | None = None,
        client_id: int | None = None,
        master_id: int | None = None,
        booking_id: int | None = None,
        broadcast_id: int | None = None,
        chat_id: int | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Notification:
        notification = Notification(
            kind=kind,
            send_at=send_at or self.clock.now(),
            client_id=client_id,
            master_id=master_id,
            booking_id=booking_id,
            broadcast_id=broadcast_id,
            chat_id=chat_id,
            payload=payload or {},
        )
        self.session.add(notification)
        return notification

    def booking_confirmed(self, booking: Booking, *, notify_client: bool = True) -> None:
        if notify_client:
            self.enqueue(
                NotificationKind.BOOKING_CONFIRMED,
                client_id=booking.client_id,
                booking_id=booking.id,
            )
        self._visit_reminders(booking)
        self.enqueue(
            NotificationKind.MASTER_NEW_BOOKING, master_id=booking.master_id, booking_id=booking.id
        )

    async def booking_rescheduled(self, booking: Booking, previous_start: datetime) -> None:
        await self.cancel_pending(booking.id, CLIENT_VISIT_KINDS)
        self._visit_reminders(booking)
        payload = {"previous_start": previous_start.isoformat()}
        self.enqueue(
            NotificationKind.BOOKING_RESCHEDULED,
            client_id=booking.client_id,
            booking_id=booking.id,
            payload=payload,
        )
        self.enqueue(
            NotificationKind.MASTER_RESCHEDULED,
            master_id=booking.master_id,
            booking_id=booking.id,
            payload=payload,
        )

    async def booking_cancelled(self, booking: Booking, *, notify_client: bool) -> None:
        await self.cancel_pending(booking.id, CLIENT_VISIT_KINDS)
        if notify_client:
            self.enqueue(
                NotificationKind.BOOKING_CANCELLED,
                client_id=booking.client_id,
                booking_id=booking.id,
            )
        self.enqueue(
            NotificationKind.MASTER_CANCELLED, master_id=booking.master_id, booking_id=booking.id
        )

    async def cancel_pending(self, booking_id: int, kinds: Iterable[NotificationKind]) -> None:
        await self.session.execute(
            update(Notification)
            .where(
                Notification.booking_id == booking_id,
                Notification.kind.in_(list(kinds)),
                Notification.sent_at.is_(None),
                Notification.cancelled_at.is_(None),
            )
            .values(cancelled_at=self.clock.now())
        )

    def _visit_reminders(self, booking: Booking) -> None:
        now = self.clock.now()
        day_before = booking.starts_at - REMINDER_DAY_BEFORE
        # A reminder "tomorrow at 15:00" makes no sense for a booking made an hour ago.
        if day_before > now + timedelta(hours=2):
            self.enqueue(
                NotificationKind.REMINDER_DAY,
                send_at=day_before,
                client_id=booking.client_id,
                booking_id=booking.id,
            )
        soon = booking.starts_at - REMINDER_SOON_BEFORE
        if soon > now + timedelta(minutes=30):
            self.enqueue(
                NotificationKind.REMINDER_SOON,
                send_at=soon,
                client_id=booking.client_id,
                booking_id=booking.id,
            )
        self.enqueue(
            NotificationKind.REVIEW_REQUEST,
            send_at=booking.ends_at + REVIEW_AFTER_END,
            client_id=booking.client_id,
            booking_id=booking.id,
        )
