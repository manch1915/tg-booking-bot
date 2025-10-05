from datetime import date, timedelta

from fastapi import APIRouter

from booking.api.admin_schemas import DayPoint, MasterReport, ReportOut, ServiceReport
from booking.api.deps import CurrentAdmin, Session
from booking.api.schemas import Localized
from booking.services.errors import PolicyError
from booking.services.reports import ReportService

router = APIRouter(prefix="/api/admin", tags=["admin reports"])


@router.get("/reports")
async def report(_: CurrentAdmin, session: Session, start: date, end: date) -> ReportOut:
    if end < start or (end - start).days > 366:
        raise PolicyError("Pick a period of up to one year")
    service = ReportService(session)
    current = await service.build(start, end)
    # Same-length period right before, for the "vs previous" figures on the dashboard.
    length = end - start
    previous_end = start - timedelta(days=1)
    previous = await service.build(previous_end - length, previous_end)
    names = await service.service_names()
    return ReportOut(
        start=current.start,
        end=current.end,
        revenue=current.revenue,
        visits=current.visits,
        average_check=current.average_check,
        no_shows=current.no_shows,
        no_show_rate=current.no_show_rate,
        cancellations=current.cancellations,
        new_clients=current.new_clients,
        deposits=current.deposits,
        tips_stars=current.tips_stars,
        load=current.load,
        by_day=[DayPoint(day=d, revenue=r, visits=v) for d, r, v in current.by_day],
        by_master=[
            MasterReport(
                master_id=m.master_id,
                revenue=m.revenue,
                visits=m.visits,
                load=m.load,
                rating=m.rating,
                reviews=m.reviews,
            )
            for m in current.by_master
        ],
        by_service=[
            ServiceReport(
                service_id=sid,
                name=Localized(ru=names[sid][0], en=names[sid][1]),
                visits=visits,
                revenue=revenue,
            )
            for sid, visits, revenue in current.by_service
        ],
        by_source=current.by_source,
        by_method=current.by_method,
        previous_revenue=previous.revenue,
        previous_visits=previous.visits,
    )
