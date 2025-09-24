from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from booking.infra.db.models import Business
from booking.services.errors import NotFoundError

BUSINESS_ID = 1


async def load_business(session: AsyncSession) -> Business:
    business = await session.get(Business, BUSINESS_ID)
    if business is None:
        raise NotFoundError("Business is not configured, run the seed first")
    return business


def business_tz(business: Business) -> ZoneInfo:
    return ZoneInfo(business.timezone)
