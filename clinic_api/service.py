"""Booking rules and SQL operations; no HTTP framework dependencies."""

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from clinic_api.database import Database
from clinic_api.errors import DomainError, not_found
from clinic_api.models import (
    Booking,
    BookingCreate,
    Clinic,
    ClinicCreate,
    ClinicPage,
    Slot,
    SlotCreate,
    SlotFilters,
    SlotPage,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime) -> str:
    """Fixed precision and UTC make stored timestamp ordering unambiguous."""
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


# Availability is derived so a slot and its booking can never get out of sync.
SLOT_SELECT = """
    SELECT s.*,
        CASE
            WHEN s.status = 'cancelled' THEN 'cancelled'
            WHEN EXISTS (
                SELECT 1 FROM bookings b WHERE b.slot_id = s.id AND b.status = 'confirmed'
            ) THEN 'booked'
            WHEN s.starts_at <= ? THEN 'expired'
            ELSE 'available'
        END AS availability
    FROM slots s
"""


class BookingService:
    def __init__(self, database: Database, clock: Callable[[], datetime] = utc_now) -> None:
        self.database = database
        self.clock = clock

    def create_clinic(self, data: ClinicCreate) -> Clinic:
        with self.database.transaction() as connection:
            clinic = Clinic(id=uuid4(), name=data.name, created_at=self.clock())
            connection.execute(
                "INSERT INTO clinics (id, name, created_at) VALUES (?, ?, ?)",
                (str(clinic.id), clinic.name, timestamp(clinic.created_at)),
            )
            return clinic

    def get_clinic(self, clinic_id: UUID) -> Clinic:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT * FROM clinics WHERE id = ?", (str(clinic_id),)
            ).fetchone()
            if row is None:
                raise not_found("clinic")
            return Clinic.model_validate(dict(row))

    def list_clinics(self, limit: int, offset: int) -> ClinicPage:
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM clinics ORDER BY created_at, id LIMIT ? OFFSET ?",
                (limit + 1, offset),
            ).fetchall()
            return ClinicPage(
                items=[Clinic.model_validate(dict(row)) for row in rows[:limit]],
                limit=limit,
                offset=offset,
                has_more=len(rows) > limit,
            )

    def create_slot(self, data: SlotCreate) -> Slot:
        with self.database.transaction() as connection:
            # Read time after acquiring the lock; a queued request may have become stale.
            now = self.clock()
            if data.starts_at <= now:
                raise DomainError(422, "SLOT_IN_PAST", "starts_at must be in the future.")
            if (
                connection.execute(
                    "SELECT 1 FROM clinics WHERE id = ?", (str(data.clinic_id),)
                ).fetchone()
                is None
            ):
                raise not_found("clinic")
            slot_id = uuid4()
            connection.execute(
                """INSERT INTO slots (id, clinic_id, starts_at, ends_at, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    str(slot_id),
                    str(data.clinic_id),
                    timestamp(data.starts_at),
                    timestamp(data.ends_at),
                    timestamp(now),
                ),
            )
            return self._get_slot(connection, slot_id, now)

    def get_slot(self, slot_id: UUID) -> Slot:
        with self.database.connection() as connection:
            return self._get_slot(connection, slot_id, self.clock())

    @staticmethod
    def _get_slot(connection: sqlite3.Connection, slot_id: UUID, now: datetime) -> Slot:
        row = connection.execute(
            SLOT_SELECT + " WHERE s.id = ?", (timestamp(now), str(slot_id))
        ).fetchone()
        if row is None:
            raise not_found("slot")
        return Slot.model_validate(dict(row))

    def list_slots(self, filters: SlotFilters) -> SlotPage:
        conditions: list[str] = []
        parameters: list[str | int] = [timestamp(self.clock())]
        if filters.clinic_id is not None:
            conditions.append("clinic_id = ?")
            parameters.append(str(filters.clinic_id))
        if filters.availability is not None:
            conditions.append("availability = ?")
            parameters.append(filters.availability)
        if filters.starts_from is not None:
            conditions.append("starts_at >= ?")
            parameters.append(timestamp(filters.starts_from))
        if filters.starts_before is not None:
            conditions.append("starts_at < ?")
            parameters.append(timestamp(filters.starts_before))
        query = f"SELECT * FROM ({SLOT_SELECT})"
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY starts_at, id LIMIT ? OFFSET ?"
        parameters.extend([filters.limit + 1, filters.offset])
        with self.database.connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
            return SlotPage(
                items=[Slot.model_validate(dict(row)) for row in rows[: filters.limit]],
                limit=filters.limit,
                offset=filters.offset,
                has_more=len(rows) > filters.limit,
            )

    def cancel_slot(self, slot_id: UUID) -> None:
        with self.database.transaction() as connection:
            now = self.clock()
            slot = self._get_slot(connection, slot_id, now)
            if slot.status == "cancelled":
                return
            if slot.availability == "booked":
                raise DomainError(
                    409,
                    "SLOT_HAS_BOOKING",
                    "Cancel the slot's active booking before cancelling it.",
                )
            connection.execute(
                "UPDATE slots SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
                (timestamp(now), str(slot_id)),
            )

    def book_slot(self, slot_id: UUID, data: BookingCreate) -> Booking:
        with self.database.transaction() as connection:
            now = self.clock()
            slot = self._get_slot(connection, slot_id, now)
            if slot.status == "cancelled":
                raise DomainError(409, "SLOT_CANCELLED", "This slot has been cancelled.")
            if slot.availability == "booked":
                raise DomainError(409, "SLOT_ALREADY_BOOKED", "This slot already has a booking.")
            if slot.starts_at <= now:
                raise DomainError(409, "SLOT_STARTED", "This slot has already started.")
            booking_id = uuid4()
            try:
                connection.execute(
                    """INSERT INTO bookings (id, slot_id, patient_id, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (str(booking_id), str(slot_id), str(data.patient_id), timestamp(now)),
                )
            except sqlite3.IntegrityError as error:
                # Keep the UNIQUE constraint as an independent, database-level safeguard.
                # Do not hide unrelated constraint failures as an availability conflict.
                if str(error) == "UNIQUE constraint failed: bookings.slot_id":
                    raise DomainError(
                        409, "SLOT_ALREADY_BOOKED", "This slot already has a booking."
                    ) from error
                raise
            return self._get_booking(connection, booking_id)

    def get_booking(self, booking_id: UUID) -> Booking:
        with self.database.connection() as connection:
            return self._get_booking(connection, booking_id)

    @staticmethod
    def _get_booking(connection: sqlite3.Connection, booking_id: UUID) -> Booking:
        row = connection.execute(
            "SELECT * FROM bookings WHERE id = ?", (str(booking_id),)
        ).fetchone()
        if row is None:
            raise not_found("booking")
        return Booking.model_validate(dict(row))

    def cancel_booking(self, booking_id: UUID) -> None:
        with self.database.transaction() as connection:
            booking = self._get_booking(connection, booking_id)
            if booking.status == "cancelled":
                return
            connection.execute(
                "UPDATE bookings SET status = 'cancelled', cancelled_at = ? WHERE id = ?",
                (timestamp(self.clock()), str(booking_id)),
            )
