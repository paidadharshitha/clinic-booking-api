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

The user originally supplied a light, pastel API infographic. The latest request explicitly replaces the information-heavy homepage with simple patient and clinic workflows. Keep the approachable navy typography, soft surfaces and health-themed icons, but use ordinary forms and appointment controls as the primary experience. The earlier API playground remains separately available at /guide, alongside Swagger at /docs.

## Evidence on hand

The existing automated suite and live concurrency tests provide verified backend evidence. The UI must show actual responses when examples run. Do not present illustrative output as a current test run.
