"""Domain exceptions. The API layer maps each one to an HTTP status in a single place."""


class DomainError(Exception):
    """Base class: an operation was refused for a business reason."""


class NotFoundError(DomainError):
    """The referenced object does not exist (or is invisible to the caller)."""


class ConflictError(DomainError):
    """The request conflicts with the current state (stale version, duplicate, ...)."""


class RuleViolationError(DomainError):
    """The request breaks a business rule (e.g. a node from another project)."""


class AuthenticationRequiredError(DomainError):
    """The caller must log in first."""


class PermissionDeniedError(DomainError):
    """The caller is known but not allowed to do this."""


class PasswordChangeRequiredError(PermissionDeniedError):
    """The account must set a new password before doing anything else."""


class InvalidCredentialsError(DomainError):
    """Login failed. Deliberately vague: never reveal whether the username exists."""


class TooManyAttemptsError(DomainError):
    """Too many failed logins; try again later."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class StaleVersionError(ConflictError):
    """The object changed since the caller loaded it (optimistic locking)."""
