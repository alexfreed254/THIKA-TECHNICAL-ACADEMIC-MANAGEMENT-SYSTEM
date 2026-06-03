-- ============================================================
-- TTTI Clearance System Migration
-- Run this in the Supabase SQL editor to support the new
-- sequential clearance flow with serial numbers.
-- ============================================================

-- 1. Add serial_number to clearance_requests
ALTER TABLE clearance_requests
  ADD COLUMN IF NOT EXISTS serial_number TEXT UNIQUE;

-- Index for fast lookup by serial number (QR/verification)
CREATE INDEX IF NOT EXISTS idx_clearance_requests_serial
  ON clearance_requests(serial_number);

-- 2. Backfill serial numbers for existing completed requests
-- (safe to run multiple times — only fills NULL rows)
UPDATE clearance_requests
SET serial_number = 'CLR/' ||
  EXTRACT(YEAR FROM COALESCE(completed_at, created_at))::TEXT || '/' ||
  UPPER(LEFT(REPLACE(id::TEXT, '-', ''), 6))
WHERE serial_number IS NULL
  AND status = 'completed';

-- ============================================================
-- Verify the migration
-- ============================================================
SELECT id, status, serial_number, completed_at
FROM clearance_requests
ORDER BY created_at DESC
LIMIT 10;
