"""Translate application errors once at the HTTP boundary."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


class AppError(Exception):
    status, code, error_code = 400, "error", "SYS_002"

    def __init__(self, message: str = "", *, field: str | None = None):
        super().__init__(message or self.code)
        self.field = field


class Invalid(AppError):
    status, code, error_code = 422, "invalid_request", "REQ_001"


class Unauthorized(AppError):
    status, code = 401, "unauthorized"


class Forbidden(AppError):
    status, code = 403, "forbidden"


class NotFound(AppError):
    status, code = 404, "not_found"


class Conflict(AppError):
    status, code = 409, "conflict"


class Unavailable(AppError):
    status, code = 503, "unavailable"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def on_app_error(_: Request, e: AppError) -> JSONResponse:
        body = {"code": e.code, "error_code": e.error_code}
        if e.field:
            body["field"] = e.field
        return JSONResponse(body, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def on_validation(_: Request, e: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"code": "invalid_request", "error_code": "REQ_001"}, status_code=422
        )

    @app.exception_handler(Exception)
    async def on_unexpected(request: Request, e: Exception) -> JSONResponse:
        # Do not log exception values: provider failures may contain credentials.
        log.error("Unhandled %s at %s", type(e).__name__, request.url.path)
        return JSONResponse(
            {"code": "internal_error", "error_code": "SYS_002"}, status_code=500
        )
