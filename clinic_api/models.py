"""Request validation and public response contracts."""

import re
import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def require_datetime_string(value: object) -> object:
    # Reject epoch numbers and dates without a time; clients must include a timezone.
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:[Zz]|[+-]\d{2}:\d{2})",
        value,
    ):
        raise ValueError(
            "Use an RFC 3339 timestamp with a timezone and at most 6 fractional digits, "
            "for example 2030-06-01T09:00:00Z."
        )
    return value


def normalize_timestamp(value: datetime) -> datetime:
    try:
        return value.astimezone(UTC)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            "Timestamp must remain within years 0001–9999 when converted to UTC."
        ) from error


Timestamp = Annotated[
    AwareDatetime, BeforeValidator(require_datetime_string), AfterValidator(normalize_timestamp)
]
Availability = Literal["available", "booked", "cancelled", "expired"]
MAX_OFFSET = 2**31 - 1


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClinicCreate(RequestModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]

    @field_validator("name")
    @classmethod
    def reject_control_characters(cls, value: str) -> str:
        if any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
            raise ValueError("Clinic names cannot contain control characters or invalid Unicode.")
        return value


class Clinic(BaseModel):
    id: UUID
    name: str
    created_at: AwareDatetime


class SlotCreate(RequestModel):
    clinic_id: UUID
    starts_at: Timestamp
    ends_at: Timestamp

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at.")
        return self


class Slot(BaseModel):
    id: UUID
    clinic_id: UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    status: Literal["active", "cancelled"]
    availability: Availability
    created_at: AwareDatetime
    cancelled_at: AwareDatetime | None


class BookingCreate(RequestModel):
    patient_id: UUID


class Booking(BaseModel):
    id: UUID
    slot_id: UUID
    patient_id: UUID
    status: Literal["confirmed", "cancelled"]
    created_at: AwareDatetime
    cancelled_at: AwareDatetime | None


class SlotFilters(RequestModel):
    clinic_id: UUID | None = None
    availability: Availability | None = None
    starts_from: Timestamp | None = None
    starts_before: Timestamp | None = None
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    offset: Annotated[int, Field(ge=0, le=MAX_OFFSET)] = 0

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.starts_from and self.starts_before and self.starts_before <= self.starts_from:
            raise ValueError("starts_before must be later than starts_from.")
        return self


class SlotPage(BaseModel):
    items: list[Slot]
    limit: int
    offset: int
    has_more: bool


class ClinicPage(BaseModel):
    items: list[Clinic]
    limit: int
    offset: int
    has_more: bool


class ErrorDetail(BaseModel):
    field: str
    message: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    error: ErrorBody
