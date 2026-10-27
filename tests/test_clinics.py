"""Clinic contact details and the canonical clinic resource."""

import pytest


def test_clinic_address_is_saved_trimmed_and_listed(client):
    response = client.post(
        "/clinics", json={"name": "  Meadow Clinic  ", "address": "  12 Lake Road, Hyderabad  "}
    )
    assert response.status_code == 201, response.text
    clinic = response.json()
    assert clinic["name"] == "Meadow Clinic"
    assert clinic["address"] == "12 Lake Road, Hyderabad"
    assert client.get(f"/clinics/{clinic['id']}").json() == clinic
    assert client.get("/clinics").json()["items"] == [clinic]


@pytest.mark.parametrize("body", [{"name": "Clinic"}, {"name": "Clinic", "address": None}])
def test_clinic_address_is_optional(client, body):
    response = client.post("/clinics", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["address"] is None


@pytest.mark.parametrize("address", ["", "  ", "a" * 301, "Road\x00Two", "Road\nTwo", 123])
def test_invalid_clinic_address_returns_field_error(client, address):
    response = client.post("/clinics", json={"name": "Clinic", "address": address})
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any("address" in detail["field"] for detail in error["details"])
    assert client.get("/clinics").json()["items"] == []
