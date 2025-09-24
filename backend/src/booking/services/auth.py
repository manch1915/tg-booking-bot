import time
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qsl

import jwt
from aiogram.utils.web_app import WebAppInitData, safe_parse_webapp_init_data
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from booking.services.errors import AuthError

INIT_DATA_MAX_AGE = 60 * 60 * 24

Audience = Literal["client", "admin"]
_hasher = PasswordHasher()


@dataclass(frozen=True, slots=True)
class TokenSubject:
    audience: Audience
    id: int


class TokenIssuer:
    def __init__(self, secret: str, ttl_minutes: int) -> None:
        self.secret = secret
        self.ttl = ttl_minutes * 60

    def issue(self, audience: Audience, subject_id: int) -> str:
        now = int(time.time())
        claims = {"sub": str(subject_id), "aud": audience, "iat": now, "exp": now + self.ttl}
        return jwt.encode(claims, self.secret, algorithm="HS256")

    def verify(self, token: str, audience: Audience) -> TokenSubject:
        try:
            claims = jwt.decode(token, self.secret, algorithms=["HS256"], audience=audience)
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired token") from exc
        return TokenSubject(audience=audience, id=int(claims["sub"]))


def verify_init_data(bot_token: str, init_data: str, *, now: float | None = None) -> WebAppInitData:
    try:
        data = safe_parse_webapp_init_data(bot_token, init_data)
    except ValueError as exc:
        raise AuthError("Invalid init data") from exc
    auth_date = int(dict(parse_qsl(init_data)).get("auth_date", "0"))
    if (now or time.time()) - auth_date > INIT_DATA_MAX_AGE:
        raise AuthError("Init data is too old")
    if data.user is None:
        raise AuthError("Init data has no user")
    return data


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
