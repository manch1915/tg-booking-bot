from datetime import datetime

from booking.api import mappers
from booking.api.admin_schemas import AdminBookingOut, AdminClientRow, ClientRef, PaymentOut
from booking.infra.db.models import Booking, Business, Client


def _masked(client: Client, mask: bool) -> tuple[str, str | None]:
    # The public demo admin must not show who of the real Telegram users tried the bot.
    if not is_masked(client, mask):
        return client.name, client.phone
    parts = client.name.split()
    if not parts:
        return "Telegram", None
    return f"{parts[0]} {parts[1][0]}." if len(parts) > 1 else parts[0], None


def is_masked(client: Client, mask: bool) -> bool:
    return mask and client.telegram_id is not None


def client_ref(client: Client, mask: bool = False) -> ClientRef:
    name, phone = _masked(client, mask)
    return ClientRef(
        id=client.id,
        name=name,
        phone=phone,
        in_telegram=client.telegram_id is not None,
    )


def admin_booking_out(
    booking: Booking, business: Business, now: datetime, mask: bool = False
) -> AdminBookingOut:
    base = mappers.booking_out(booking, business, now)
    return AdminBookingOut(
        **base.model_dump(),
        client=client_ref(booking.client, mask),
        comment="" if is_masked(booking.client, mask) else booking.comment,
        created_at=booking.created_at,
        cancel_reason=booking.cancel_reason,
        payments=[
            PaymentOut(
                id=p.id,
                provider=p.provider,
                purpose=p.purpose.value,
                status=p.status,
                amount=p.amount,
                currency=p.currency,
                amount_base=p.amount_base,
                paid_at=p.paid_at,
            )
            for p in booking.payments
        ],
    )


def client_row(
    client: Client, visits: int, last_visit: datetime | None, spent: int, mask: bool = False
) -> AdminClientRow:
    name, phone = _masked(client, mask)
    return AdminClientRow(
        id=client.id,
        name=name,
        phone=phone,
        language=client.language.value,
        in_telegram=client.telegram_id is not None,
        bonus_balance=client.bonus_balance,
        visits=visits,
        last_visit=last_visit,
        spent=spent,
        created_at=client.created_at,
    )
