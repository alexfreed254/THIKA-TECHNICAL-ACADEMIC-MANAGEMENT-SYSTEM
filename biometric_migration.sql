-- ─────────────────────────────────────────────────────────────────────────────
-- Biometric Attendance Migration
-- Run this once in your Supabase SQL editor (Database > SQL Editor)
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Biometric sessions table
--    Stores each attendance session opened by a trainer.
--    Status: 'open' (scanning active) | 'closed' (finalised)
CREATE TABLE IF NOT EXISTS biometric_sessions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    trainer_id  UUID        NOT NULL,
    class_id    UUID        NOT NULL,
    unit_id     UUID        NOT NULL,
    unit_code   TEXT        NOT NULL DEFAULT '',
    week        INTEGER     NOT NULL,
    lesson      TEXT        NOT NULL,
    year        INTEGER     NOT NULL,
    term        INTEGER     NOT NULL,
    status      TEXT        NOT NULL DEFAULT 'open'
                            CHECK (status IN ('open', 'closed')),
    device_ip   TEXT        DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    closed_at   TIMESTAMPTZ
);

-- 2. Biometric ID column on user_profiles
--    Stores the numeric ID enrolled on the BioEntry W device for each student.
--    Must match exactly what the device sends as "fingerprint_id" / "user_id".
ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS biometric_id TEXT DEFAULT NULL;

-- Optional index for fast fingerprint lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_biometric_id
    ON user_profiles (biometric_id);
