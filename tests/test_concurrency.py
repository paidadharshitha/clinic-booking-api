"""Exercise SQLite locking across independent apps, connections, and processes.

The barriers release callers together, rather than sending sequential requests
and describing them as a concurrency test. All apps share a real database file.
"""

import multiprocessing
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from datetime import UTC, datetime
from threading import Barrier, Event
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from clinic_api.main import create_app


def fixed_now():
    return datetime(2030, 6, 1, 8, tzinfo=UTC)


def active_booking_count(database_path, slot_id):
    with closing(sqlite3.connect(database_path)) as connection:
        return connection.execute(
            "SELECT count(*) FROM bookings WHERE slot_id = ? AND status = 'confirmed'",
            (slot_id,),
        ).fetchone()[0]


@pytest.mark.concurrency
def test_eight_simultaneous_requests_commit_exactly_one_booking(database_path, slot, clock):
    workers = 8
    barrier = Barrier(workers, timeout=10)

    # Each client has its own application and Database instance. No Python lock
    # shared by one service instance can accidentally make this test pass.
    with ExitStack() as stack:
        clients = [
            stack.enter_context(TestClient(create_app(database_path, clock=clock)))
            for _ in range(workers)
        ]

        def book(client):
            barrier.wait()
            return client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": str(uuid4())})

        with ThreadPoolExecutor(max_workers=workers) as pool:
            responses = list(pool.map(book, clients))

    assert sorted(response.status_code for response in responses) == [201] + [409] * (workers - 1)
    for response in responses:
        if response.status_code == 409:
            assert response.json()["error"]["code"] == "SLOT_ALREADY_BOOKED"
    assert active_booking_count(database_path, slot["id"]) == 1


def book_in_process(database_path, slot_id, barrier, results):
    """Top-level function so the test also works with the spawn start method."""
    try:
        with TestClient(create_app(database_path, clock=fixed_now)) as client:
            barrier.wait(timeout=15)
            response = client.post(f"/slots/{slot_id}/bookings", json={"patient_id": str(uuid4())})
            results.put((response.status_code, response.json()))
    except Exception as error:
        results.put(("process_error", repr(error)))


def initialize_in_process(database_path, barrier, results):
    try:
        # Release processes before lifespan initializes the database, reproducing
        # several server workers starting against a completely fresh file.
        barrier.wait(timeout=15)
        with TestClient(create_app(database_path, clock=fixed_now)) as client:
            response = client.get("/health")
            results.put((response.status_code, response.json()))
    except Exception as error:
        results.put(("process_error", repr(error)))


@pytest.mark.concurrency
@pytest.mark.parametrize("attempt", range(2))
def test_four_processes_can_initialize_the_same_fresh_database(database_path, attempt):
    assert not database_path.exists()
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(4)
    results = context.Queue()
    processes = [
        context.Process(
            target=initialize_in_process,
            args=(str(database_path), barrier, results),
        )
        for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=25) for _ in processes]
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0

        assert outcomes == [(200, {"status": "ok"})] * 4
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()
        results.join_thread()


@pytest.mark.concurrency
def test_two_independent_processes_cannot_double_book(database_path, slot):
    # Spawn avoids inherited memory, services, locks, and database connections.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    processes = [
        context.Process(
            target=book_in_process,
            args=(str(database_path), slot["id"], barrier, results),
        )
        for _ in range(2)
    ]
    try:
        for process in processes:
            process.start()
        outcomes = [results.get(timeout=25) for _ in processes]
        for process in processes:
            process.join(timeout=5)
            assert process.exitcode == 0

        assert all(isinstance(status, int) for status, _ in outcomes), outcomes
        assert sorted(status for status, _ in outcomes) == [201, 409], outcomes
        loser = next(body for status, body in outcomes if status == 409)
        assert loser["error"]["code"] == "SLOT_ALREADY_BOOKED"
        assert active_booking_count(database_path, slot["id"]) == 1
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        results.close()
        results.join_thread()


@pytest.mark.concurrency
@pytest.mark.parametrize("attempt", range(3))
def test_booking_racing_slot_cancellation_has_only_valid_outcomes(
    database_path, slot, clock, attempt
):
    barrier = Barrier(2, timeout=10)
    slot_url = f"/slots/{slot['id']}"
    with (
        TestClient(create_app(database_path, clock=clock)) as booking_client,
        TestClient(create_app(database_path, clock=clock)) as cancelling_client,
    ):

        def book():
            barrier.wait()
            return booking_client.post(f"{slot_url}/bookings", json={"patient_id": str(uuid4())})

        def cancel():
            barrier.wait()
            return cancelling_client.delete(slot_url)

        with ThreadPoolExecutor(max_workers=2) as pool:
            booking_future = pool.submit(book)
            cancel_future = pool.submit(cancel)
            booking_response = booking_future.result(timeout=15)
            cancel_response = cancel_future.result(timeout=15)

        final_slot = booking_client.get(slot_url).json()

    if booking_response.status_code == 201:
        assert cancel_response.status_code == 409, cancel_response.text
        assert cancel_response.json()["error"]["code"] == "SLOT_HAS_BOOKING"
        assert final_slot["status"] == "active"
        assert final_slot["availability"] == "booked"
        assert active_booking_count(database_path, slot["id"]) == 1
    else:
        assert booking_response.status_code == 409, booking_response.text
        assert booking_response.json()["error"]["code"] == "SLOT_CANCELLED"
        assert cancel_response.status_code == 204, cancel_response.text
        assert final_slot["status"] == "cancelled"
        assert final_slot["availability"] == "cancelled"
        assert active_booking_count(database_path, slot["id"]) == 0


