"""Public API behavior: lifecycle rules, validation, and discovery."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest


def assert_error(response, status_code, code):
    assert response.status_code == status_code, response.text
    error = response.json()["error"]
    assert error["code"] == code
    assert error["message"]
    assert isinstance(error["details"], list)
    return error


def test_create_and_retrieve_clinic(client):
    response = client.post("/clinics", json={"name": "  Meadow Clinic  "})

    assert response.status_code == 201
    clinic = response.json()
    assert clinic["name"] == "Meadow Clinic"
    assert response.headers["location"] == f"/clinics/{clinic['id']}"
    assert client.get(response.headers["location"]).json() == clinic


def test_clinic_pagination_is_stable(client):
    ids = {
        client.post("/clinics", json={"name": name}).json()["id"]
        for name in ("Meadow Clinic", "City Clinic", "Lake Clinic")
    }

    first = client.get("/clinics", params={"limit": 2}).json()
    second = client.get("/clinics", params={"limit": 2, "offset": 2}).json()

    assert first["limit"] == 2
    assert first["offset"] == 0
    assert first["has_more"] is True
    assert second["has_more"] is False
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    assert {row["id"] for row in first["items"] + second["items"]} == ids


def test_slot_normalizes_timezones_and_is_retrievable(client, clinic):
    response = client.post(
        "/slots",
        json={
            "clinic_id": clinic["id"],
            "starts_at": "2030-06-01T14:30:00+05:30",
            "ends_at": "2030-06-01T05:00:00-04:30",
        },
    )

    assert response.status_code == 201, response.text
    slot = response.json()
    assert response.headers["location"] == f"/slots/{slot['id']}"
    assert datetime.fromisoformat(slot["starts_at"]) == datetime(2030, 6, 1, 9, tzinfo=UTC)
    assert datetime.fromisoformat(slot["starts_at"]).utcoffset().total_seconds() == 0
    assert datetime.fromisoformat(slot["ends_at"]) == datetime(2030, 6, 1, 9, 30, tzinfo=UTC)
    assert slot["status"] == "active"
    assert slot["availability"] == "available"
    assert slot["cancelled_at"] is None
    assert client.get(response.headers["location"]).json() == slot


def test_booking_prevents_second_booking_and_changes_slot_availability(client, slot, patient_id):
    response = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id})

    assert response.status_code == 201, response.text
    booking = response.json()
    assert response.headers["location"] == f"/bookings/{booking['id']}"
    assert booking["slot_id"] == slot["id"]
    assert booking["patient_id"] == patient_id
    assert booking["status"] == "confirmed"
    assert booking["cancelled_at"] is None
    assert client.get(response.headers["location"]).json() == booking
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "booked"

    # A duplicate request from either the same or another patient is a conflict.
    for patient in (patient_id, str(uuid4())):
        duplicate = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient})
        assert_error(duplicate, 409, "SLOT_ALREADY_BOOKED")


def test_cancel_and_rebook_preserves_history_and_old_cancel_is_idempotent(client, slot, patient_id):
    first = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id}).json()
    first_url = f"/bookings/{first['id']}"

    cancelled = client.delete(first_url)
    assert cancelled.status_code == 204
    assert cancelled.content == b""
    first_snapshot = client.get(first_url).json()
    assert first_snapshot["status"] == "cancelled"
    assert first_snapshot["cancelled_at"] is not None
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "available"

    second = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": str(uuid4())})
    assert second.status_code == 201, second.text
    assert second.json()["id"] != first["id"]

    # Retrying the old cancellation must never cancel the new booking.
    assert client.delete(first_url).status_code == 204
    assert client.get(first_url).json() == first_snapshot
    assert client.get(f"/bookings/{second.json()['id']}").json()["status"] == "confirmed"
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "booked"


def test_booked_slot_cannot_be_cancelled_until_booking_is_cancelled(client, slot, patient_id):
    booking = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id}).json()

    assert_error(client.delete(f"/slots/{slot['id']}"), 409, "SLOT_HAS_BOOKING")
    assert client.get(f"/slots/{slot['id']}").json()["status"] == "active"
    assert client.get(f"/bookings/{booking['id']}").json()["status"] == "confirmed"

    assert client.delete(f"/bookings/{booking['id']}").status_code == 204
    assert client.delete(f"/slots/{slot['id']}").status_code == 204


def test_slot_cancellation_is_idempotent_and_prevents_booking(client, slot, patient_id, clock):
    slot_url = f"/slots/{slot['id']}"

    response = client.delete(slot_url)
    assert response.status_code == 204
    assert response.content == b""
    snapshot = client.get(slot_url).json()
    assert snapshot["status"] == "cancelled"
    assert snapshot["availability"] == "cancelled"
    assert snapshot["cancelled_at"] is not None

    clock.advance(minutes=1)
    assert client.delete(slot_url).status_code == 204
    assert client.get(slot_url).json() == snapshot
    assert_error(
        client.post(f"{slot_url}/bookings", json={"patient_id": patient_id}),
        409,
        "SLOT_CANCELLED",
    )


def test_started_slot_cannot_be_booked(client, slot, patient_id, clock):
    clock.advance(hours=1)

    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "expired"
    assert_error(
        client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id}),
        409,
        "SLOT_STARTED",
    )


def test_booking_can_be_cancelled_after_start_but_slot_stays_unbookable(
    client, slot, patient_id, clock
):
    booking = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id}).json()
    clock.advance(hours=2)

    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "booked"
    assert client.delete(f"/bookings/{booking['id']}").status_code == 204
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "expired"
    assert_error(
        client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id}),
        409,
        "SLOT_STARTED",
    )


def test_slot_filters_and_pagination_respect_clinic_time_and_availability(
    client, clinic, make_slot, patient_id
):
    slots = [make_slot(hours=hour) for hour in (1, 2, 3)]
    other_clinic = client.post("/clinics", json={"name": "Other Clinic"}).json()
    make_slot(clinic_id=other_clinic["id"], hours=2)
    client.post(f"/slots/{slots[1]['id']}/bookings", json={"patient_id": patient_id})
    client.delete(f"/slots/{slots[2]['id']}")

    first = client.get("/slots", params={"clinic_id": clinic["id"], "limit": 2}).json()
    second = client.get(
        "/slots", params={"clinic_id": clinic["id"], "limit": 2, "offset": 2}
    ).json()
    assert [row["id"] for row in first["items"]] == [row["id"] for row in slots[:2]]
    assert first["has_more"] is True
    assert first["offset"] == 0
    assert first["limit"] == 2
    assert [row["id"] for row in second["items"]] == [slots[2]["id"]]
    assert second["has_more"] is False

    for availability, slot in zip(("available", "booked", "cancelled"), slots, strict=True):
        response = client.get(
            "/slots", params={"clinic_id": clinic["id"], "availability": availability}
        )
        assert [row["id"] for row in response.json()["items"]] == [slot["id"]]

    # Time filters use an inclusive lower bound and an exclusive upper bound.
    bounded = client.get(
        "/slots",
        params={
            "clinic_id": clinic["id"],
            "starts_from": "2030-06-01T15:30:00+05:30",
            "starts_before": "2030-06-01T11:00:00Z",
        },
    )
    assert [row["id"] for row in bounded.json()["items"]] == [slots[1]["id"]]


def test_available_filter_excludes_started_slots(client, make_slot, clock):
    expired = make_slot(hours=1)
    available = make_slot(hours=2)
    clock.advance(hours=1)

    result = client.get("/slots", params={"availability": "available"}).json()
    assert [row["id"] for row in result["items"]] == [available["id"]]
    result = client.get("/slots", params={"availability": "expired"}).json()
    assert [row["id"] for row in result["items"]] == [expired["id"]]


@pytest.mark.parametrize(
    ("starts_at", "ends_at", "code"),
    [
        ("2030-06-01T07:00:00Z", "2030-06-01T09:00:00Z", "SLOT_IN_PAST"),
        ("2030-06-01T08:00:00Z", "2030-06-01T09:00:00Z", "SLOT_IN_PAST"),
        ("2030-06-01T09:00:00Z", "2030-06-01T09:00:00Z", "VALIDATION_ERROR"),
        ("2030-06-01T10:00:00Z", "2030-06-01T09:00:00Z", "VALIDATION_ERROR"),
        ("2030-06-01T09:00:00", "2030-06-01T09:30:00Z", "VALIDATION_ERROR"),
        ("2030-06-01T09:00:00Z", "2030-06-01T09:30:00", "VALIDATION_ERROR"),
        ("2030-06-01", "2030-06-02", "VALIDATION_ERROR"),
        (1906534800, 1906536600, "VALIDATION_ERROR"),
        ("1906534800", "1906536600", "VALIDATION_ERROR"),
        ("2030-06-01T09:00:00Z", "9999-12-31T23:30:00-02:00", "VALIDATION_ERROR"),
        ("not-a-time", "2030-06-01T09:30:00Z", "VALIDATION_ERROR"),
    ],
)
def test_rejects_invalid_slot_times(client, clinic, starts_at, ends_at, code):
    response = client.post(
        "/slots",
        json={"clinic_id": clinic["id"], "starts_at": starts_at, "ends_at": ends_at},
    )
    assert_error(response, 422, code)
    assert client.get("/slots").json()["items"] == []


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "a" * 121,
        None,
        42,
        "\x00Clinic",
        "City\nClinic",
        "City\x7fClinic",
        "City\x80Clinic",
    ],
)
def test_rejects_invalid_clinic_names(client, name):
    error = assert_error(client.post("/clinics", json={"name": name}), 422, "VALIDATION_ERROR")
    assert any("name" in detail["field"] for detail in error["details"])


@pytest.mark.parametrize("body", [r'{"name":"Clinic\ud800"}', r'{"name":"Clinic\udfff"}'])
def test_rejects_unpaired_unicode_surrogates_in_clinic_names(client, body):
    response = client.post("/clinics", content=body, headers={"Content-Type": "application/json"})
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert any("name" in detail["field"] for detail in error["details"])


def test_rejects_unknown_fields_and_invalid_booking_patient(client, slot):
    assert_error(
        client.post("/clinics", json={"name": "Clinic", "unexpected": "value"}),
        422,
        "VALIDATION_ERROR",
    )
    for body in (
        {},
        {"patient_id": "invalid"},
        {"patient_id": str(uuid4()), "status": "confirmed"},
    ):
        error = assert_error(
            client.post(f"/slots/{slot['id']}/bookings", json=body), 422, "VALIDATION_ERROR"
        )
        assert error["details"]
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "available"


@pytest.mark.parametrize(
    "params",
    [
        {"clinic_id": "invalid"},
        {"availability": "unknown"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"starts_from": "2030-06-01T09:00:00"},
        {"starts_from": "0001-01-01T00:00:00+01:00"},
        {"starts_from": "2030-06-01T10:00:00Z", "starts_before": "2030-06-01T09:00:00Z"},
    ],
)
def test_rejects_invalid_slot_filters(client, params):
    assert_error(client.get("/slots", params=params), 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("resource", ["clinics", "slots"])
@pytest.mark.parametrize("offset", [2**31, 10**100])
def test_oversized_pagination_offsets_are_validation_errors(client, resource, offset):
    error = assert_error(
        client.get(f"/{resource}", params={"offset": offset}), 422, "VALIDATION_ERROR"
    )
    assert any("offset" in detail["field"] for detail in error["details"])


@pytest.mark.parametrize(
    ("method", "path", "code"),
    [
        ("get", "/clinics/{id}", "CLINIC_NOT_FOUND"),
        ("get", "/slots/{id}", "SLOT_NOT_FOUND"),
        ("delete", "/slots/{id}", "SLOT_NOT_FOUND"),
        ("get", "/bookings/{id}", "BOOKING_NOT_FOUND"),
        ("delete", "/bookings/{id}", "BOOKING_NOT_FOUND"),
        ("get", "/unknown-route", "NOT_FOUND"),
    ],
)
def test_missing_resources_return_consistent_errors(client, method, path, code):
    response = getattr(client, method)(path.format(id=uuid4()))
    assert_error(response, 404, code)


def test_create_operations_require_existing_resources(client, patient_id):
    assert_error(
        client.post(
            "/slots",
            json={
                "clinic_id": str(uuid4()),
                "starts_at": "2030-06-01T09:00:00Z",
                "ends_at": "2030-06-01T09:30:00Z",
            },
        ),
        404,
        "CLINIC_NOT_FOUND",
    )
    assert_error(
        client.post(f"/slots/{uuid4()}/bookings", json={"patient_id": patient_id}),
        404,
        "SLOT_NOT_FOUND",
    )


@pytest.mark.parametrize("resource", ["clinics", "slots", "bookings"])
def test_malformed_resource_ids_are_validation_errors(client, resource):
    assert_error(client.get(f"/{resource}/not-a-uuid"), 422, "VALIDATION_ERROR")


def test_malformed_json_returns_helpful_error(client):
    response = client.post("/clinics", content="{", headers={"Content-Type": "application/json"})
    error = assert_error(response, 422, "VALIDATION_ERROR")
    assert error["details"]
