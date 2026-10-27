"""Appointment lifecycle rules using short SQLAlchemy transactions."""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import Label

from clinic_api import models, schemas
from clinic_api.database import Database
from clinic_api.errors import DomainError, not_found


def utc_now() -> datetime:
    return datetime.now(UTC)


def slot_selection(now: datetime) -> tuple[Select[tuple[models.Slot, str]], Label[str]]:
    occupied = (
        select(models.Booking.id)
        .where(models.Booking.slot_id == models.Slot.id, models.Booking.status == "confirmed")
        .exists()
    )
    availability = case(
        (models.Slot.status == "cancelled", "cancelled"),
        (occupied, "booked"),
        (models.Slot.starts_at <= now, "expired"),
        else_="available",
    ).label("availability")
    return select(models.Slot, availability), availability


def slot_response(slot: models.Slot, availability: str) -> schemas.Slot:
    return schemas.Slot(
        **{column.name: getattr(slot, column.name) for column in models.Slot.__table__.columns},
        availability=availability,
    )


class BookingService:
    def __init__(self, database: Database, clock: Callable[[], datetime] = utc_now) -> None:
        self.database = database
        self.clock = clock

    def create_clinic(self, data: schemas.ClinicCreate) -> schemas.Clinic:
        with self.database.session(write=True) as session:
            clinic = models.Clinic(
                id=str(uuid4()), name=data.name, address=data.address, created_at=self.clock()
            )
            session.add(clinic)
            session.flush()
            return schemas.Clinic.model_validate(clinic)

    @staticmethod
    def _clinic(session: Session, clinic_id: UUID) -> models.Clinic:
        clinic = session.get(models.Clinic, str(clinic_id))
        if clinic is None:
            raise not_found("clinic")
        return clinic

    def get_clinic(self, clinic_id: UUID) -> schemas.Clinic:
        with self.database.session() as session:
            return schemas.Clinic.model_validate(self._clinic(session, clinic_id))

    def list_clinics(self, limit: int, offset: int) -> schemas.ClinicPage:
        with self.database.session() as session:
            clinics = session.scalars(
                select(models.Clinic)
                .order_by(models.Clinic.created_at, models.Clinic.id)
                .limit(limit + 1)
                .offset(offset)
            ).all()
            return schemas.ClinicPage(
                items=[schemas.Clinic.model_validate(clinic) for clinic in clinics[:limit]],
                limit=limit,
                offset=offset,
                has_more=len(clinics) > limit,
            )

    def create_slot(self, data: schemas.SlotCreate) -> schemas.Slot:
        with self.database.session(write=True) as session:
            now = self.clock()
            if data.starts_at <= now:
                raise DomainError(422, "SLOT_IN_PAST", "starts_at must be in the future.")
            self._clinic(session, data.clinic_id)
            slot = models.Slot(
                id=str(uuid4()),
                clinic_id=str(data.clinic_id),
                starts_at=data.starts_at,
                ends_at=data.ends_at,
                created_at=now,
            )
            session.add(slot)
            session.flush()
            return slot_response(slot, "available")

    def get_slot(self, slot_id: UUID) -> schemas.Slot:
        with self.database.session() as session:
            return self._slot(session, slot_id, self.clock())[1]

    @staticmethod
    def _slot(session: Session, slot_id: UUID, now: datetime) -> tuple[models.Slot, schemas.Slot]:
        query, _ = slot_selection(now)
        result = session.execute(query.where(models.Slot.id == str(slot_id))).one_or_none()
        if result is None:
            raise not_found("slot")
        slot, availability = result
        return slot, slot_response(slot, availability)

    def list_slots(self, filters: schemas.SlotFilters) -> schemas.SlotPage:
        with self.database.session() as session:
            return self._list_slots(session, filters)

    def list_clinic_slots(self, clinic_id: UUID, filters: schemas.SlotFilters) -> schemas.SlotPage:
        with self.database.session() as session:
            self._clinic(session, clinic_id)
            return self._list_slots(session, filters.model_copy(update={"clinic_id": clinic_id}))

    def _list_slots(self, session: Session, filters: schemas.SlotFilters) -> schemas.SlotPage:
        query, availability = slot_selection(self.clock())
        if filters.clinic_id is not None:
            query = query.where(models.Slot.clinic_id == str(filters.clinic_id))
        if filters.availability is not None:
            query = query.where(availability == filters.availability)
        if filters.starts_from is not None:
            query = query.where(models.Slot.starts_at >= filters.starts_from)
        if filters.starts_before is not None:
            query = query.where(models.Slot.starts_at < filters.starts_before)
        rows = session.execute(
            query.order_by(models.Slot.starts_at, models.Slot.id)
            .limit(filters.limit + 1)
            .offset(filters.offset)
        ).all()
        return schemas.SlotPage(
            items=[slot_response(slot, status) for slot, status in rows[: filters.limit]],
            limit=filters.limit,
            offset=filters.offset,
            has_more=len(rows) > filters.limit,
        )

    def cancel_slot(self, slot_id: UUID) -> None:
        with self.database.session(write=True) as session:
            now = self.clock()
            record, slot = self._slot(session, slot_id, now)
            if slot.status == "cancelled":
                return
            if slot.availability == "booked":
                raise DomainError(
                    409,
                    "SLOT_HAS_BOOKING",
                    "Cancel the slot's active booking before cancelling it.",
                )
            record.status = "cancelled"
            record.cancelled_at = now

    def book_slot(
        self, slot_id: UUID, data: schemas.BookingCreate | schemas.AppointmentCreate
    ) -> schemas.Booking:
        with self.database.session(write=True) as session:
            now = self.clock()
            _, slot = self._slot(session, slot_id, now)
            if slot.status == "cancelled":
                raise DomainError(409, "SLOT_CANCELLED", "This slot has been cancelled.")
            if slot.availability == "booked":
                raise DomainError(409, "SLOT_ALREADY_BOOKED", "This slot already has a booking.")
            if slot.starts_at <= now:
                raise DomainError(409, "SLOT_STARTED", "This slot has already started.")
            booking = models.Booking(
                id=str(uuid4()),
                slot_id=str(slot_id),
                patient_id=str(data.patient_id),
                patient_name=data.patient_name,
                patient_email=str(data.patient_email) if data.patient_email is not None else None,
                created_at=now,
            )
            session.add(booking)
            try:
                session.flush()
            except IntegrityError as error:
                if str(error.orig) == "UNIQUE constraint failed: bookings.slot_id":
                    raise DomainError(
                        409, "SLOT_ALREADY_BOOKED", "This slot already has a booking."
                    ) from error
                raise
            return schemas.Booking.model_validate(booking)

    @staticmethod
    def _booking(session: Session, booking_id: UUID) -> models.Booking:
        booking = session.get(models.Booking, str(booking_id))
        if booking is None:
            raise not_found("booking")
        return booking

    def get_booking(self, booking_id: UUID) -> schemas.Booking:
        with self.database.session() as session:
            return schemas.Booking.model_validate(self._booking(session, booking_id))

    def list_bookings(self, filters: schemas.BookingFilters) -> schemas.BookingPage:
        with self.database.session() as session:
            query = select(models.Booking)
            if filters.clinic_id is not None:
                query = query.join(models.Slot).where(
                    models.Slot.clinic_id == str(filters.clinic_id)
                )
            for field in ("slot_id", "patient_id", "patient_email", "status"):
                value = getattr(filters, field)
                if value is not None:
                    query = query.where(getattr(models.Booking, field) == str(value))
            bookings = session.scalars(
                query.order_by(models.Booking.created_at, models.Booking.id)
                .limit(filters.limit + 1)
                .offset(filters.offset)
            ).all()
            return schemas.BookingPage(
                items=[schemas.Booking.model_validate(b) for b in bookings[: filters.limit]],
                limit=filters.limit,
                offset=filters.offset,
                has_more=len(bookings) > filters.limit,
            )

    def cancel_booking(self, booking_id: UUID) -> None:
        with self.database.session(write=True) as session:
            booking = self._booking(session, booking_id)
            if booking.status == "cancelled":
                return
            booking.status = "cancelled"
            booking.cancelled_at = self.clock()
