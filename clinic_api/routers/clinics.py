"""Clinic resources and their appointment slots."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from clinic_api.dependencies import Service
from clinic_api.schemas import (
    MAX_OFFSET,
    Clinic,
    ClinicCreate,
    ClinicPage,
    ClinicSlotFilters,
    Slot,
    SlotCreate,
    SlotFilters,
    SlotPage,
    SlotTimeCreate,
)

router = APIRouter(tags=["Clinics"])


@router.post("/clinics", response_model=Clinic, status_code=201)
def create_clinic(data: ClinicCreate, response: Response, service: Service) -> Clinic:
    clinic = service.create_clinic(data)
    response.headers["Location"] = f"/clinics/{clinic.id}"
    return clinic


@router.get("/clinics", response_model=ClinicPage)
def list_clinics(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ClinicPage:
    return service.list_clinics(limit, offset)


@router.get("/clinics/{clinic_id}", response_model=Clinic)
def get_clinic(clinic_id: UUID, service: Service) -> Clinic:
    return service.get_clinic(clinic_id)


@router.post("/clinics/{clinic_id}/slots", response_model=Slot, status_code=201)
def create_clinic_slot(
    clinic_id: UUID, data: SlotTimeCreate, response: Response, service: Service
) -> Slot:
    """Publish a future slot for this clinic; timestamps must include a timezone."""
    slot = service.create_slot(SlotCreate(clinic_id=clinic_id, **data.model_dump()))
    response.headers["Location"] = f"/slots/{slot.id}"
    return slot


@router.get("/clinics/{clinic_id}/slots", response_model=SlotPage)
def list_clinic_slots(
    clinic_id: UUID, filters: Annotated[ClinicSlotFilters, Query()], service: Service
) -> SlotPage:
    """List this clinic's slots; an unknown clinic returns 404."""
    return service.list_clinic_slots(clinic_id, SlotFilters(**filters.model_dump()))
