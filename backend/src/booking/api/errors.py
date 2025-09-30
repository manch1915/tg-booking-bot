from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from booking.services.errors import (
    AuthError,
    DomainError,
    InvalidStateError,
    NotFoundError,
    PaymentError,
    PolicyError,
    SlotUnavailableError,
)

STATUS = {
    AuthError: 401,
    NotFoundError: 404,
    SlotUnavailableError: 409,
    InvalidStateError: 409,
    PolicyError: 422,
    PaymentError: 402,
}


async def domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    status = next((code for cls, code in STATUS.items() if isinstance(exc, cls)), 400)
    details = {k: v for k, v in exc.details.items() if isinstance(v, str | int | float | bool)}
    return JSONResponse(
        status_code=status,
        content={"error": exc.code, "message": exc.message, "details": details},
    )


def install(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)
