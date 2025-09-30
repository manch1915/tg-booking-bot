import hashlib
import hmac
import json
import time
from collections.abc import AsyncIterator
from datetime import timedelta
from urllib.parse import urlencode

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncEngine

from booking.api.app import create_app
from booking.api.state import AppState
from booking.config import Settings
from booking.infra.db.session import make_sessionmaker
from booking.services.auth import TokenIssuer
from booking.services.clock import FixedClock

from .conftest import NOW

BOT_TOKEN = "123456:TEST-token-for-signatures"


def signed_init_data(user: dict[str, object], **extra: str) -> str:
    fields = {"auth_date": str(int(time.time())), "user": json.dumps(user), **extra}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
async def api(engine: AsyncEngine, settings: Settings) -> AsyncIterator[AsyncClient]:
    app_settings = settings.model_copy(update={"bot_token": SecretStr(BOT_TOKEN)})
    state = AppState(
        settings=app_settings,
        engine=engine,
        sessions=make_sessionmaker(engine),
        tokens=TokenIssuer("test-secret-test-secret-test-secret", 60),
        clock=FixedClock(NOW),
    )
    app = create_app(app_settings, state)
    app.state.booking = state
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def demo_login(api: AsyncClient) -> dict[str, str]:
    response = await api.post("/api/app/auth/demo", json={"language": "en"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


async def test_catalog_is_public(api: AsyncClient) -> None:
    response = await api.get("/api/app/catalog")
    assert response.status_code == 200
    body = response.json()
    assert [c["name"]["en"] for c in body["categories"]] == [
        "Haircuts",
        "Beard & shave",
        "Combos",
        "Care",
    ]
    fade = next(
        s for c in body["categories"] for s in c["services"] if s["name"]["en"] == "Skin fade"
    )
    assert fade["price_from"] == 2700  # the junior barber is cheaper
    assert len(body["masters"]) == 4


async def test_demo_guest_has_history_and_bonuses(api: AsyncClient) -> None:
    headers = await demo_login(api)
    me = (await api.get("/api/app/me", headers=headers)).json()
    assert me["is_demo_guest"]
    assert me["visits"] == 2
    assert me["bonus_balance"] > 300
    history = (await api.get("/api/app/bookings", headers=headers)).json()
    assert {b["status"] for b in history} == {"completed"}


async def test_requests_without_token_are_rejected(api: AsyncClient) -> None:
    response = await api.get("/api/app/me")
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


async def test_telegram_login_and_referral(api: AsyncClient) -> None:
    friend = await demo_login(api)
    code = (await api.get("/api/app/me", headers=friend)).json()["referral_code"]
    init_data = signed_init_data(
        {"id": 987654321, "first_name": "Tigran", "language_code": "ru"},
        start_param=f"ref_{code}",
    )
    response = await api.post("/api/app/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 200
    client = response.json()["client"]
    assert client["in_telegram"]
    assert client["language"] == "ru"


async def test_forged_init_data_is_rejected(api: AsyncClient) -> None:
    init_data = signed_init_data({"id": 1, "first_name": "Eve"}).replace("Eve", "Bob")
    response = await api.post("/api/app/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 401


async def test_full_booking_flow(api: AsyncClient) -> None:
    headers = await demo_login(api)
    catalog = (await api.get("/api/app/catalog")).json()
    service = next(
        s for c in catalog["categories"] for s in c["services"] if s["name"]["en"] == "Beard trim"
    )
    days = (
        await api.get("/api/app/availability/calendar", params={"service_id": service["id"]})
    ).json()
    day = next(d["day"] for d in days[2:] if d["slots"] > 0)
    slots = (
        await api.get(
            "/api/app/availability/slots", params={"service_id": service["id"], "day": day}
        )
    ).json()
    slot = slots[len(slots) // 2]

    created = await api.post(
        "/api/app/bookings",
        headers=headers,
        json={
            "service_id": service["id"],
            "starts_at": slot["starts_at"],
            "payment_method": "card",
            "use_bonus": True,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    booking, payment = body["booking"], body["payment"]
    assert booking["status"] == "pending_payment"
    assert booking["master"]["id"] in slot["master_ids"]
    assert payment["provider"] == "demo"
    assert booking["bonus_spent"] > 0

    taken = await api.post(
        "/api/app/bookings",
        headers=await demo_login(api),
        json={
            "service_id": service["id"],
            "master_id": booking["master"]["id"],
            "starts_at": slot["starts_at"],
            "payment_method": "card",
        },
    )
    assert taken.status_code == 409

    paid = await api.post(
        f"/api/app/payments/{payment['payment_id']}/demo-confirm", headers=headers
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "confirmed"
    assert paid.json()["deposit_status"] == "paid"
    assert paid.json()["can_reschedule"]

    cancelled = await api.post(f"/api/app/bookings/{booking['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["refund"] == "refunded"
    assert cancelled.json()["booking"]["status"] == "cancelled"


async def test_review_only_after_visit(api: AsyncClient) -> None:
    headers = await demo_login(api)
    history = (await api.get("/api/app/bookings", headers=headers)).json()
    past = history[0]
    response = await api.post(
        f"/api/app/bookings/{past['id']}/review",
        headers=headers,
        json={"rating": 5, "comment": "Sharp lines, quick and friendly"},
    )
    assert response.status_code == 200
    assert response.json()["review"]["rating"] == 5


async def test_booking_of_another_client_is_hidden(api: AsyncClient) -> None:
    owner = await demo_login(api)
    stranger = await demo_login(api)
    booking_id = (await api.get("/api/app/bookings", headers=owner)).json()[0]["id"]
    response = await api.get(f"/api/app/bookings/{booking_id}", headers=stranger)
    assert response.status_code == 404


async def test_slot_outside_horizon_is_refused(api: AsyncClient) -> None:
    headers = await demo_login(api)
    catalog = (await api.get("/api/app/catalog")).json()
    service = catalog["categories"][0]["services"][0]
    far = (NOW + timedelta(days=40)).replace(hour=8).isoformat()
    response = await api.post(
        "/api/app/bookings",
        headers=headers,
        json={"service_id": service["id"], "starts_at": far, "payment_method": "card"},
    )
    assert response.status_code == 409
