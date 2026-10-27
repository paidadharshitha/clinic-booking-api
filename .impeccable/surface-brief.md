# Clinic booking portal

Mode: Operate.

## Purpose

The user explicitly requested removal of the information-heavy developer-demo drawback. Patients choose a clinic and time, enter name/email and receive a real booking confirmation through ordinary forms. A second view finds appointments by email and supports cancellation. A clinic view creates clinics, publishes times and manages the schedule. This remains an unauthenticated assessment demo; no login or privacy guarantees may be implied.

## Direction

Retain local Nunito Sans, navy text, violet actions, soft lavender/mint surfaces and simple health icons. Replace the infographic with clear product navigation and a two-column booking layout. Technical examples and concurrency tooling remain at /guide and /docs. The user's current functional direction supersedes the original infographic composition.

## First viewport

A restrained brand/navigation bar, a clear booking heading and actual clinic/time selection lead. The right column shows appointment details and patient fields. Mobile stacks available times above the form. No invented doctors, ratings, testimonials or availability counts.

## Interaction

Selecting a time marks it and fills the appointment summary. Confirmation uses a real POST, preserves entries on errors and explains conflicts. Local date/time controls convert to UTC. Cancellation has an inline confirmation, changes real state and releases the slot. Initial load reads data only. Loading, empty, error, success and stale async responses are handled honestly.

## Quality bar

Users should know what to click without understanding JSON, UUIDs or HTTP status codes. Text is readable at ordinary zoom; narrow screens have no horizontal overflow. All views work by keyboard, network failures offer recovery, and original booking rules remain enforced by the backend.
