"""Clinic-scoped slot publication and discovery."""

from uuid import uuid4

import pytest


@pytest.mark.parametrize("time_fields", [("starts_at", "ends_at"), ("start_time", "end_time")])
def test_publish_slot_using_canonical_clinic_route(client, clinic, time_fields):
    start, end = time_fields
    response = client.post(
        f"/clinics/{clinic['id']}/slots",
        json={start: "2030-06-01T14:30:00+05:30", end: "2030-06-01T15:00:00+05:30"},
    )
    assert response.status_code == 201, response.text
    slot = response.json()
    assert slot["clinic_id"] == clinic["id"]
    assert slot["starts_at"] == "2030-06-01T09:00:00Z"
    assert slot["ends_at"] == "2030-06-01T09:30:00Z"
    assert slot["availability"] == "available"
    assert response.headers["location"] == f"/slots/{slot['id']}"
    assert client.get(response.headers["location"]).json() == slot


def test_nested_slot_listing_scopes_filters_and_pagination(client, clinic, make_slot):
    slots = [make_slot(hours=hour) for hour in (1, 2, 3)]
    other = client.post("/clinics", json={"name": "Other Clinic"}).json()
    make_slot(clinic_id=other["id"], hours=1)
    client.delete(f"/slots/{slots[2]['id']}")
    endpoint = f"/clinics/{clinic['id']}/slots"

    first = client.get(endpoint, params={"limit": 2}).json()
    second = client.get(endpoint, params={"limit": 2, "offset": 2}).json()
    assert [row["id"] for row in first["items"]] == [row["id"] for row in slots[:2]]
    assert first["has_more"] is True
    assert first["limit"] == 2
    assert first["offset"] == 0
    assert [row["id"] for row in second["items"]] == [slots[2]["id"]]
    assert second["has_more"] is False

    filtered = client.get(
        endpoint,
        params={"availability": "available", "starts_from": "2030-06-01T10:00:00Z"},
    )
    assert [row["id"] for row in filtered.json()["items"]] == [slots[1]["id"]]


def test_empty_and_nonexistent_clinic_slot_list_are_distinct(client, clinic):
    response = client.get(f"/clinics/{clinic['id']}/slots")
    assert response.status_code == 200
    assert response.json()["items"] == []
    response = client.get(f"/clinics/{uuid4()}/slots")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLINIC_NOT_FOUND"


def test_cannot_publish_slot_for_nonexistent_clinic(client):
    response = client.post(
        f"/clinics/{uuid4()}/slots",
        json={"starts_at": "2030-06-01T09:00:00Z", "ends_at": "2030-06-01T09:30:00Z"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CLINIC_NOT_FOUND"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"starts_at": "2030-06-01T09:00:00Z"},
        {"starts_at": "2030-06-01T09:00:00Z", "ends_at": "2030-06-01T09:00:00Z"},
        {"start_time": "2030-06-01T09:00:00", "end_time": "2030-06-01T09:30:00Z"},
        {"starts_at": "2030-06-01T09:00:00Z", "ends_at": "2030-06-01T08:30:00Z"},
    ],
)
def test_nested_slot_publication_validates_inputs(client, clinic, body):
    response = client.post(f"/clinics/{clinic['id']}/slots", json=body)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/clinics/{clinic['id']}/slots").json()["items"] == []
