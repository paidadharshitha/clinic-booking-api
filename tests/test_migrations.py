"""Existing v1 files retain identifiers, timestamps, and cancellation history."""

import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from clinic_api.main import create_app


def test_v1_database_migration_preserves_history_and_accepts_new_patient_details(
    database_path, clock
):
    clinic_id, slot_id, cancelled_slot_id, old_booking_id, active_booking_id, patient_id = (
        str(uuid4()) for _ in range(6)
    )
    created_at = "2030-06-01T07:00:00.000000Z"
    cancelled_at = "2030-06-01T07:30:00.000000Z"
    starts_at = "2030-06-01T09:00:00.123456Z"
    ends_at = "2030-06-01T09:30:00.123456Z"
    v1_schema = Path(__file__).with_name("fixtures").joinpath("v1.sql").read_text()
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(v1_schema)
        connection.execute(
            "INSERT INTO clinics (id, name, created_at) VALUES (?, 'Existing Clinic', ?)",
            (clinic_id, created_at),
        )
        connection.execute(
            "INSERT INTO slots (id, clinic_id, starts_at, ends_at, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (slot_id, clinic_id, starts_at, ends_at, created_at),
        )
        connection.execute(
            "INSERT INTO slots "
            "(id, clinic_id, starts_at, ends_at, status, created_at, cancelled_at) "
            "VALUES (?, ?, ?, ?, 'cancelled', ?, ?)",
            (cancelled_slot_id, clinic_id, starts_at, ends_at, created_at, cancelled_at),
        )
        connection.execute(
            "INSERT INTO bookings (id, slot_id, patient_id, status, created_at, cancelled_at) "
            "VALUES (?, ?, ?, 'cancelled', ?, ?)",
            (old_booking_id, slot_id, patient_id, created_at, cancelled_at),
        )
        connection.execute(
            "INSERT INTO bookings (id, slot_id, patient_id, created_at) VALUES (?, ?, ?, ?)",
            (active_booking_id, slot_id, patient_id, created_at),
        )
        connection.execute("PRAGMA user_version = 1")
        connection.commit()

    app = create_app(database_path, clock=clock)
    with TestClient(app) as client:
        clinic = client.get(f"/clinics/{clinic_id}").json()
        assert clinic["id"] == clinic_id
        assert clinic["name"] == "Existing Clinic"
        assert clinic["address"] is None
        active = client.get(f"/bookings/{active_booking_id}").json()
        assert active["id"] == active_booking_id
        assert active["patient_id"] == patient_id
        assert active["patient_name"] is None
        assert active["patient_email"] is None
        assert active["status"] == "confirmed"
        cancelled = client.get(f"/bookings/{old_booking_id}").json()
        assert cancelled["status"] == "cancelled"
        assert cancelled["cancelled_at"] is not None
        assert client.get(f"/slots/{slot_id}").json()["availability"] == "booked"
        assert client.get(f"/slots/{cancelled_slot_id}").json()["status"] == "cancelled"

        # Initializing a migrated database again does not reset or duplicate rows.
        app.state.database.initialize()
        with app.state.database.connection() as connection:
            assert connection.exec_driver_sql("PRAGMA user_version").scalar_one() == 2
            assert (
                connection.exec_driver_sql(
                    "SELECT starts_at FROM slots WHERE id = ?", (slot_id,)
                ).scalar_one()
                == starts_at
            )
            assert (
                connection.exec_driver_sql(
                    "SELECT cancelled_at FROM bookings WHERE id = ?", (old_booking_id,)
                ).scalar_one()
                == cancelled_at
            )
            assert connection.exec_driver_sql("SELECT count(*) FROM bookings").scalar_one() == 2

        body = {
            "slot_id": slot_id,
            "patient_name": "New Patient",
            "patient_email": "new@example.com",
        }
        assert client.post("/bookings", json=body).status_code == 409
        assert client.delete(f"/bookings/{active_booking_id}").status_code == 204
        replacement = client.post("/bookings", json=body)
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["patient_name"] == "New Patient"
        history = client.get("/bookings", params={"slot_id": slot_id}).json()["items"]
        assert len(history) == 3
        assert sum(row["status"] == "confirmed" for row in history) == 1
