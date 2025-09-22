from datetime import UTC, datetime, timedelta

import pytest

from booking.domain.policies import (
    cashback_for,
    change_policy,
    deposit_for,
    max_bonus_spend,
    stars_for,
)

VISIT = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("price", "percent", "expected"),
    [(3500, 30, 1100), (4000, 25, 1000), (2000, 0, 0), (999, 10, 100)],
)
def test_deposit_rounds_up_to_whole_units(price: int, percent: int, expected: int) -> None:
    assert deposit_for(price, percent) == expected


def test_bonus_spend_is_capped_by_share_and_balance() -> None:
    assert max_bonus_spend(price=4000, balance=5000, max_share_percent=30) == 1200
    assert max_bonus_spend(price=4000, balance=700, max_share_percent=30) == 700
    assert max_bonus_spend(price=4000, balance=0, max_share_percent=30) == 0


def test_cashback() -> None:
    assert cashback_for(3500, 5) == 175


def test_stars_conversion_and_fixed_price() -> None:
    assert stars_for(1100, stars_per_usd=50) == 550
    assert stars_for(1, stars_per_usd=50) == 1
    assert stars_for(1100, stars_per_usd=50, fixed=1) == 1


def test_change_in_time_allows_everything() -> None:
    decision = change_policy(starts_at=VISIT, now=VISIT - timedelta(hours=5), window_hours=3)
    assert decision.can_cancel
    assert decision.can_reschedule
    assert decision.refund_deposit


def test_late_cancel_keeps_deposit() -> None:
    decision = change_policy(starts_at=VISIT, now=VISIT - timedelta(hours=1), window_hours=3)
    assert decision.can_cancel
    assert not decision.can_reschedule
    assert not decision.refund_deposit


def test_deadline_is_inclusive() -> None:
    decision = change_policy(starts_at=VISIT, now=VISIT - timedelta(hours=3), window_hours=3)
    assert decision.refund_deposit


def test_visit_started_cannot_be_cancelled() -> None:
    decision = change_policy(starts_at=VISIT, now=VISIT, window_hours=3)
    assert not decision.can_cancel
