"""Validated API requests and public response contracts, separate from ORM models."""

import re
import unicodedata
from datetime import UTC, datetime
from typing import Annotated, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    AfterValidator,
    AliasChoices,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)


def reject_unsafe_text(value: object) -> object:
    if isinstance(value, str) and any(unicodedata.category(char) in {"Cc", "Cs"} for char in value):
        raise ValueError("Text cannot contain control characters or invalid Unicode.")
    return value


def require_datetime_string(value: object) -> object:
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
CleanName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    BeforeValidator(reject_unsafe_text),
]
CleanAddress = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    BeforeValidator(reject_unsafe_text),
]
Availability = Literal["available", "booked", "cancelled", "expired"]
BookingStatus = Literal["confirmed", "cancelled"]
MAX_OFFSET = 2**31 - 1


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResponseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ClinicCreate(RequestModel):
    name: CleanName
    address: CleanAddress | None = None


class Clinic(ResponseModel):
    id: UUID
    name: str
    address: str | None = None
    created_at: AwareDatetime


class SlotTimeCreate(RequestModel):
    starts_at: Timestamp = Field(validation_alias=AliasChoices("starts_at", "start_time"))
    ends_at: Timestamp = Field(validation_alias=AliasChoices("ends_at", "end_time"))

    @model_validator(mode="after")
    def validate_interval(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at.")
        return self


class SlotCreate(SlotTimeCreate):
    clinic_id: UUID


class Slot(ResponseModel):
    id: UUID
    clinic_id: UUID
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    status: Literal["active", "cancelled"]
    availability: Availability
    created_at: AwareDatetime
    cancelled_at: AwareDatetime | None


class BookingCreate(RequestModel):
    """Compatibility body for booking by caller-supplied patient identifier."""

    patient_id: UUID
    patient_name: CleanName | None = None
    patient_email: EmailStr | None = None

    @model_validator(mode="after")
    def validate_patient_details(self) -> Self:
        if (self.patient_name is None) != (self.patient_email is None):
            raise ValueError("Provide patient_name and patient_email together.")
        return self


class AppointmentCreate(RequestModel):
    slot_id: UUID
    patient_name: CleanName
    patient_email: EmailStr
    patient_id: UUID = Field(default_factory=uuid4)


class Booking(ResponseModel):
    id: UUID
    slot_id: UUID
    patient_id: UUID
    patient_name: str | None = None
    patient_email: str | None = None
    status: BookingStatus
    created_at: AwareDatetime
    cancelled_at: AwareDatetime | None


class Pagination(RequestModel):
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    offset: Annotated[int, Field(ge=0, le=MAX_OFFSET)] = 0


class ClinicSlotFilters(Pagination):
    availability: Availability | None = None
    starts_from: Timestamp | None = None
    starts_before: Timestamp | None = None

    @model_validator(mode="after")
    def validate_range(self) -> Self:
        if self.starts_from and self.starts_before and self.starts_before <= self.starts_from:
            raise ValueError("starts_before must be later than starts_from.")
        return self


class SlotFilters(ClinicSlotFilters):
    clinic_id: UUID | None = None


class BookingFilters(Pagination):
    clinic_id: UUID | None = None
    slot_id: UUID | None = None
    patient_id: UUID | None = None
    patient_email: EmailStr | None = None
    status: BookingStatus | None = None


class SlotPage(ResponseModel):
    items: list[Slot]
    limit: int
    offset: int
    has_more: bool


class ClinicPage(ResponseModel):
    items: list[Clinic]
    limit: int
    offset: int
    has_more: bool


class BookingPage(ResponseModel):
    items: list[Booking]
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
