"""Fills the database with the demo barbershop.

python -m booking.seed            # wipe and seed
python -m booking.seed --if-empty # seed only a fresh database (used by docker compose)
"""

import argparse
import asyncio
import logging
import random
import secrets
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from booking import demo_data as demo
from booking.config import Settings, get_settings
from booking.domain.availability import DaySchedule, Interval, free_slots
from booking.domain.enums import (
    AdminRole,
    BonusKind,
    BookingSource,
    BookingStatus,
    Language,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    Segment,
    WaitlistStatus,
)
from booking.domain.policies import cashback_for, deposit_for, max_bonus_spend
from booking.infra.db.models import (
    AdminUser,
    Base,
    BonusTransaction,
    Booking,
    BreakRule,
    Broadcast,
    Business,
    Category,
    Client,
    Master,
    MasterService,
    Payment,
    Review,
    Service,
    TimeOff,
    WaitlistEntry,
    WorkingHours,
)
from booking.infra.db.session import make_engine, make_sessionmaker
from booking.services.auth import hash_password
from booking.services.business import BUSINESS_ID
from booking.services.clients import new_referral_code

log = logging.getLogger(__name__)

HISTORY_DAYS = 75
FUTURE_DAYS = 14
NO_PRICE_DELTA = {"wash-style", "face-care", "kids-cut"}


