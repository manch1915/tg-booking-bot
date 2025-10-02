from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Button:
    text: str
    callback: str | None = None
    url: str | None = None
    web_app: str | None = None


@dataclass(frozen=True, slots=True)
class OutgoingMessage:
    chat_id: int
    text: str
    buttons: list[list[Button]] = field(default_factory=list)


class DeliveryError(Exception):
    def __init__(self, reason: str, *, permanent: bool, retry_after: float | None = None) -> None:
        super().__init__(reason)
        self.permanent = permanent
        self.retry_after = retry_after


class Messenger(Protocol):
    async def send(self, message: OutgoingMessage) -> None: ...
