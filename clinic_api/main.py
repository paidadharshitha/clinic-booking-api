"""Application factory, lifecycle, and consistent error responses."""

import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from clinic_api.api import router
from clinic_api.database import Database
from clinic_api.errors import DomainError
from clinic_api.schemas import ErrorBody, ErrorDetail, ErrorResponse
from clinic_api.services.booking_service import BookingService, utc_now

logger = logging.getLogger(__name__)


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or []))
    return JSONResponse(status_code=status_code, content=payload.model_dump(), headers=headers)


def create_app(
    database_path: str | Path | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
    database_timeout: float = 5.0,
) -> FastAPI:
    database = Database(
        database_path
        if database_path is not None
        else os.getenv("BOOKING_DB_PATH", "data/bookings.db"),
        timeout=database_timeout,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        database.initialize()
        try:
            yield
        finally:
            database.dispose()

    application = FastAPI(
        title="Clinic Booking API",
        version="2.0.0",
        description=(
            "Publish clinic appointment slots, book them atomically, and cancel safely. "
            "Every timestamp includes a timezone; responses use UTC. "
            "A slot can have at most one confirmed booking."
        ),
        lifespan=lifespan,
        openapi_tags=[
            {"name": "Clinics", "description": "Register and retrieve clinics."},
            {"name": "Slots", "description": "Publish, find, and cancel appointment slots."},
            {"name": "Bookings", "description": "Book a slot and manage its booking."},
            {"name": "Health", "description": "Service and database readiness."},
            {
                "name": "Compatibility",
                "description": "Original endpoints retained for existing clients.",
            },
        ],
    )
    application.state.database = database
    application.state.service = BookingService(database, clock or utc_now)

    @application.exception_handler(DomainError)
    async def handle_domain_error(request: Request, error: DomainError) -> JSONResponse:
        return error_response(
            error.status_code,
            error.code,
            error.message,
            headers={"Retry-After": "1"} if error.status_code == 503 else None,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        # Do not echo request bodies or validation internals in error responses.
        return error_response(
            422,
            "VALIDATION_ERROR",
            "Check the highlighted fields and try again.",
            details=[
                ErrorDetail(
                    field=".".join(str(part) for part in item["loc"]),
                    message=item["msg"],
                    type=item["type"],
                )
                for item in error.errors()
            ],
        )

    @application.exception_handler(HTTPException)
    async def handle_http_error(request: Request, error: HTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(error.status_code, "HTTP_ERROR")
        return error_response(error.status_code, code, str(error.detail), headers=error.headers)

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, error: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=error)
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")

    @application.get(
        "/health",
        tags=["Health"],
        responses={503: {"model": ErrorResponse, "description": "Database unavailable"}},
    )
    def health() -> dict[str, str]:
        with database.connection() as connection:
            connection.exec_driver_sql("SELECT 1 FROM clinics LIMIT 1")
        return {"status": "ok"}

    application.include_router(router)
    return application


app = create_app()
