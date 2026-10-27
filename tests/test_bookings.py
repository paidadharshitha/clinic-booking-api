"""Canonical patient bookings, history, filtering, and compatibility routes."""

from uuid import UUID, uuid4

import pytest


@pytest.fixture
def make_booking(client):
    def create(slot, *, email="patient@example.com", patient_id=None):
        body = {"slot_id": slot["id"], "patient_name": "Asha Rao", "patient_email": email}
        if patient_id is not None:
            body["patient_id"] = patient_id
        response = client.post("/bookings", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return create


def test_create_booking_persists_patient_details_and_generates_patient_id(client, slot):
    response = client.post(
        "/bookings",
        json={
            "slot_id": slot["id"],
            "patient_name": "  Asha Rao  ",
            "patient_email": "asha@EXAMPLE.COM",
        },
    )
    assert response.status_code == 201, response.text
    booking = response.json()
    assert UUID(booking["patient_id"])
    assert booking["patient_name"] == "Asha Rao"
    assert booking["patient_email"] == "asha@example.com"
    assert booking["slot_id"] == slot["id"]
    assert booking["status"] == "confirmed"
    assert booking["cancelled_at"] is None
    assert response.headers["location"] == f"/bookings/{booking['id']}"
    assert client.get(response.headers["location"]).json() == booking
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "booked"


def test_canonical_booking_accepts_existing_patient_identifier(slot, patient_id, make_booking):
    assert make_booking(slot, patient_id=patient_id)["patient_id"] == patient_id


def test_canonical_and_legacy_routes_share_booking_and_cancellation_rules(
    client, slot, patient_id, make_booking
):
    first = make_booking(slot)
    legacy_url = f"/slots/{slot['id']}/bookings"
    conflict = client.post(legacy_url, json={"patient_id": patient_id})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "SLOT_ALREADY_BOOKED"

    assert client.delete(f"/bookings/{first['id']}").status_code == 204
    legacy = client.post(legacy_url, json={"patient_id": patient_id})
    assert legacy.status_code == 201, legacy.text
    second = legacy.json()
    assert second["patient_name"] is None
    assert second["patient_email"] is None

    # Cancelling an old booking again must not release a newly booked slot.
    assert client.delete(f"/bookings/{first['id']}").status_code == 204
    conflict = client.post(
        "/bookings",
        json={
            "slot_id": slot["id"],
            "patient_name": "Different patient",
            "patient_email": "next@example.com",
        },
    )
    assert conflict.status_code == 409
    assert client.get(f"/bookings/{second['id']}").json()["status"] == "confirmed"

    assert client.delete(f"/bookings/{second['id']}").status_code == 204
    third = make_booking(slot)
    history = client.get("/bookings", params={"slot_id": slot["id"]}).json()["items"]
    assert {row["id"] for row in history} == {first["id"], second["id"], third["id"]}
    assert [row["id"] for row in history if row["status"] == "confirmed"] == [third["id"]]


@pytest.mark.parametrize(
    ("state", "status_code", "error_code"),
    [
        ("cancelled", 409, "SLOT_CANCELLED"),
        ("started", 409, "SLOT_STARTED"),
        ("missing", 404, "SLOT_NOT_FOUND"),
    ],
)
def test_canonical_booking_rejects_unavailable_slots(
    client, slot, clock, state, status_code, error_code
):
    slot_id = slot["id"]
    if state == "cancelled":
        client.delete(f"/slots/{slot_id}")
    elif state == "started":
        clock.advance(hours=1)
    else:
        slot_id = str(uuid4())

    response = client.post(
        "/bookings",
        json={"slot_id": slot_id, "patient_name": "Asha Rao", "patient_email": "asha@example.com"},
    )
    assert response.status_code == status_code, response.text
    assert response.json()["error"]["code"] == error_code


@pytest.mark.parametrize("missing", ["slot_id", "patient_name", "patient_email"])
def test_canonical_booking_requires_slot_and_patient_details(client, slot, missing):
    body = {"slot_id": slot["id"], "patient_name": "Asha Rao", "patient_email": "asha@example.com"}
    del body[missing]
    response = client.post("/bookings", json=body)
    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert any(missing in detail["field"] for detail in error["details"])
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "available"


@pytest.mark.parametrize(
    "changes",
    [
        {"patient_name": "   "},
        {"patient_name": "a" * 121},
        {"patient_name": "Asha\x00Rao"},
        {"patient_email": "not-an-email"},
        {"patient_email": "patient@"},
        {"patient_email": None},
        {"slot_id": "not-a-uuid"},
        {"patient_id": "not-a-uuid"},
        {"status": "cancelled"},
    ],
)
def test_canonical_booking_rejects_invalid_details_without_booking_slot(client, slot, changes):
    body = {"slot_id": slot["id"], "patient_name": "Asha Rao", "patient_email": "asha@example.com"}
    response = client.post("/bookings", json=body | changes)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get(f"/slots/{slot['id']}").json()["availability"] == "available"


@pytest.mark.parametrize("body", ["{", "[]", "null"])
def test_canonical_booking_rejects_malformed_request_body(client, body):
    response = client.post("/bookings", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_bookings_filters_combine_and_pagination_is_stable(
    client, clinic, make_slot, make_booking, patient_id
):
    first_slot, second_slot = make_slot(hours=1), make_slot(hours=2)
    other_clinic = client.post("/clinics", json={"name": "Other Clinic"}).json()
    third_slot = make_slot(clinic_id=other_clinic["id"], hours=1)
    first = make_booking(first_slot, email="shared@example.com", patient_id=patient_id)
    second = make_booking(second_slot, email="other@example.com", patient_id=patient_id)
    third = make_booking(third_slot, email="shared@example.com")
    assert client.delete(f"/bookings/{second['id']}").status_code == 204

    filters = [
        ({"clinic_id": clinic["id"]}, {first["id"], second["id"]}),
        ({"slot_id": first_slot["id"]}, {first["id"]}),
        ({"patient_id": patient_id}, {first["id"], second["id"]}),
        ({"patient_email": "shared@EXAMPLE.COM"}, {first["id"], third["id"]}),
        ({"status": "confirmed"}, {first["id"], third["id"]}),
        ({"status": "cancelled"}, {second["id"]}),
        (
            {
                "clinic_id": clinic["id"],
                "patient_email": "shared@example.com",
                "status": "confirmed",
            },
            {first["id"]},
        ),
    ]
    for params, expected_ids in filters:
        response = client.get("/bookings", params=params)
        assert response.status_code == 200, response.text
        assert {row["id"] for row in response.json()["items"]} == expected_ids

    first_page = client.get("/bookings", params={"limit": 2}).json()
    second_page = client.get("/bookings", params={"limit": 2, "offset": 2}).json()
    expected_order = sorted((first["id"], second["id"], third["id"]))
    assert [row["id"] for row in first_page["items"] + second_page["items"]] == expected_order
    assert first_page["has_more"] is True
    assert first_page["offset"] == 0
    assert first_page["limit"] == 2
    assert second_page["has_more"] is False


@pytest.mark.parametrize("filter_name", ["clinic_id", "slot_id", "patient_id"])
def test_bookings_without_filter_matches_returns_empty_page(client, filter_name):
    response = client.get("/bookings", params={filter_name: str(uuid4())})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["has_more"] is False


@pytest.mark.parametrize(
    "params",
    [
        {"clinic_id": "bad"},
        {"slot_id": "bad"},
        {"patient_id": "bad"},
        {"patient_email": "bad"},
        {"status": "unknown"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 10**100},
        {"unexpected": "field"},
    ],
)
def test_booking_filters_validate_values(client, params):
    response = client.get("/bookings", params=params)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
