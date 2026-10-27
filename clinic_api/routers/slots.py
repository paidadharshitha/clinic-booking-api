"""Slot resources and compatibility routes for the original API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from clinic_api.dependencies import Service
from clinic_api.schemas import (
    Booking,
    BookingCreate,
    Slot,
    SlotCreate,
    SlotFilters,
    SlotPage,
)

router = APIRouter()


@router.post("/slots", response_model=Slot, status_code=201, tags=["Compatibility"])
def create_slot(data: SlotCreate, response: Response, service: Service) -> Slot:
    """Create a slot with clinic_id in the body; also available under /clinics/{id}/slots."""
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
    """Cancel an unoccupied slot. Repeated cancellation preserves history."""
    service.cancel_slot(slot_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/slots/{slot_id}/bookings", response_model=Booking, status_code=201, tags=["Compatibility"]
)
def book_slot(slot_id: UUID, data: BookingCreate, response: Response, service: Service) -> Booking:
    """Book a slot using a caller-supplied patient UUID; also available via POST /bookings."""
    booking = service.book_slot(slot_id, data)
    response.headers["Location"] = f"/bookings/{booking.id}"
    return booking
