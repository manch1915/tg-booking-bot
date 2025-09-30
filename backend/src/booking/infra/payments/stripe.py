from stripe import StripeClient


class StripeRefunder:
    """Refunds card deposits taken through Telegram's Stripe integration.

    Telegram hands over the Stripe charge id as `provider_payment_charge_id`.
    """

    def __init__(self, secret_key: str) -> None:
        self.client = StripeClient(secret_key)

    async def refund(self, *, provider_charge_id: str, amount: int, idempotency_key: str) -> None:
        await self.client.v1.refunds.create_async(
            params={"charge": provider_charge_id, "amount": amount},
            options={"idempotency_key": idempotency_key},
        )
