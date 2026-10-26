"""Thin HTTP routes; all booking decisions live in the service."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

from clinic_api.models import (
    MAX_OFFSET,
    Booking,
    BookingCreate,
    Clinic,
    ClinicCreate,
    ClinicPage,
    ErrorResponse,
    Slot,
    SlotCreate,
    SlotFilters,
    SlotPage,
)
from clinic_api.service import BookingService

router = APIRouter(
    responses={
        404: {"model": ErrorResponse, "description": "Resource not found"},
        409: {
            "model": ErrorResponse,
            "description": "Booking or cancellation conflicts with state",
        },
        422: {"model": ErrorResponse, "description": "Invalid input"},
        503: {"model": ErrorResponse, "description": "Database busy; retry after 1 second"},
    }
)


def get_service(request: Request) -> BookingService:
    return request.app.state.service


Service = Annotated[BookingService, Depends(get_service)]


@router.post("/clinics", response_model=Clinic, status_code=201, tags=["Clinics"])
def create_clinic(data: ClinicCreate, response: Response, service: Service) -> Clinic:
    clinic = service.create_clinic(data)
    response.headers["Location"] = f"/clinics/{clinic.id}"
    return clinic


@router.get("/clinics", response_model=ClinicPage, tags=["Clinics"])
def list_clinics(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ClinicPage:
    return service.list_clinics(limit, offset)


@router.get("/clinics/{clinic_id}", response_model=Clinic, tags=["Clinics"])
def get_clinic(clinic_id: UUID, service: Service) -> Clinic:
    return service.get_clinic(clinic_id)


@router.post("/slots", response_model=Slot, status_code=201, tags=["Slots"])
def create_slot(data: SlotCreate, response: Response, service: Service) -> Slot:
    """Publish a future slot for an existing clinic; timestamps must include a timezone."""
    slot = service.create_slot(data)
    response.headers["Location"] = f"/slots/{slot.id}"
    return slot


@router.get("/slots", response_model=SlotPage, tags=["Slots"])
def list_slots(filters: Annotated[SlotFilters, Query()], service: Service) -> SlotPage:
    """List by start time, then ID. Time bounds are inclusive from and exclusive before."""
    return service.list_slots(filters)


@router.get("/slots/{slot_id}", response_model=Slot, tags=["Slots"])
def get_slot(slot_id: UUID, service: Service) -> Slot:
    return service.get_slot(slot_id)


@router.delete("/slots/{slot_id}", status_code=204, tags=["Slots"])
def cancel_slot(slot_id: UUID, service: Service) -> Response:
    """Cancel an unoccupied slot. Repeated cancellation succeeds without changing history."""
    service.cancel_slot(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/slots/{slot_id}/bookings", response_model=Booking, status_code=201, tags=["Bookings"]
)
def book_slot(slot_id: UUID, data: BookingCreate, response: Response, service: Service) -> Booking:
    """Atomically book an available, future slot. At most one request can succeed."""
    booking = service.book_slot(slot_id, data)
    response.headers["Location"] = f"/bookings/{booking.id}"
    return booking


@router.get("/bookings/{booking_id}", response_model=Booking, tags=["Bookings"])
def get_booking(booking_id: UUID, service: Service) -> Booking:
    return service.get_booking(booking_id)


@router.delete("/bookings/{booking_id}", status_code=204, tags=["Bookings"])
def cancel_booking(booking_id: UUID, service: Service) -> Response:
    """Cancel a booking and release the slot atomically. Safe to repeat."""
    service.cancel_booking(booking_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
