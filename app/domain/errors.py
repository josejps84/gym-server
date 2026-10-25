class DomainError(Exception):
    """A rule was broken. `code` is a stable, machine-readable key the app can translate."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code


class NotFound(DomainError):
    pass


class Forbidden(DomainError):
    pass


class Conflict(DomainError):
    pass


class Invalid(DomainError):
    pass
