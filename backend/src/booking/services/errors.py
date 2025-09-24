class DomainError(Exception):
    code = "domain_error"

    def __init__(self, message: str = "", **details: object) -> None:
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details


class NotFoundError(DomainError):
    code = "not_found"


class SlotUnavailableError(DomainError):
    code = "slot_unavailable"


class PolicyError(DomainError):
    code = "policy_violation"


class InvalidStateError(DomainError):
    code = "invalid_state"


class PaymentError(DomainError):
    code = "payment_error"


class AuthError(DomainError):
    code = "unauthorized"
