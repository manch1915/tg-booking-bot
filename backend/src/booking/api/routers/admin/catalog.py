from fastapi import APIRouter
from sqlalchemy import select

from booking.api import mappers
from booking.api.admin_schemas import (
    AdminMasterOut,
    AdminServiceOut,
    CategoryOutAdmin,
    DaySpanIn,
    MasterIn,
    MasterServiceOut,
    MasterServicesIn,
    ScheduleIn,
    ServiceIn,
    SettingsIn,
    TimeOffIn,
    TimeOffOut,
)
from booking.api.deps import CurrentAdmin, Session, State
from booking.api.schemas import BusinessOut, Localized
from booking.api.state import AppState
from booking.infra.db.models import Category, Master, Service
from booking.services.admin import DaySpan, ScheduleAdmin, ServiceLink, services_with_links
from booking.services.business import load_business
from booking.services.catalog import CatalogService
from booking.services.errors import NotFoundError

router = APIRouter(prefix="/api/admin", tags=["admin catalogue"])


def _master_out(
    master: Master, state: AppState, rating: tuple[float, int] | None
) -> AdminMasterOut:
    link = None
    if master.link_token:
        link = f"https://t.me/{state.settings.bot_username}?start=master_{master.link_token}"
    return AdminMasterOut(
        master=mappers.master_out(master, rating),
        is_active=master.is_active,
        telegram_linked=master.telegram_id is not None,
        link_url=link,
        hours=[
            DaySpanIn(weekday=h.weekday, start=h.start_time, end=h.end_time) for h in master.hours
        ],
        breaks=[
            DaySpanIn(weekday=b.weekday, start=b.start_time, end=b.end_time)
            for b in sorted(master.breaks, key=lambda b: (b.weekday, b.start_time))
        ],
        services=[
            MasterServiceOut(
                service_id=s.service_id, price=s.price, duration_minutes=s.duration_minutes
            )
            for s in master.services
        ],
    )


@router.get("/masters")
async def masters(_: CurrentAdmin, state: State, session: Session) -> list[AdminMasterOut]:
    ratings = await CatalogService(session).ratings()
    return [
        _master_out(m, state, ratings.get(m.id)) for m in await ScheduleAdmin(session).masters()
    ]


@router.post("/masters", status_code=201)
async def create_master(
    body: MasterIn, _: CurrentAdmin, state: State, session: Session
) -> AdminMasterOut:
    master = Master(**body.model_dump())
    ScheduleAdmin.new_link_token(master)
    session.add(master)
    await session.flush()
    return _master_out(await ScheduleAdmin(session).master(master.id), state, None)


@router.put("/masters/{master_id}")
async def update_master(
    master_id: int, body: MasterIn, _: CurrentAdmin, state: State, session: Session
) -> AdminMasterOut:
    schedule = ScheduleAdmin(session)
    master = await schedule.master(master_id)
    for key, value in body.model_dump().items():
        setattr(master, key, value)
    await session.flush()
    return _master_out(master, state, (await CatalogService(session).ratings()).get(master.id))


@router.put("/masters/{master_id}/schedule")
async def set_schedule(
    master_id: int, body: ScheduleIn, _: CurrentAdmin, state: State, session: Session
) -> AdminMasterOut:
    schedule = ScheduleAdmin(session)
    master = await schedule.set_schedule(
        await schedule.master(master_id),
        [DaySpan(h.weekday, h.start, h.end) for h in body.hours],
        [DaySpan(b.weekday, b.start, b.end) for b in body.breaks],
    )
    return _master_out(master, state, (await CatalogService(session).ratings()).get(master.id))


@router.put("/masters/{master_id}/services")
async def set_services(
    master_id: int, body: MasterServicesIn, _: CurrentAdmin, state: State, session: Session
) -> AdminMasterOut:
    schedule = ScheduleAdmin(session)
    master = await schedule.set_services(
        await schedule.master(master_id),
        [ServiceLink(s.service_id, s.price, s.duration_minutes) for s in body.services],
    )
    return _master_out(master, state, (await CatalogService(session).ratings()).get(master.id))


@router.post("/masters/{master_id}/link")
async def new_link(
    master_id: int, _: CurrentAdmin, state: State, session: Session
) -> AdminMasterOut:
    schedule = ScheduleAdmin(session)
    master = await schedule.master(master_id)
    schedule.new_link_token(master)
    await session.flush()
    return _master_out(master, state, (await CatalogService(session).ratings()).get(master.id))


@router.post("/masters/{master_id}/time-off", status_code=201)
async def add_time_off(
    master_id: int, body: TimeOffIn, _: CurrentAdmin, session: Session
) -> TimeOffOut:
    schedule = ScheduleAdmin(session)
    off = await schedule.add_time_off(
        await schedule.master(master_id), body.starts_at, body.ends_at, body.reason
    )
    return TimeOffOut(
        id=off.id,
        master_id=off.master_id,
        starts_at=off.starts_at,
        ends_at=off.ends_at,
        reason=off.reason,
    )


@router.delete("/time-off/{time_off_id}", status_code=204)
async def remove_time_off(time_off_id: int, _: CurrentAdmin, session: Session) -> None:
    await ScheduleAdmin(session).remove_time_off(time_off_id)


def _service_out(service: Service) -> AdminServiceOut:
    return AdminServiceOut(
        id=service.id,
        category_id=service.category_id,
        category=Localized(ru=service.category.name_ru, en=service.category.name_en),
        name=Localized(ru=service.name_ru, en=service.name_en),
        description=Localized(ru=service.description_ru, en=service.description_en),
        duration_minutes=service.duration_minutes,
        price=service.price,
        photo_url=service.photo_url,
        is_popular=service.is_popular,
        is_active=service.is_active,
        masters=len(service.masters),
    )


@router.get("/categories")
async def categories(_: CurrentAdmin, session: Session) -> list[CategoryOutAdmin]:
    rows = await session.scalars(select(Category).order_by(Category.sort))
    return [CategoryOutAdmin(id=c.id, name=Localized(ru=c.name_ru, en=c.name_en)) for c in rows]


@router.get("/services")
async def services(_: CurrentAdmin, session: Session) -> list[AdminServiceOut]:
    return [_service_out(s) for s in await services_with_links(session)]


@router.post("/services", status_code=201)
async def create_service(body: ServiceIn, _: CurrentAdmin, session: Session) -> AdminServiceOut:
    if await session.get(Category, body.category_id) is None:
        raise NotFoundError("Category not found")
    service = Service(**body.model_dump())
    session.add(service)
    await session.flush()
    created = next(s for s in await services_with_links(session) if s.id == service.id)
    return _service_out(created)


@router.put("/services/{service_id}")
async def update_service(
    service_id: int, body: ServiceIn, _: CurrentAdmin, session: Session
) -> AdminServiceOut:
    service = await session.get(Service, service_id)
    if service is None:
        raise NotFoundError("Service not found")
    for key, value in body.model_dump().items():
        setattr(service, key, value)
    await session.flush()
    updated = next(s for s in await services_with_links(session) if s.id == service.id)
    return _service_out(updated)


@router.get("/settings")
async def get_settings(_: CurrentAdmin, state: State, session: Session) -> BusinessOut:
    return mappers.business_out(await load_business(session), state.settings)


@router.put("/settings")
async def update_settings(
    body: SettingsIn, _: CurrentAdmin, state: State, session: Session
) -> BusinessOut:
    business = await load_business(session)
    for key, value in body.model_dump().items():
        setattr(business, key, value)
    await session.flush()
    return mappers.business_out(business, state.settings)
