# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users and purpose

Clinics publish appointment slots and patients book or cancel them. The repository is a technical assessment evaluated primarily on booking correctness, including concurrent requests, then API design, structure, and tests.

## Operating context

The user requested a working local browser preview and a public GitHub repository. Python, FastAPI, SQLAlchemy, SQLite, Pydantic, Pytest, and HTTPX are explicit requirements. The API uses UUID identifiers, UTC timestamps, and consistent errors. Authentication is outside this assessment's scope; browser examples use synthetic data.

## Capabilities and constraints

Create and list clinics; create, list and cancel slots; create, retrieve, list and cancel bookings. A slot has at most one confirmed booking. SQLite write transactions and a partial unique index enforce that constraint. Cancellation is idempotent. An occupied slot cannot be cancelled until its booking is cancelled.

## Brand commitments

The user supplied a light three-column Clinic Appointment Booking API reference image and explicitly requested that visual format on localhost. Preserve its navy typography, pastel panels, API examples, schema diagram, and health-themed vector icons. Keep the implementation's actual API contracts accurate where reference text differs.

## Evidence on hand

The existing automated suite and live concurrency tests provide verified backend evidence. The UI must show actual responses when examples run. Do not present illustrative output as a current test run.
