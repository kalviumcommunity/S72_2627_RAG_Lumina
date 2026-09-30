"""Typed application errors and their JSON handlers."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import get_logger

log = get_logger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, code: str | None = None, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_failed"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


def _body(code: str, message: str, details: object | None = None) -> dict[str, object]:
    error: dict[str, object] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        headers = {"Retry-After": "60"} if isinstance(exc, RateLimitedError) else None
        return JSONResponse(_body(exc.code, exc.message, exc.details), exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo request input back (it may contain a raw question with identifiers).
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]
        return JSONResponse(_body("validation_failed", "Request validation failed", details), 422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(_body("internal_error", "An unexpected error occurred"), 500)
