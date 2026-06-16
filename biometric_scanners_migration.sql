-- ============================================================
-- TTTI Biometric Scanner Registry
-- Run this once in your Supabase SQL editor.
-- ============================================================

CREATE TABLE IF NOT EXISTS biometric_scanners (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  serial_number   TEXT NOT NULL UNIQUE,        -- BioEntry W device serial / ID
  device_name     TEXT,                        -- Friendly label (e.g. "Workshop A Scanner")
  room            TEXT NOT NULL,               -- Room name (e.g. "Lab 3", "Workshop A")
  building        TEXT,                        -- Building / block (e.g. "Block B")
  department_id   UUID REFERENCES departments(id) ON DELETE SET NULL,
  notes           TEXT,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  registered_by   UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
  registered_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ
);

-- Auto-update updated_at on any change
CREATE OR REPLACE FUNCTION _set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END; $$;

DROP TRIGGER IF EXISTS trg_biometric_scanners_updated ON biometric_scanners;
CREATE TRIGGER trg_biometric_scanners_updated
  BEFORE UPDATE ON biometric_scanners
  FOR EACH ROW EXECUTE FUNCTION _set_updated_at();

-- Indexes
CREATE INDEX IF NOT EXISTS idx_biometric_scanners_serial    ON biometric_scanners (serial_number);
CREATE INDEX IF NOT EXISTS idx_biometric_scanners_room      ON biometric_scanners (room);
CREATE INDEX IF NOT EXISTS idx_biometric_scanners_dept      ON biometric_scanners (department_id);
CREATE INDEX IF NOT EXISTS idx_biometric_scanners_active    ON biometric_scanners (is_active);

-- Row-level security (optional — mirror your existing table policies)
ALTER TABLE biometric_scanners ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (used by Flask backend)
DROP POLICY IF EXISTS biometric_scanners_service ON biometric_scanners;
CREATE POLICY biometric_scanners_service ON biometric_scanners
  USING (TRUE) WITH CHECK (TRUE);
