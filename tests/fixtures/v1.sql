CREATE TABLE IF NOT EXISTS clinics (
    id TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL
);

-- Every timestamp is normalized to fixed-width UTC before insertion.
CREATE TABLE IF NOT EXISTS slots (
    id TEXT PRIMARY KEY NOT NULL,
    clinic_id TEXT NOT NULL REFERENCES clinics(id),
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL CHECK (ends_at > starts_at),
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'cancelled')),
    created_at TEXT NOT NULL,
    cancelled_at TEXT,
    CHECK ((status = 'active' AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL))
);

CREATE TABLE IF NOT EXISTS bookings (
    id TEXT PRIMARY KEY NOT NULL,
    slot_id TEXT NOT NULL REFERENCES slots(id),
    patient_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled')),
    created_at TEXT NOT NULL,
    cancelled_at TEXT,
    CHECK ((status = 'confirmed' AND cancelled_at IS NULL)
        OR (status = 'cancelled' AND cancelled_at IS NOT NULL))
);

-- This is the final safeguard: two confirmed bookings for one slot cannot commit.
-- Cancelled bookings stay in the history without blocking a later booking.
CREATE UNIQUE INDEX IF NOT EXISTS one_confirmed_booking_per_slot
    ON bookings(slot_id) WHERE status = 'confirmed';

CREATE INDEX IF NOT EXISTS slots_by_clinic_and_time ON slots(clinic_id, starts_at, id);
CREATE INDEX IF NOT EXISTS slots_by_time ON slots(starts_at, id);
CREATE INDEX IF NOT EXISTS clinics_by_creation ON clinics(created_at, id);
