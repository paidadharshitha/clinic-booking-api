# Clinic Booking API

[![CI](https://github.com/paidadharshitha/clinic-booking-api/actions/workflows/ci.yml/badge.svg)](https://github.com/paidadharshitha/clinic-booking-api/actions/workflows/ci.yml)

A small FastAPI service for publishing clinic appointment slots and booking them safely. SQLite transactions coordinate competing requests, and a database constraint guarantees **at most one confirmed booking per slot**.

Python 3.11+ · FastAPI · Pydantic · SQLite · pytest

## Run locally

```bash
git clone https://github.com/paidadharshitha/clinic-booking-api.git
cd clinic-booking-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
uvicorn clinic_api.main:app --reload
```

Open [interactive API docs](http://127.0.0.1:8000/docs), [ReDoc](http://127.0.0.1:8000/redoc), or the [OpenAPI schema](http://127.0.0.1:8000/openapi.json). The database and its parent directory are created automatically on startup.

`BOOKING_DB_PATH` defaults to `./data/bookings.db`. Set it to use another persistent database:

```bash
BOOKING_DB_PATH=./data/demo.db uvicorn clinic_api.main:app --reload
```

The requirements file pins the development environment. To install using the supported dependency ranges instead, use `python -m pip install -e '.[dev]'`.

### Docker

```bash
docker compose up --build
```

The API runs at `http://127.0.0.1:8000` as a non-root user. The named volume `clinic-booking-data` persists `/app/data/bookings.db` across container replacements. Stop it with `docker compose down`; adding `--volumes` also deletes the stored appointments.

## Booking rules

- A slot belongs to an existing clinic. Its start must be in the future and its end strictly after its start.
- A patient can book an active, unstarted slot only if it has no confirmed booking.
- Cancelling a booking frees its slot for a new booking if the slot has not started.
- A slot with a confirmed booking cannot be cancelled. Cancel the booking first.
- Cancellation is idempotent: cancelling an already cancelled resource returns `204` again. Unknown resources return `404`.
- Slots and bookings are retained after cancellation; historical bookings never prevent rebooking.
- Cancellation is allowed after a slot starts. Booking is not.

Every input timestamp must use RFC 3339 with a `T` separator, seconds, and an explicit timezone, such as `2030-06-01T09:00:00Z` or `2030-06-01T14:30:00+05:30`. Optional fractional seconds may have at most six digits. Values are normalized to UTC. Unknown request fields are rejected.

`status` records a slot's lifecycle (`active` or `cancelled`). `availability` is computed when it is read, in this precedence: `cancelled`, `booked`, `expired`, `available`. An unbooked slot becomes `expired` when its start time is reached. Bookings have a separate `confirmed` / `cancelled` status.

Distinct slots may overlap: a clinic may have multiple practitioners or rooms. Capacity is one booking **per slot**, not one booking per clinic or patient. Patients are represented by caller-supplied UUIDs; a patient registry is outside this exercise.

## API

All request and response bodies are JSON, except successful cancellations, which have no response body. IDs are UUIDs.

| Method | Endpoint | Purpose | Success |
| --- | --- | --- | --- |
| `GET` | `/health` | Check service and database readiness | `200` |
| `POST` | `/clinics` | Create a clinic with `{ "name": "Lakeside Clinic" }` | `201` |
| `GET` | `/clinics` | List clinics | `200` |
| `GET` | `/clinics/{clinic_id}` | Read one clinic | `200` |
| `POST` | `/slots` | Create a slot with `clinic_id`, `starts_at`, `ends_at` | `201` |
| `GET` | `/slots` | List and filter slots | `200` |
| `GET` | `/slots/{slot_id}` | Read one slot and its availability | `200` |
| `DELETE` | `/slots/{slot_id}` | Cancel a slot | `204` |
| `POST` | `/slots/{slot_id}/bookings` | Book a slot with `{ "patient_id": "<uuid>" }` | `201` |
| `GET` | `/bookings/{booking_id}` | Read one booking | `200` |
| `DELETE` | `/bookings/{booking_id}` | Cancel a booking | `204` |

Clinic names are trimmed and must contain 1–120 characters without control characters. Creation responses include a `Location` header pointing to the created resource.

### Listing and filtering

Both list endpoints accept `limit` (default `20`, range `1–100`) and `offset` (default `0`, range `0–2147483647`). Responses contain `items`, `limit`, `offset`, and `has_more`.

`GET /slots` also accepts:

| Parameter | Meaning |
| --- | --- |
| `clinic_id` | Only this clinic's slots |
| `availability` | `available`, `booked`, `cancelled`, or `expired`; omitted means all |
| `starts_from` | Slot start is on or after this timezone-aware timestamp |
| `starts_before` | Slot start is strictly before this timezone-aware timestamp |

Slots are ordered by start time, then ID. When both time bounds are provided, `starts_before` must be later than `starts_from`. Offset pagination is appropriate for this small API; concurrent changes can shift page boundaries.

```bash
curl --get 'http://127.0.0.1:8000/slots' \
  --data-urlencode 'availability=available' \
  --data-urlencode 'limit=10'
```

### Errors

Errors have a stable machine-readable code, a human-readable message, and an optional list of field-level details:

```json
{
  "error": {
    "code": "SLOT_ALREADY_BOOKED",
    "message": "This slot already has a booking.",
    "details": []
  }
}
```

| Status | Code | Meaning |
| --- | --- | --- |
| `404` | `CLINIC_NOT_FOUND`, `SLOT_NOT_FOUND`, `BOOKING_NOT_FOUND` | Referenced resource does not exist |
| `409` | `SLOT_ALREADY_BOOKED` | Another confirmed booking occupies the slot |
| `409` | `SLOT_CANCELLED` | The slot cannot accept a booking |
| `409` | `SLOT_STARTED` | The slot's start time has been reached |
| `409` | `SLOT_HAS_BOOKING` | Cancel the confirmed booking before cancelling the slot |
| `422` | `VALIDATION_ERROR` | Invalid UUID, timestamp, interval, field, or query parameter |
| `422` | `SLOT_IN_PAST` | A new slot must start in the future |
| `503` | `DATABASE_BUSY` | Database lock wait exceeded; includes `Retry-After: 1` |

Validation details use `{ "field": "...", "message": "...", "type": "..." }`. Clients should branch on `code`, rather than matching error-message text.

## Try the full flow

Run these commands in a second shell with the virtual environment activated. The example generates tomorrow's timestamps, so it stays runnable without editing fixed dates. It requires `curl` and Python, but no `jq`.

```bash
BASE=http://127.0.0.1:8000
json_id() { python -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }

CLINIC_ID=$(curl --fail-with-body -sS -X POST "$BASE/clinics" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lakeside Clinic"}' | json_id)

SLOT_JSON=$(python - "$CLINIC_ID" <<'PY'
import json
import sys
from datetime import datetime, timedelta, timezone

start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
print(json.dumps({
    "clinic_id": sys.argv[1],
    "starts_at": start.isoformat(),
    "ends_at": (start + timedelta(minutes=30)).isoformat(),
}))
PY
)

SLOT_ID=$(curl --fail-with-body -sS -X POST "$BASE/slots" \
  -H 'Content-Type: application/json' -d "$SLOT_JSON" | json_id)
PATIENT_ID=$(python -c 'from uuid import uuid4; print(uuid4())')

# First booking succeeds: 201.
BOOKING_ID=$(curl --fail-with-body -sS -X POST "$BASE/slots/$SLOT_ID/bookings" \
  -H 'Content-Type: application/json' \
  -d "{\"patient_id\":\"$PATIENT_ID\"}" | json_id)

# A second booking receives 409 SLOT_ALREADY_BOOKED.
curl -i -X POST "$BASE/slots/$SLOT_ID/bookings" \
  -H 'Content-Type: application/json' \
  -d "{\"patient_id\":\"$PATIENT_ID\"}"

# Cancel the original booking: 204. The slot is available again.
curl -i -X DELETE "$BASE/bookings/$BOOKING_ID"
curl -sS "$BASE/slots/$SLOT_ID"

# Rebooking succeeds with a new booking ID: 201.
NEW_BOOKING_ID=$(curl --fail-with-body -sS -X POST "$BASE/slots/$SLOT_ID/bookings" \
  -H 'Content-Type: application/json' \
  -d "{\"patient_id\":\"$PATIENT_ID\"}" | json_id)

# Release the booking, then cancel the slot: both return 204.
curl -i -X DELETE "$BASE/bookings/$NEW_BOOKING_ID"
curl -i -X DELETE "$BASE/slots/$SLOT_ID"
```

## Why simultaneous requests are safe

Every write uses a short transaction on its own SQLite connection:

1. `BEGIN IMMEDIATE` acquires SQLite's writer lock **before** checking slot state.
2. The service checks cancellation, current time, and any confirmed booking inside that transaction.
3. It inserts or updates the record, then commits; failures roll back.

If two requests book the same available slot, one transaction proceeds first. The other waits, then reads the committed booking and returns `409 SLOT_ALREADY_BOOKED`. The ordinary race result is exactly one `201` and one `409`. If a lock remains held beyond the five-second timeout, the waiting request receives `503` instead; the invariant still holds. Slot cancellation participates in the same locking protocol, so booking and cancellation cannot both succeed for an initially available slot.

The database also enforces the invariant independently of the service:

```sql
CREATE UNIQUE INDEX one_confirmed_booking_per_slot
    ON bookings(slot_id) WHERE status = 'confirmed';
```

Cancelled rows remain for history without consuming capacity. There is no process-local mutex or in-memory reservation state. SQLite's [transaction semantics](https://www.sqlite.org/lang_transaction.html) coordinate writers across processes, and its [unique partial indexes](https://www.sqlite.org/partialindex.html) enforce uniqueness only for the selected rows.

WAL mode permits readers alongside a writer. SQLite still serializes writes across the database, which is a deliberate simplicity/throughput tradeoff. Use a persistent file on one host's local disk, including when running multiple worker processes. Multi-host deployments and network filesystems require a different storage design, such as PostgreSQL with equivalent transactional checks and a partial unique constraint.

## Tests and checks

```bash
pytest -q
pytest --cov=clinic_api --cov-report=term-missing
pytest -q -m concurrency
ruff check .
ruff format --check .
```

Tests use isolated, file-backed SQLite databases. They cover successful booking, duplicate booking, cancellation and rebooking, invalid input, time boundaries, and concurrent state changes. Race tests synchronize independent HTTP clients against the same database and check the persisted outcome; the database uniqueness constraint is also tested directly. No external database service is required.

For a quick correctness review, start with [the concurrency tests](tests/test_concurrency.py) and [the database constraints](clinic_api/schema.sql). GitHub Actions runs Ruff and the complete test suite on Python 3.11, 3.12, and 3.13, with a minimum coverage threshold of 90%.

## Structure and scope

```text
clinic_api/
  main.py       Application factory, lifecycle, error responses
  api.py        Thin HTTP routes and dependency wiring
  models.py     Request validation and public response contracts
  service.py    Booking rules and transactional operations
  database.py   Connections, transactions, schema initialization
  schema.sql    Tables, integrity checks, indexes
  errors.py     Domain errors
tests/          API, persistence, and concurrency tests
```

This submission focuses on booking correctness and a reproducible local development experience. The initial schema is versioned; later schema changes need explicit migrations. Authentication, clinic/patient authorization, notifications, payment, and appointment rescheduling are outside scope. An authenticated identity must replace trusted caller-supplied patient IDs before use with real patient data.
