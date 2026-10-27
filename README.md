# Clinic Booking API

[![CI](https://github.com/paidadharshitha/clinic-booking-api/actions/workflows/ci.yml/badge.svg)](https://github.com/paidadharshitha/clinic-booking-api/actions/workflows/ci.yml)

A FastAPI service and visual interactive guide for publishing clinic appointment slots and booking them safely. SQLite transactions coordinate competing requests, and a database constraint guarantees **at most one confirmed booking per slot**.

Python 3.11+ · FastAPI · SQLAlchemy 2.x · Pydantic · SQLite · pytest / HTTPX

## Run locally

Prerequisites: Python 3.11 or newer and Git. Docker is optional.

```bash
git clone https://github.com/paidadharshitha/clinic-booking-api.git
cd clinic-booking-api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e .
uvicorn clinic_api.main:app --reload
```

Open the [visual interactive guide](http://localhost:8000/) to explore the booking flow and make live requests. [Swagger API docs](http://localhost:8000/docs), [ReDoc](http://localhost:8000/redoc), and the [OpenAPI schema](http://localhost:8000/openapi.json) remain available.

The guide's live actions use the same API and database as other clients. Created clinics, slots, and bookings persist after refreshing the page or restarting the server; use synthetic patient details while trying it. The database and its parent directory are created automatically on startup.

The guide's HTML, CSS, JavaScript, and Nunito Sans font are bundled with the Python package. The font's [SIL Open Font License](clinic_api/static/OFL-NunitoSans.txt) is included.

New databases use the SQLAlchemy schema. Existing version 1 databases are upgraded transactionally to version 2, adding the optional address and patient contact fields while preserving IDs, timestamps, and booking history. No separate initialization command is needed.

`BOOKING_DB_PATH` defaults to `./data/bookings.db`. Set it to use another persistent database:

```bash
BOOKING_DB_PATH=./data/demo.db uvicorn clinic_api.main:app --reload
```

The requirements file pins the development environment. To install using the supported dependency ranges instead, use `python -m pip install -e '.[dev]'`.

See [.env.example](.env.example) for configuration. The application reads environment variables; it does not automatically load `.env` files.

### Docker

```bash
docker compose up --build
```

The guide and API run at `http://localhost:8000` as a non-root user. The named volume `clinic-booking-data` persists `/app/data/bookings.db` across container replacements. Stop it with `docker compose down`; adding `--volumes` also deletes the stored appointments.

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

Distinct slots may overlap: a clinic may have multiple practitioners or rooms. Capacity is one booking **per slot**, not one booking per clinic or patient. A booking stores a patient's name and email. `patient_id` may be supplied or generated; it does not establish identity, and repeat emails do not automatically merge patients into a registry.

## API

All request and response bodies are JSON, except successful cancellations, which have no response body. IDs are UUIDs.

| Method | Endpoint | Purpose | Success |
| --- | --- | --- | --- |
| `GET` | `/health` | Check service and database readiness | `200` |
| `POST` | `/clinics` | Create a clinic with `name` and optional `address` | `201` |
| `GET` | `/clinics` | List clinics | `200` |
| `GET` | `/clinics/{clinic_id}` | Read one clinic | `200` |
| `POST` | `/clinics/{clinic_id}/slots` | Create a slot with `starts_at` and `ends_at` | `201` |
| `GET` | `/clinics/{clinic_id}/slots` | List and filter this clinic's slots | `200` |
| `GET` | `/slots/{slot_id}` | Read one slot and its availability | `200` |
| `DELETE` | `/slots/{slot_id}` | Cancel a slot | `204` |
| `POST` | `/bookings` | Book with `slot_id`, `patient_name`, `patient_email`, optional `patient_id` | `201` |
| `GET` | `/bookings` | List and filter bookings | `200` |
| `GET` | `/bookings/{booking_id}` | Read one booking | `200` |
| `DELETE` | `/bookings/{booking_id}` | Cancel a booking | `204` |
| `GET` | `/slots` | List and filter slots across clinics | `200` |
| `POST` | `/slots` | Compatibility: create with `clinic_id`, `starts_at`, `ends_at` | `201` |
| `POST` | `/slots/{slot_id}/bookings` | Compatibility: book with required `patient_id` | `201` |

Clinic and patient names are trimmed and must contain 1–120 characters. An optional clinic address must contain 1–300 characters after trimming. These fields reject control characters and invalid Unicode. Email addresses are validated; their domains are normalized. Creation responses include a `Location` header pointing to the created resource.

Slot requests also accept `start_time` / `end_time` as aliases; responses use `starts_at` / `ends_at`. Send only one name for each field. The compatibility booking route accepts either just `patient_id`, or `patient_id` plus both `patient_name` and `patient_email`; older bookings may therefore have null contact details.

### Listing and filtering

All list endpoints accept `limit` (default `20`, range `1–100`) and `offset` (default `0`, range `0–2147483647`). Responses contain `items`, `limit`, `offset`, and `has_more`.

`GET /slots` also accepts:

| Parameter | Meaning |
| --- | --- |
| `clinic_id` | Only this clinic's slots |
| `availability` | `available`, `booked`, `cancelled`, or `expired`; omitted means all |
| `starts_from` | Slot start is on or after this timezone-aware timestamp |
| `starts_before` | Slot start is strictly before this timezone-aware timestamp |

Slots are ordered by start time, then ID. When both time bounds are provided, `starts_before` must be later than `starts_from`. Offset pagination is appropriate for this small API; concurrent changes can shift page boundaries.

`GET /clinics/{clinic_id}/slots` supports the same filters except `clinic_id`, which comes from the path. An unknown clinic returns `404`, even if it would have no slots. `GET /bookings` accepts `clinic_id`, `slot_id`, `patient_id`, `patient_email`, and `status` (`confirmed` or `cancelled`); omitted filters match all values.

Clinics and bookings are ordered by creation time, then ID. Booking filters match exact stored values; the email filter uses the same email normalization as booking creation.

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
| `503` | `DATABASE_UNAVAILABLE` | Storage could not complete the operation; includes `Retry-After: 1` |

Validation details use `{ "field": "...", "message": "...", "type": "..." }`. Clients should branch on `code`, rather than matching error-message text.

## Try the full flow

Run these commands in a second shell with the virtual environment activated. The example generates tomorrow's timestamps, so it stays runnable without editing fixed dates. It requires `curl` and Python, but no `jq`.

```bash
BASE=http://127.0.0.1:8000
json_id() { python -c 'import json,sys; print(json.load(sys.stdin)["id"])'; }

CLINIC_ID=$(curl --fail-with-body -sS -X POST "$BASE/clinics" \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lakeside Clinic","address":"12 Lake Road"}' | json_id)

SLOT_JSON=$(python - <<'PY'
import json
from datetime import datetime, timedelta, timezone

start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0)
print(json.dumps({
    "starts_at": start.isoformat(),
    "ends_at": (start + timedelta(minutes=30)).isoformat(),
}))
PY
)

SLOT_ID=$(curl --fail-with-body -sS -X POST "$BASE/clinics/$CLINIC_ID/slots" \
  -H 'Content-Type: application/json' -d "$SLOT_JSON" | json_id)
BOOKING_JSON="{\"slot_id\":\"$SLOT_ID\",\"patient_name\":\"Alex Rao\",\"patient_email\":\"alex@example.com\"}"

# First booking succeeds: 201.
BOOKING_ID=$(curl --fail-with-body -sS -X POST "$BASE/bookings" \
  -H 'Content-Type: application/json' -d "$BOOKING_JSON" | json_id)

# A second booking receives 409 SLOT_ALREADY_BOOKED.
curl -i -X POST "$BASE/bookings" \
  -H 'Content-Type: application/json' -d "$BOOKING_JSON"

# Read this clinic's confirmed bookings.
curl --get "$BASE/bookings" \
  --data-urlencode "clinic_id=$CLINIC_ID" \
  --data-urlencode 'status=confirmed'

# Cancel the original booking: 204. The slot is available again.
curl -i -X DELETE "$BASE/bookings/$BOOKING_ID"
curl -sS "$BASE/slots/$SLOT_ID"

# Rebooking succeeds with a new booking ID: 201.
NEW_BOOKING_ID=$(curl --fail-with-body -sS -X POST "$BASE/bookings" \
  -H 'Content-Type: application/json' -d "$BOOKING_JSON" | json_id)

# Release the booking, then cancel the slot: both return 204.
curl -i -X DELETE "$BASE/bookings/$NEW_BOOKING_ID"
curl -i -X DELETE "$BASE/slots/$SLOT_ID"
```

A successful booking has this shape (IDs and timestamps are illustrative):

```json
{
  "id": "722854b9-3da2-425e-9cc8-107f3cb10bc9",
  "slot_id": "8b990f94-04b1-45c0-9874-d2047289bff2",
  "patient_id": "f30b6463-a392-4cdf-9783-b5b770030df0",
  "patient_name": "Alex Rao",
  "patient_email": "alex@example.com",
  "status": "confirmed",
  "created_at": "2030-06-01T08:00:00Z",
  "cancelled_at": null
}
```

## Why simultaneous requests are safe

Every write uses a short SQLAlchemy transaction with its own database session:

1. `BEGIN IMMEDIATE` acquires SQLite's writer lock **before** checking slot state.
2. The service checks cancellation, current time, and any confirmed booking inside that transaction.
3. It inserts or updates the record, then commits; failures roll back.

The engine uses `NullPool`, so operations acquire independent connections. SQLite's implicit transaction handling is disabled: reads use explicit `BEGIN`, and writes use explicit `BEGIN IMMEDIATE`. Slot state and the current time are checked after the writer lock is acquired.

SQLite does not provide row-level `SELECT ... FOR UPDATE` locking. The explicit writer transaction and partial unique index are the safeguards here; see SQLAlchemy's [SQLite transaction guidance](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver). Datetimes use a custom SQLAlchemy type that persists fixed-width UTC text, preserving timezone information and ordering across the version 1 migration.

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

For a quick correctness review, start with [the concurrency tests](tests/test_concurrency.py), [the database models and constraints](clinic_api/models.py), and [the transaction boundaries](clinic_api/database.py). GitHub Actions runs Ruff and the complete test suite on Python 3.11, 3.12, and 3.13, with a minimum coverage threshold of 90%.

## Architecture and data model

```text
clinic_api/
  main.py       Application factory, lifecycle, error responses
  api.py        Router composition and shared error contracts
  dependencies.py  FastAPI service injection
  models.py     SQLAlchemy tables, integrity checks, indexes
  schemas.py    Pydantic request validation and response contracts
  database.py   Engine, sessions, transactions, schema initialization
  errors.py     Domain errors
  routers/
    clinics.py  Clinics and clinic-specific slot endpoints
    slots.py    Slots and compatibility endpoints
    bookings.py Booking creation, filtering, and cancellation
  services/
    booking_service.py  Booking rules and transactional operations
  static/       Packaged HTML, CSS, and JavaScript for the guide at /
tests/          API, persistence, and concurrency tests
```

Routes validate HTTP inputs and delegate to the service. The service applies business rules inside database transactions. SQLAlchemy models define storage constraints; Pydantic schemas define the external API.

| Table | Stored data and relationships |
| --- | --- |
| `clinics` | UUID, name, optional address, creation timestamp |
| `slots` | UUID, clinic foreign key, UTC start/end, lifecycle status, timestamps |
| `bookings` | UUID, slot foreign key, patient UUID and optional contact details, status, timestamps |

A clinic has many slots; a slot retains many historical bookings but at most one confirmed booking. Foreign keys protect relationships, checks constrain statuses and time intervals, and indexes support listing and the single-booking invariant.

## Scope and next steps

Authentication and authorization are not implemented. Patient details and UUIDs are trusted input for this assessment; the API should be used with synthetic data until authenticated identities and access rules are added. A patient registry, notifications, payments, and rescheduling are outside scope.

Future work would add authentication and clinic/patient permissions, explicit versioned migrations for later schema changes, cursor pagination for larger datasets, and PostgreSQL for higher write concurrency or deployment across hosts. Appointment notifications should run after transaction commit through a durable job queue.

## Publish your own copy

The submission repository is [paidadharshitha/clinic-booking-api](https://github.com/paidadharshitha/clinic-booking-api). To publish a separate copy after cloning, create an empty repository in your GitHub account, then replace the placeholders below with its owner and name:

```bash
git remote set-url origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Commit any local changes before pushing. Run the tests and checks above before submitting the repository URL.