def test_database_itself_rejects_two_confirmed_bookings(client, slot, patient_id, database_path):
    response = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id})
    assert response.status_code == 201

    # Deliberately bypass the application to verify its final database safeguard.
    with (
        closing(sqlite3.connect(database_path)) as connection,
        pytest.raises(sqlite3.IntegrityError, match="UNIQUE constraint failed"),
    ):
        connection.execute(
            "INSERT INTO bookings (id, slot_id, patient_id, status, created_at) "
            "VALUES (?, ?, ?, 'confirmed', ?)",
            (str(uuid4()), slot["id"], str(uuid4()), "2030-06-01T08:00:00.000000Z"),
        )

    assert active_booking_count(database_path, slot["id"]) == 1


def test_exhausted_write_lock_returns_retryable_error_and_no_partial_write(
    database_path, slot, clock, patient_id
):
    app = create_app(database_path, clock=clock, database_timeout=0.05)
    with (
        TestClient(app) as client,
        closing(sqlite3.connect(database_path, isolation_level=None)) as writer,
    ):
        writer.execute("BEGIN IMMEDIATE")
        try:
            response = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id})
            assert response.status_code == 503, response.text
            assert response.json()["error"]["code"] == "DATABASE_BUSY"
            assert response.headers["retry-after"] == "1"
            assert active_booking_count(database_path, slot["id"]) == 0
        finally:
            writer.rollback()

        # A retry succeeds once the database lock is released.
        retry = client.post(f"/slots/{slot['id']}/bookings", json={"patient_id": patient_id})
        assert retry.status_code == 201, retry.text
        assert active_booking_count(database_path, slot["id"]) == 1


@pytest.mark.concurrency
@pytest.mark.parametrize("operation", ["book", "publish"])
def test_slot_start_time_is_rechecked_after_waiting_for_writer_lock(
    app, client, database_path, slot, clock, patient_id, operation
):
    about_to_acquire_lock = Event()

    def before_execute(connection, cursor, statement, parameters, context, executemany):
        if statement == "BEGIN IMMEDIATE":
            about_to_acquire_lock.set()

    event.listen(app.state.database.engine, "before_cursor_execute", before_execute)

    if operation == "book":
        path = f"/slots/{slot['id']}/bookings"
        body = {"patient_id": patient_id}
        expected_status, expected_code = 409, "SLOT_STARTED"
    else:
        path = "/slots"
        body = {key: slot[key] for key in ("clinic_id", "starts_at", "ends_at")}
        expected_status, expected_code = 422, "SLOT_IN_PAST"

    try:
        with closing(sqlite3.connect(database_path, isolation_level=None)) as writer:
            writer.execute("BEGIN IMMEDIATE")
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(client.post, path, json=body)
                try:
                    # SQLAlchemy signals the acquisition attempt while the external
                    # writer still holds the real lock. Advance time before releasing
                    # it, without sleeps or a replacement transaction implementation.
                    assert about_to_acquire_lock.wait(timeout=5)
                    clock.advance(hours=1)
                finally:
                    writer.rollback()
                response = future.result(timeout=10)
    finally:
        event.remove(app.state.database.engine, "before_cursor_execute", before_execute)

    assert response.status_code == expected_status, response.text
    assert response.json()["error"]["code"] == expected_code
    assert active_booking_count(database_path, slot["id"]) == 0
    assert [row["id"] for row in client.get("/slots").json()["items"]] == [slot["id"]]


@pytest.mark.concurrency
def test_canonical_booking_requests_race_across_independent_apps(database_path, slot, clock):
    barrier = Barrier(2, timeout=10)
    with ExitStack() as stack:
        clients = [
            stack.enter_context(TestClient(create_app(database_path, clock=clock)))
            for _ in range(2)
        ]

        def book(index):
            barrier.wait()
            return clients[index].post(
                "/bookings",
                json={
                    "slot_id": slot["id"],
                    "patient_name": f"Patient {index}",
                    "patient_email": f"patient{index}@example.com",
                },
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(book, range(2)))

    assert sorted(response.status_code for response in responses) == [201, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "SLOT_ALREADY_BOOKED"
    assert active_booking_count(database_path, slot["id"]) == 1
