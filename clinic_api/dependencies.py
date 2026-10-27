"""FastAPI dependency wiring for application-scoped services."""

from typing import Annotated

from fastapi import Depends, Request

from clinic_api.services.booking_service import BookingService


def get_service(request: Request) -> BookingService:
    return request.app.state.service


Service = Annotated[BookingService, Depends(get_service)]
