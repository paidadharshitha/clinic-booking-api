"""Compose resource routers and their shared error response contracts."""

from fastapi import APIRouter

from clinic_api.routers import bookings, clinics, slots
from clinic_api.schemas import ErrorResponse

router = APIRouter(
    responses={
        404: {"model": ErrorResponse, "description": "Resource not found"},
        409: {
            "model": ErrorResponse,
            "description": "Booking or cancellation conflicts with state",
        },
        422: {"model": ErrorResponse, "description": "Invalid input"},
        503: {"model": ErrorResponse, "description": "Database busy or unavailable; retry shortly"},
    }
)
router.include_router(clinics.router)
router.include_router(slots.router)
router.include_router(bookings.router)
