from datetime import datetime, timedelta

from httpx import AsyncClient

from .conftest import NOW
from .test_api import api  # noqa: F401 - shared fixture

TODAY = NOW.date()


async def login(api: AsyncClient) -> None:  # noqa: F811
    response = await api.post("/api/admin/auth/demo")
    assert response.status_code == 200
    assert response.json()["demo"]


async def test_admin_requires_cookie(api: AsyncClient) -> None:  # noqa: F811
    api.cookies.clear()
    response = await api.get("/api/admin/journal", params={"start": TODAY.isoformat()})
    assert response.status_code == 401


async def test_password_login(api: AsyncClient) -> None:  # noqa: F811
    bad = await api.post(
        "/api/admin/auth/login", json={"email": "owner@brassblade.demo", "password": "nope"}
    )
    assert bad.status_code == 401
    good = await api.post(
        "/api/admin/auth/login",
        json={"email": "owner@brassblade.demo", "password": "demo-owner-2026"},
    )
    assert good.status_code == 200
    assert (await api.get("/api/admin/auth/me")).json()["name"]


async def test_journal_shows_week_of_masters_and_bookings(api: AsyncClient) -> None:  # noqa: F811
    await login(api)
    response = await api.get("/api/admin/journal", params={"start": TODAY.isoformat(), "days": 7})
    assert response.status_code == 200
    body = response.json()
    assert len(body["days"]) == 7
    assert len(body["masters"]) == 4
    assert body["bookings"]
    booking = body["bookings"][0]
    assert {"client", "payments", "master", "service"} <= booking.keys()
    assert any(o["reason"] for o in body["time_off"])


async def test_manual_booking_by_phone_off_grid(api: AsyncClient) -> None:  # noqa: F811
    await login(api)
    masters = (await api.get("/api/admin/masters")).json()
    services = (await api.get("/api/admin/services")).json()
    davit = next(m for m in masters if m["master"]["name"]["en"] == "Davit Melkonyan")
    shave = next(s for s in services if s["name"]["en"] == "Royal shave")
    day = TODAY + timedelta(days=12)
    slots = (
        await api.get(
            "/api/app/availability/slots",
            params={
                "service_id": shave["id"],
                "day": day.isoformat(),
                "master_id": davit["master"]["id"],
            },
        )
    ).json()
    starts = [datetime.fromisoformat(s["starts_at"]) for s in slots]
    # A walk-in style time off the 15-minute grid, inside a window that has room for it.
    gap = next(s for s in starts if s + timedelta(minutes=15) in starts)
    payload = {
        "client_name": "Гагик по телефону",
        "client_phone": "+374 99 123 456",
        "service_id": shave["id"],
        "master_id": davit["master"]["id"],
        "starts_at": (gap + timedelta(minutes=5)).isoformat(),
        "comment": "Позвонил в 10:05",
    }
    created = await api.post("/api/admin/bookings", json=payload)
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["status"] == "confirmed"
    assert booking["source"] == "admin"
    assert booking["client"]["phone"] == "+374 99 123 456"

    again = await api.post("/api/admin/bookings", json=payload)
    assert again.status_code == 409

    done = await api.post(
        f"/api/admin/bookings/{booking['id']}/status", json={"action": "cancel", "reason": "звонок"}
    )
    assert done.json()["status"] == "cancelled"


async def test_reports_and_export(api: AsyncClient) -> None:  # noqa: F811
    await login(api)
    start = (TODAY - timedelta(days=20)).isoformat()
    end = (TODAY - timedelta(days=1)).isoformat()
    report = (await api.get("/api/admin/reports", params={"start": start, "end": end})).json()
    assert report["revenue"] > 0
    assert report["visits"] > 100
    assert 0 < report["load"] < 1
    assert len(report["by_day"]) == 20
    assert {m["master_id"] for m in report["by_master"]}
    assert report["by_service"][0]["revenue"] >= report["by_service"][-1]["revenue"]

    csv = await api.get("/api/admin/bookings.csv", params={"start": start, "end": end})
    assert csv.status_code == 200
    lines = csv.text.splitlines()
    assert lines[0].lstrip("﻿").startswith("id;date;time;client")
    assert len(lines) > 100


async def test_clients_segments_and_bonus(api: AsyncClient) -> None:  # noqa: F811
    await login(api)
    page = (await api.get("/api/admin/clients", params={"per_page": 10})).json()
    assert page["total"] >= 300
    first = page["items"][0]
    detail = (await api.get(f"/api/admin/clients/{first['id']}")).json()
    assert detail["bookings"]
    adjusted = await api.post(
        f"/api/admin/clients/{first['id']}/bonus", json={"amount": 500, "comment": "Извинение"}
    )
    assert adjusted.json()["client"]["bonus_balance"] == first["bonus_balance"] + 500

    inactive = (await api.get("/api/admin/clients", params={"segment": "inactive_30"})).json()
    assert inactive["total"] < page["total"]


async def test_broadcast_is_simulated_in_demo(api: AsyncClient) -> None:  # noqa: F811
    await login(api)
    preview = (await api.post("/api/admin/broadcasts/preview", json={"segment": "all"})).json()
    assert preview["total"] >= 300
    sent = await api.post(
        "/api/admin/broadcasts",
        json={"segment": "all", "text_ru": "Тест", "text_en": "Test"},
    )
    assert sent.status_code == 201
    assert sent.json()["recipients"] == preview["total"]


async def test_schedule_update_validates_intervals(api: AsyncClient) -> None:  # noqa: F811
    await login(api)
    masters = (await api.get("/api/admin/masters")).json()
    mark = next(m for m in masters if m["master"]["name"]["en"] == "Mark Avetisyan")
    bad = await api.put(
        f"/api/admin/masters/{mark['master']['id']}/schedule",
        json={"hours": [{"weekday": 0, "start": "18:00", "end": "10:00"}]},
    )
    assert bad.status_code == 422
    link = await api.post(f"/api/admin/masters/{mark['master']['id']}/link")
    assert "start=master_" in link.json()["link_url"]
