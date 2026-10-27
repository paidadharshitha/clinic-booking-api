"""Deterministic checks for bounded retry during concurrent first startup."""

import sqlite3
from dataclasses import dataclass, field

import pytest
from sqlalchemy.exc import OperationalError

import clinic_api.database as database_module
from clinic_api.database import Database
from clinic_api.errors import DomainError


@dataclass
class FakeTime:
    now: float = 0
    sleeps: list[float] = field(default_factory=list)

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_startup_retries_transient_busy_then_initializes_schema(database_path, monkeypatch):
    database = Database(database_path, timeout=1)
    fake_time = FakeTime()
    monkeypatch.setattr(database_module, "time", fake_time)
    initialize_once = database._initialize_once
    attempts = []

    def initially_busy():
        attempts.append(fake_time.now)
        if len(attempts) == 1:
            raise DomainError(503, "DATABASE_BUSY", "Another worker is initializing.")
        initialize_once()

    monkeypatch.setattr(database, "_initialize_once", initially_busy)
    database.initialize()

    assert len(attempts) == 2
    assert 0 < fake_time.now <= database.timeout
    with database.connection() as connection:
        assert connection.exec_driver_sql("PRAGMA user_version").fetchone()[0] == 2
        assert connection.exec_driver_sql("SELECT count(*) FROM clinics").fetchone()[0] == 0


def test_startup_stops_retrying_when_busy_deadline_expires(database_path, monkeypatch):
    database = Database(database_path, timeout=0.12)
    fake_time = FakeTime()
    monkeypatch.setattr(database_module, "time", fake_time)
    attempts = []

    def always_busy():
        attempts.append(fake_time.now)
        raise DomainError(503, "DATABASE_BUSY", "Database is still busy.")

    monkeypatch.setattr(database, "_initialize_once", always_busy)
    with pytest.raises(DomainError) as failure:
        database.initialize()

    assert failure.value.code == "DATABASE_BUSY"
    assert fake_time.now == pytest.approx(database.timeout)
    assert len(attempts) == len(fake_time.sleeps) + 1
    assert len(attempts) <= 4
    assert all(0 < duration <= 0.05 for duration in fake_time.sleeps)


@pytest.mark.parametrize(
    "error",
    [DomainError(500, "OTHER_ERROR", "Unrelated failure"), RuntimeError("Unrelated failure")],
)
def test_startup_does_not_retry_unrelated_failures(database_path, monkeypatch, error):
    database = Database(database_path)
    fake_time = FakeTime()
    monkeypatch.setattr(database_module, "time", fake_time)

    def fail():
        raise error

    monkeypatch.setattr(database, "_initialize_once", fail)
    with pytest.raises(type(error)) as failure:
        database.initialize()

    assert failure.value is error
    assert fake_time.sleeps == []


def test_database_failure_returns_safe_retryable_api_error(app, client, monkeypatch):
    def unavailable():
        raise OperationalError(
            "SELECT private_data FROM internal_table",
            {"patient_email": "private@example.com"},
            sqlite3.OperationalError("disk I/O error"),
        )

    with monkeypatch.context() as context:
        context.setattr(app.state.database.engine, "connect", unavailable)
        response = client.get("/health")

    assert response.status_code == 503, response.text
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert response.headers["retry-after"] == "1"
    assert "private" not in response.text
    assert "internal_table" not in response.text
    assert "disk I/O" not in response.text
    assert client.get("/health").json() == {"status": "ok"}
