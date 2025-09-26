from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-secret-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"), env_file_encoding="utf-8", extra="ignore"
    )

    env: Literal["dev", "test", "prod"] = "dev"
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://booking:booking@localhost:5447/booking"
    redis_url: str = "redis://localhost:6387/0"

    # Public URL where the web build is served, used for Mini App buttons and links.
    public_url: str = "http://localhost:5177"

    bot_token: SecretStr | None = None
    bot_username: str = "brass_blade_demo_bot"

    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_ttl_minutes: int = 60 * 24 * 7

    # Card payments go through Telegram invoices. The token comes from BotFather
    # (Stripe TEST or YooKassa TEST). In demo mode a missing token falls back to a fake checkout.
    payment_provider_token: SecretStr | None = None
    payment_currency: str = "USD"
    # Optional: lets refunds of card deposits go through the Stripe API automatically.
    stripe_secret_key: SecretStr | None = None

    stars_per_usd: int = Field(default=50, ge=1)
    # Public demo charges a symbolic amount of Stars regardless of the deposit size.
    stars_fixed_price: int | None = None

    # Public demo: fake checkout, one-click admin login, demo guests and a nightly data reset.
    demo_mode: bool = False
    demo_admin_email: str = "owner@brassblade.demo"
    demo_admin_password: SecretStr = SecretStr("demo-owner-2026")

    cors_origins: list[str] = ["http://localhost:5177"]

    @model_validator(mode="after")
    def _check_secrets(self) -> Self:
        secret = self.jwt_secret.get_secret_value()
        if self.env == "prod" and (secret == DEV_JWT_SECRET or len(secret) < 32):
            raise ValueError("Set JWT_SECRET to a random string of at least 32 characters")
        return self

    @property
    def telegram_enabled(self) -> bool:
        return self.bot_token is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
