from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from booking.infra.db.models import Category, Master, MasterService, Review, Service
from booking.services.errors import NotFoundError


@dataclass(frozen=True, slots=True)
class MasterOffer:
    """A master who performs a service, with the price and duration that apply to them."""

    master: Master
    price: int
    duration_minutes: int
    rating: float | None
    reviews: int


class CatalogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def categories(self) -> list[Category]:
        rows = await self.session.scalars(
            select(Category).options(selectinload(Category.services)).order_by(Category.sort)
        )
        categories = list(rows)
        for category in categories:
            category.services.sort(key=lambda s: (s.sort, s.id))
        return categories

    async def service(self, service_id: int) -> Service:
        service = await self.session.get(Service, service_id)
        if service is None or not service.is_active:
            raise NotFoundError("Service not found")
        return service

    async def masters(self, *, active_only: bool = True) -> list[Master]:
        query = select(Master).order_by(Master.sort, Master.id)
        if active_only:
            query = query.where(Master.is_active)
        return list(await self.session.scalars(query))

    async def master(self, master_id: int) -> Master:
        master = await self.session.get(Master, master_id)
        if master is None or not master.is_active:
            raise NotFoundError("Master not found")
        return master

    async def ratings(self) -> dict[int, tuple[float, int]]:
        rows = await self.session.execute(
            select(Review.master_id, func.avg(Review.rating), func.count(Review.id)).group_by(
                Review.master_id
            )
        )
        return {master_id: (float(avg), int(count)) for master_id, avg, count in rows.all()}

    async def offers(self, service_id: int) -> list[MasterOffer]:
        service = await self.service(service_id)
        rows = await self.session.execute(
            select(MasterService, Master)
            .join(Master, Master.id == MasterService.master_id)
            .where(MasterService.service_id == service_id, Master.is_active)
            .order_by(Master.sort, Master.id)
        )
        ratings = await self.ratings()
        offers = []
        for link, master in rows.all():
            rating, count = ratings.get(master.id, (None, 0))
            offers.append(
                MasterOffer(
                    master=master,
                    price=link.price if link.price is not None else service.price,
                    duration_minutes=link.duration_minutes or service.duration_minutes,
                    rating=round(rating, 2) if rating is not None else None,
                    reviews=count,
                )
            )
        return offers

    async def offer(self, service_id: int, master_id: int) -> MasterOffer:
        for offer in await self.offers(service_id):
            if offer.master.id == master_id:
                return offer
        raise NotFoundError("This master does not perform the service")
