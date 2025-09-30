from aiogram import Bot
from aiogram.types import LabeledPrice

from booking.services.payments import Invoice


class AiogramInvoiceGateway:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def create_invoice_link(self, invoice: Invoice) -> str:
        return await self.bot.create_invoice_link(
            title=invoice.title[:32],
            description=invoice.description[:255],
            payload=invoice.payload,
            currency=invoice.currency,
            prices=[LabeledPrice(label=invoice.title[:32], amount=invoice.amount)],
            provider_token=invoice.provider_token,
            photo_url=invoice.photo_url,
        )

    async def refund_stars(self, *, user_id: int, telegram_charge_id: str) -> None:
        await self.bot.refund_star_payment(
            user_id=user_id, telegram_payment_charge_id=telegram_charge_id
        )
