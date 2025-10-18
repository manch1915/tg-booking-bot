import random
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.enums import (
    BonusKind,
    BookingSource,
    BookingStatus,
    Language,
    PaymentMethod,
)
from booking.domain.policies import cashback_for
from booking.infra.db.models import Booking, Client, MasterService, Service
from booking.services.bonuses import BonusService
from booking.services.business import load_business
from booking.services.clock import Clock

REFERRAL_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
RU_LIKE = {"ru", "uk", "be", "kk", "hy"}


@dataclass(frozen=True, slots=True)
class TelegramProfile:
    id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


def language_from_code(code: str | None) -> Language:
    if code is None or code.split("-")[0] in RU_LIKE:
        return Language.RU
    return Language.EN


def new_referral_code() -> str:
    return "".join(secrets.choice(REFERRAL_ALPHABET) for _ in range(8))


class ClientService:
    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        self.session = session
        self.clock = clock
        self.bonuses = BonusService(session)

    async def get(self, client_id: int) -> Client | None:
        return await self.session.get(Client, client_id)

    async def by_telegram(self, telegram_id: int) -> Client | None:
        return await self.session.scalar(select(Client).where(Client.telegram_id == telegram_id))

    async def from_telegram(
        self, profile: TelegramProfile, *, referral_code: str | None = None
    ) -> tuple[Client, bool]:
        client = await self.by_telegram(profile.id)
        name = " ".join(p for p in (profile.first_name, profile.last_name) if p).strip()
        if client is not None:
            client.username = profile.username
            return client, False

        referrer = None
        if referral_code:
            referrer = await self.session.scalar(
                select(Client).where(Client.referral_code == referral_code)
            )
        client = Client(
            telegram_id=profile.id,
            username=profile.username,
            name=name or "Telegram user",
            language=language_from_code(profile.language_code),
            referral_code=new_referral_code(),
            referred_by_id=referrer.id if referrer else None,
        )
        self.session.add(client)
        await self.session.flush()
        await self._welcome(client)
        return client, True

    async def create_demo_guest(self, language: Language) -> Client:
        number = random.randint(1000, 9999)
        label = "Гость" if language is Language.RU else "Guest"
        client = Client(
            name=f"{label} {number}",
            language=language,
            referral_code=new_referral_code(),
            is_demo_guest=True,
        )
        self.session.add(client)
        await self.session.flush()
        await self._welcome(client)
        await self._demo_history(client)
        return client

    async def update_profile(
        self,
        client: Client,
        *,
        name: str | None = None,
        phone: str | None = None,
        language: Language | None = None,
    ) -> Client:
        if name is not None and name.strip():
            client.name = name.strip()[:120]
        if phone is not None:
            client.phone = phone.strip()[:32] or None
        if language is not None:
            client.language = language
        await self.session.flush()
        return client

    async def stats(self, client: Client) -> dict[str, int]:
        visits = await self.session.scalar(
            select(func.count(Booking.id)).where(
                Booking.client_id == client.id, Booking.status == BookingStatus.COMPLETED
            )
        )
        invited = await self.session.scalar(
            select(func.count(Client.id)).where(Client.referred_by_id == client.id)
        )
        return {"visits": int(visits or 0), "invited": int(invited or 0)}

    async def _welcome(self, client: Client) -> None:
        business = await load_business(self.session)
        await self.bonuses.change(client, business.welcome_bonus, BonusKind.WELCOME)

    async def _demo_history(self, client: Client) -> None:
        """Two past visits so a fresh demo guest sees a profile with history and cashback."""
        business = await load_business(self.session)
        links = (
            await self.session.execute(
                select(MasterService, Service)
                .join(Service, Service.id == MasterService.service_id)
                .where(Service.is_active)
            )
        ).all()
        if not links:
            return
        now = self.clock.now().replace(minute=0, second=0, microsecond=0)
        for weeks_ago in (5, 2):
            link, service = random.choice(links)
            price = link.price if link.price is not None else service.price
            duration = link.duration_minutes or service.duration_minutes
            starts = now - timedelta(weeks=weeks_ago, hours=random.randint(1, 6))
            booking = Booking(
                client_id=client.id,
                master_id=link.master_id,
                service_id=service.id,
                starts_at=starts,
                ends_at=starts + timedelta(minutes=duration),
                status=BookingStatus.COMPLETED,
                source=BookingSource.MINIAPP,
                payment_method=PaymentMethod.ON_SITE,
                price=price,
                completed_at=starts + timedelta(minutes=duration),
            )
            self.session.add(booking)
            await self.session.flush()
            tx = await self.bonuses.change(
                client,
                cashback_for(price, business.cashback_percent),
                BonusKind.CASHBACK,
                booking_id=booking.id,
            )
            if tx is not None:
                tx.created_at = booking.ends_at
