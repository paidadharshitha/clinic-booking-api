"""Fresh, file-backed databases and a controllable clock for every test."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from clinic_api.main import create_app


@dataclass
class Clock:
    now: datetime = datetime(2030, 6, 1, 8, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs: float) -> None:
        self.now += timedelta(**kwargs)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def database_path(tmp_path):
    return tmp_path / "appointments.sqlite3"


@pytest.fixture
def app(database_path, clock):
    return create_app(database_path, clock=clock)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def clinic(client):
    response = client.post("/clinics", json={"name": "Meadow Clinic"})
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def make_slot(client, clinic, clock):
    def create(*, clinic_id=None, hours=1, minutes=30):
        starts_at = clock.now + timedelta(hours=hours)
        response = client.post(
            "/slots",
            json={
                "clinic_id": clinic_id or clinic["id"],
                "starts_at": starts_at.isoformat(),
                "ends_at": (starts_at + timedelta(minutes=minutes)).isoformat(),
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return create


@pytest.fixture
def slot(make_slot):
    return make_slot()


@pytest.fixture
def patient_id():
    return str(uuid4())
