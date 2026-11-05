"""Errors that business logic raises. The HTTP layer turns them into responses.

Services raise these instead of FastAPI's HTTPException, so business rules don't
depend on the web framework and can be called from anywhere (scripts, jobs, tests).
`main.py` registers one handler that renders every AppError as
`{"detail": "<message>"}` with the error's status code (same shape FastAPI uses).
"""


class AppError(Exception):
    """Base class. `status_code` is the matching HTTP status."""

    status_code = 400

    def __init__(
        self, message: str, *, status_code: int | None = None, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers
        if status_code is not None:
            self.status_code = status_code


class BadRequest(AppError):
    status_code = 400


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Invalid(AppError):
    """Input is well-formed but breaks a business rule (e.g. unknown unit)."""

    status_code = 422


class TooManyRequests(AppError):
    status_code = 429
