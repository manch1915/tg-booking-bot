"""Business rules for money and cancellations. Amounts are in minor units (cents)."""

from dataclasses import dataclass
from datetime import datetime, timedelta


def percent_of(amount: int, percent: int) -> int:
    return (amount * percent + 50) // 100


def deposit_for(price: int, deposit_percent: int) -> int:
    """Deposit rounded up to a whole currency unit so invoices look tidy."""
    raw = percent_of(price, deposit_percent)
    return -(-raw // 100) * 100 if raw else 0


def max_bonus_spend(price: int, balance: int, max_share_percent: int) -> int:
    return max(0, min(balance, percent_of(price, max_share_percent)))


def cashback_for(paid_total: int, cashback_percent: int) -> int:
    return percent_of(paid_total, cashback_percent)


def stars_for(amount_cents: int, stars_per_usd: int, fixed: int | None = None) -> int:
    if fixed is not None:
        return fixed
    return max(1, -(-amount_cents * stars_per_usd // 100))


@dataclass(frozen=True, slots=True)
class ChangeDecision:
    can_cancel: bool
    can_reschedule: bool
    refund_deposit: bool
    deadline: datetime


def change_policy(*, starts_at: datetime, now: datetime, window_hours: int) -> ChangeDecision:
    """Clients may move or cancel with a refund until `window_hours` before the visit.

    After the deadline cancelling is still allowed (the slot frees up for the waitlist),
    but the deposit stays with the shop.
    """
    deadline = starts_at - timedelta(hours=window_hours)
    in_time = now <= deadline
    return ChangeDecision(
        can_cancel=now < starts_at,
        can_reschedule=in_time,
        refund_deposit=in_time,
        deadline=deadline,
    )