class DemoSeeder:
    def __init__(self, session: AsyncSession, settings: Settings, now: datetime) -> None:
        self.session = session
        self.settings = settings
        self.now = now
        self.rng = random.Random(2026)
        self.tz = ZoneInfo(demo.BUSINESS["timezone"])
        self.services: dict[str, Service] = {}
        self.masters: dict[str, Master] = {}
        self.offers: dict[str, list[tuple[Service, int, int]]] = {}
        self.clients: list[Client] = []
        self.weights: list[int] = []
        self.days_off: set[tuple[str, date]] = set()

    async def run(self) -> None:
        await self._business()
        await self._catalog()
        await self._masters()
        await self._admin()
        await self._clients()
        await self._bookings()
        await self._extras()
        await self._sync_balances()

    async def _business(self) -> None:
        self.session.add(Business(id=BUSINESS_ID, **demo.BUSINESS))
        await self.session.flush()

    async def _catalog(self) -> None:
        categories = {}
        for sort, (slug, ru, en) in enumerate(demo.CATEGORIES):
            categories[slug] = Category(name_ru=ru, name_en=en, sort=sort)
            self.session.add(categories[slug])
        await self.session.flush()
        for sort, row in enumerate(demo.SERVICES):
            slug, cat, ru, en, minutes, price, popular, desc_ru, desc_en = row
            service = Service(
                category_id=categories[cat].id,
                name_ru=ru,
                name_en=en,
                description_ru=desc_ru,
                description_en=desc_en,
                duration_minutes=minutes,
                price=price,
                photo_url=demo.service_photo(slug),
                is_popular=popular,
                sort=sort,
            )
            self.services[slug] = service
            self.session.add(service)
        await self.session.flush()

    async def _masters(self) -> None:
        for sort, row in enumerate(demo.MASTERS):
            slug, name, name_en, title_ru, title_en, color, bio_ru, bio_en, delta, scope = row
            master = Master(
                name=name,
                name_en=name_en,
                title_ru=title_ru,
                title_en=title_en,
                bio_ru=bio_ru,
                bio_en=bio_en,
                color=color,
                photo_url=demo.master_photo(slug),
                link_token=secrets.token_urlsafe(12),
                sort=sort,
            )
            self.masters[slug] = master
            self.session.add(master)
            await self.session.flush()

            slugs = list(self.services) if scope == "all" else list(scope)
            self.offers[slug] = []
            for service_slug in slugs:
                service = self.services[service_slug]
                price = (
                    None if service_slug in NO_PRICE_DELTA or not delta else service.price + delta
                )
                self.session.add(
                    MasterService(master_id=master.id, service_id=service.id, price=price)
                )
                self.offers[slug].append(
                    (service, price or service.price, service.duration_minutes)
                )

            for weekday, (start, end) in demo.SCHEDULES[slug].items():
                self.session.add(
                    WorkingHours(
                        master_id=master.id, weekday=weekday, start_time=start, end_time=end
                    )
                )
                lunch_start, lunch_end = demo.LUNCH[slug]
                self.session.add(
                    BreakRule(
                        master_id=master.id,
                        weekday=weekday,
                        start_time=lunch_start,
                        end_time=lunch_end,
                    )
                )
        await self.session.flush()

        # Ani is off for two days next week, Davit leaves early on Friday.
        today = self.now.astimezone(self.tz).date()
        next_wed = today + timedelta(days=(2 - today.weekday()) % 7 + 7)
        self.days_off = {("ani", next_wed), ("ani", next_wed + timedelta(days=1))}
        self.session.add(
            TimeOff(
                master_id=self.masters["ani"].id,
                starts_at=datetime.combine(next_wed, time(0), tzinfo=self.tz),
                ends_at=datetime.combine(next_wed + timedelta(days=2), time(0), tzinfo=self.tz),
                reason="Отпуск",
            )
        )
        friday = today + timedelta(days=(4 - today.weekday()) % 7)
        self.session.add(
            TimeOff(
                master_id=self.masters["davit"].id,
                starts_at=datetime.combine(friday, time(17), tzinfo=self.tz),
                ends_at=datetime.combine(friday, time(20), tzinfo=self.tz),
                reason="Семинар",
            )
        )
        await self.session.flush()

    async def _admin(self) -> None:
        self.session.add(
            AdminUser(
                email=self.settings.demo_admin_email,
                name="Карина Арутюнян",
                password_hash=hash_password(self.settings.demo_admin_password.get_secret_value()),
                role=AdminRole.OWNER,
            )
        )

    async def _clients(self) -> None:
        names: set[str] = set()
        while len(names) < demo.CLIENT_COUNT:
            if self.rng.random() < 0.7:
                names.add(
                    f"{self.rng.choice(demo.FIRST_NAMES_RU)} {self.rng.choice(demo.LAST_NAMES_RU)}"
                )
            else:
                names.add(
                    f"{self.rng.choice(demo.FIRST_NAMES_EN)} {self.rng.choice(demo.LAST_NAMES_EN)}"
                )
        for name in sorted(names):
            is_ru = any("а" <= ch.lower() <= "я" for ch in name)
            digits = str(self.rng.randint(10_000_000, 99_999_999))
            client = Client(
                name=name,
                phone=f"+374 {digits[:2]} {digits[2:5]} {digits[5:]}",
                language=Language.RU if is_ru else Language.EN,
                referral_code=new_referral_code(),
                created_at=self.now - timedelta(days=self.rng.randint(25, 400)),
            )
            self.session.add(client)
            self.clients.append(client)
        await self.session.flush()
        for index, client in enumerate(self.clients):
            if index > 10 and self.rng.random() < 0.12:
                client.referred_by_id = self.rng.choice(self.clients[:10]).id
            self._bonus(client, 300, BonusKind.WELCOME, when=client.created_at)
        # A few regulars come far more often than the rest, like in any real shop.
        self.weights = [2 if i % 9 == 0 else 1 for i in range(len(self.clients))]

    async def _bookings(self) -> None:
        today = self.now.astimezone(self.tz).date()
        for offset in range(-HISTORY_DAYS, FUTURE_DAYS):
            day = today + timedelta(days=offset)
            for slug, master in self.masters.items():
                hours = demo.SCHEDULES[slug].get(day.weekday())
                if hours is None or (slug, day) in self.days_off:
                    continue
                await self._fill_day(slug, master, day, offset, hours)
        await self.session.flush()

    async def _fill_day(
        self, slug: str, master: Master, day: date, offset: int, hours: tuple[time, time]
    ) -> None:
        # Busy past, a full next few days, thinner further ahead. Looks like a real shop.
        if offset < 0:
            load = self.rng.uniform(0.6, 0.85)
        else:
            load = max(0.12, 0.55 - offset * 0.035) * self.rng.uniform(0.75, 1.1)
        schedule = DaySchedule(work=hours, breaks=[demo.LUNCH[slug]])
        shift_minutes = (
            datetime.combine(day, hours[1]) - datetime.combine(day, hours[0])
        ).seconds / 60
        busy: list[Interval] = []
        booked_minutes = 0
        for _ in range(30):
            if booked_minutes >= shift_minutes * load:
                break
            service, price, minutes = self.rng.choice(self.offers[slug])
            slots = free_slots(
                day=day,
                tz=self.tz,
                schedule=schedule,
                busy=busy,
                duration=timedelta(minutes=minutes),
                step=timedelta(minutes=15),
                not_before=datetime(2000, 1, 1, tzinfo=UTC),
            )
            if not slots:
                continue
            start = self.rng.choice(slots)
            busy.append(Interval(start, start + timedelta(minutes=minutes)))
            booked_minutes += minutes
            self._booking(master, service, price, start, minutes)

    def _booking(
        self, master: Master, service: Service, price: int, start: datetime, minutes: int
    ) -> None:
        client = self.rng.choices(self.clients, weights=self.weights)[0]
        end = start + timedelta(minutes=minutes)
        roll = self.rng.random()
        if end <= self.now:
            status = (
                BookingStatus.COMPLETED
                if roll < 0.9
                else BookingStatus.NO_SHOW
                if roll < 0.95
                else BookingStatus.CANCELLED
            )
        else:
            status = BookingStatus.CONFIRMED if roll < 0.93 else BookingStatus.CANCELLED
        method = self.rng.choices(
            [PaymentMethod.CARD, PaymentMethod.STARS, PaymentMethod.ON_SITE], weights=[5, 2, 3]
        )[0]
        source = self.rng.choices(
            [BookingSource.MINIAPP, BookingSource.BOT, BookingSource.ADMIN], weights=[5, 3, 2]
        )[0]
        if source is BookingSource.ADMIN:
            method = PaymentMethod.ON_SITE
        bonus = 0
        if self.rng.random() < 0.15:
            bonus = max_bonus_spend(price, client.bonus_balance, 30)
        deposit = 0 if method is PaymentMethod.ON_SITE else deposit_for(price, 30)
        created = start - timedelta(days=self.rng.randint(1, 9), hours=self.rng.randint(0, 10))
        booking = Booking(
            client=client,
            master=master,
            service=service,
            starts_at=start,
            ends_at=end,
            status=status,
            source=source,
            payment_method=method,
            price=price,
            deposit=deposit,
            bonus_spent=bonus,
            created_at=min(created, self.now - timedelta(minutes=30)),
        )
        if status is BookingStatus.CANCELLED:
            booking.cancelled_at = booking.created_at + timedelta(hours=self.rng.randint(1, 20))
            booking.cancel_reason = self.rng.choice(["", "Планы поменялись", "Заболел"])
        if status is BookingStatus.COMPLETED:
            booking.completed_at = end
        self.session.add(booking)

        if bonus:
            self._bonus(client, -bonus, BonusKind.SPEND, booking=booking, when=booking.created_at)
            if status is BookingStatus.CANCELLED:
                self._bonus(
                    client, bonus, BonusKind.RETURN, booking=booking, when=booking.cancelled_at
                )
        if deposit:
            refunded = status is BookingStatus.CANCELLED
            stars = method is PaymentMethod.STARS
            self.session.add(
                Payment(
                    booking=booking,
                    provider=PaymentProvider.DEMO,
                    purpose=PaymentPurpose.DEPOSIT,
                    status=PaymentStatus.REFUNDED if refunded else PaymentStatus.PAID,
                    amount=deposit * self.settings.stars_per_usd // 100 if stars else deposit,
                    currency="XTR" if stars else "USD",
                    amount_base=deposit,
                    payload=f"seed_{secrets.token_hex(10)}",
                    paid_at=booking.created_at + timedelta(minutes=2),
                    refunded_at=booking.cancelled_at if refunded else None,
                    created_at=booking.created_at,
                )
            )
        if status is BookingStatus.COMPLETED:
            self._bonus(
                client,
                cashback_for(price - bonus, 5),
                BonusKind.CASHBACK,
                booking=booking,
                when=end,
            )
            if self.rng.random() < 0.55:
                self._review(booking, client, master)

    def _review(self, booking: Booking, client: Client, master: Master) -> None:
        rating = self.rng.choices([5, 4, 3], weights=[78, 18, 4])[0]
        pool = demo.REVIEWS_RU if client.language is Language.RU else demo.REVIEWS_EN
        comment = self.rng.choice(pool) if self.rng.random() < 0.7 else ""
        self.session.add(
            Review(
                booking=booking,
                client=client,
                master_id=master.id,
                rating=rating,
                comment=comment,
                created_at=booking.ends_at + timedelta(hours=self.rng.randint(1, 30)),
            )
        )

    def _bonus(
        self,
        client: Client,
        amount: int,
        kind: BonusKind,
        *,
        booking: Booking | None = None,
        when: datetime | None = None,
    ) -> None:
        if not amount:
            return
        client.bonus_balance = (client.bonus_balance or 0) + amount
        tx = BonusTransaction(client_id=client.id, kind=kind, amount=amount)
        if booking is not None:
            tx.booking = booking
        if when is not None:
            tx.created_at = when
        self.session.add(tx)

    async def _extras(self) -> None:
        today = self.now.astimezone(self.tz).date()
        for days, client in ((1, self.clients[3]), (2, self.clients[57]), (2, self.clients[98])):
            self.session.add(
                WaitlistEntry(
                    client_id=client.id,
                    service_id=self.services["skin-fade"].id,
                    master_id=self.masters["artur"].id if days == 1 else None,
                    day=today + timedelta(days=days),
                    status=WaitlistStatus.WAITING,
                )
            )
        self.session.add_all(
            [
                Broadcast(
                    segment=Segment.INACTIVE_30,
                    text_ru="Давно не виделись! До конца месяца комплекс «Стрижка и борода» "
                    "на 5 долларов дешевле. Записаться можно прямо здесь.",
                    text_en="Long time no see! Haircut and beard is 5 dollars off until the end "
                    "of the month. Book right here.",
                    recipients=14,
                    created_by="Карина Арутюнян",
                    created_at=self.now - timedelta(days=9),
                ),
                Broadcast(
                    segment=Segment.ALL,
                    text_ru="В субботу работаем до 22:00. Свободные окна смотрите в приложении.",
                    text_en="We're open until 10 pm on Saturday. Check free slots in the app.",
                    recipients=45,
                    created_by="Карина Арутюнян",
                    created_at=self.now - timedelta(days=3),
                ),
            ]
        )
        await self.session.flush()

    async def _sync_balances(self) -> None:
        await self.session.execute(
            text(
                "UPDATE client SET bonus_balance = GREATEST(0, COALESCE("
                "(SELECT SUM(amount) FROM bonus_transaction t WHERE t.client_id = client.id), 0))"
            )
        )


async def wipe(session: AsyncSession) -> None:
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    await session.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


async def seed(session: AsyncSession, settings: Settings, now: datetime | None = None) -> None:
    await wipe(session)
    await DemoSeeder(session, settings, now or datetime.now(UTC)).run()


async def main(if_empty: bool) -> None:
    settings = get_settings()
    if not settings.demo_mode:
        # The seed creates a well-known admin login, so it only runs for the public demo.
        raise SystemExit("Demo data is only loaded with DEMO_MODE=true")
    engine = make_engine(settings.database_url)
    factory = make_sessionmaker(engine)
    async with factory() as session, session.begin():
        if if_empty and await session.get(Business, BUSINESS_ID) is not None:
            log.info("Database already has data, skipping seed")
        else:
            await seed(session, settings)
            log.info("Demo data loaded")
    await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--if-empty", action="store_true")
    asyncio.run(main(parser.parse_args().if_empty))
