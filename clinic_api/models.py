"""SQLAlchemy models and database-enforced appointment invariants."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator[datetime]):
    """Preserve timezone and ordering, including timestamps in version-1 databases."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Database timestamps must include a timezone.")
        return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")

    def process_result_value(self, value: str | None, dialect: Dialect) -> datetime | None:
        return datetime.fromisoformat(value).astimezone(UTC) if value is not None else None


class Base(DeclarativeBase):
    pass


class Clinic(Base):
    __tablename__ = "clinics"
    __table_args__ = (
        CheckConstraint("length(trim(name)) BETWEEN 1 AND 120", name="valid_clinic_name"),
        Index("clinics_by_creation", "created_at", "id"),
    )

    # String UUIDs retain the hyphens used by the original public API and database.
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    slots: Mapped[list["Slot"]] = relationship(back_populates="clinic")


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="positive_slot_duration"),
        CheckConstraint("status IN ('active', 'cancelled')", name="valid_slot_status"),
        CheckConstraint(
            "(status = 'active' AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="consistent_slot_cancellation",
        ),
        Index("slots_by_clinic_and_time", "clinic_id", "starts_at", "id"),
        Index("slots_by_time", "starts_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(ForeignKey("clinics.id"))
    starts_at: Mapped[datetime] = mapped_column(UTCDateTime())
    ends_at: Mapped[datetime] = mapped_column(UTCDateTime())
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    clinic: Mapped[Clinic] = relationship(back_populates="slots")
    bookings: Mapped[list["Booking"]] = relationship(back_populates="slot")


class Booking(Base):
    __tablename__ = "bookings"
    __table_args__ = (
        CheckConstraint("status IN ('confirmed', 'cancelled')", name="valid_booking_status"),
        CheckConstraint(
            "(status = 'confirmed' AND cancelled_at IS NULL) OR "
            "(status = 'cancelled' AND cancelled_at IS NOT NULL)",
            name="consistent_booking_cancellation",
        ),
        # This protects capacity even if a future code path bypasses the service.
        Index(
            "one_confirmed_booking_per_slot",
            "slot_id",
            unique=True,
            sqlite_where=text("status = 'confirmed'"),
        ),
        Index("bookings_by_creation", "created_at", "id"),
        Index("bookings_by_slot_and_creation", "slot_id", "created_at", "id"),
        Index("bookings_by_patient", "patient_id", "created_at", "id"),
        Index("bookings_by_email", "patient_email", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    slot_id: Mapped[str] = mapped_column(ForeignKey("slots.id"))
    patient_id: Mapped[str] = mapped_column(String(36))
    # Nullable for historical bookings and the original UUID-only endpoint.
    patient_name: Mapped[str | None] = mapped_column(String(120))
    patient_email: Mapped[str | None] = mapped_column(String(254))
    status: Mapped[str] = mapped_column(String(20), default="confirmed", server_default="confirmed")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime())
    cancelled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    slot: Mapped[Slot] = relationship(back_populates="bookings")
