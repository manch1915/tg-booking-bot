from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from booking.domain.enums import BonusKind
from booking.infra.db.models import BonusTransaction, Client
from booking.services.errors import PolicyError


class BonusService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def change(
        self,
        client: Client,
        amount: int,
        kind: BonusKind,
        *,
        booking_id: int | None = None,
        comment: str = "",
    ) -> BonusTransaction | None:
        if amount == 0:
            return None
        # Atomic update keeps the cached balance correct under concurrent changes.
        result = await self.session.execute(
            update(Client)
            .where(Client.id == client.id, Client.bonus_balance + amount >= 0)
            .values(bonus_balance=Client.bonus_balance + amount)
            .returning(Client.bonus_balance)
        )
        new_balance = result.scalar_one_or_none()
        if new_balance is None:
            raise PolicyError("Not enough bonuses", balance=client.bonus_balance)
        client.bonus_balance = new_balance
        tx = BonusTransaction(
            client_id=client.id, booking_id=booking_id, kind=kind, amount=amount, comment=comment
        )
        self.session.add(tx)
        return tx
