"""Booking creation, discovery, and cancellation."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, status

from clinic_api.dependencies import Service
from clinic_api.schemas import AppointmentCreate, Booking, BookingFilters, BookingPage

router = APIRouter(tags=["Bookings"])


@router.post("/bookings", response_model=Booking, status_code=201)
def create_booking(data: AppointmentCreate, response: Response, service: Service) -> Booking:
    """Atomically book a future slot with the patient's name and email."""
    booking = service.book_slot(data.slot_id, data)
    response.headers["Location"] = f"/bookings/{booking.id}"
    return booking


@router.get("/bookings", response_model=BookingPage)
def list_bookings(filters: Annotated[BookingFilters, Query()], service: Service) -> BookingPage:
    """List bookings with optional clinic, slot, patient, and status filters."""
    return service.list_bookings(filters)


@router.get("/bookings/{booking_id}", response_model=Booking)
def get_booking(booking_id: UUID, service: Service) -> Booking:
    return service.get_booking(booking_id)


@router.delete("/bookings/{booking_id}", status_code=204)
def cancel_booking(booking_id: UUID, service: Service) -> Response:
    """Cancel a booking and release its slot atomically. Safe to repeat."""
    service.cancel_booking(booking_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
