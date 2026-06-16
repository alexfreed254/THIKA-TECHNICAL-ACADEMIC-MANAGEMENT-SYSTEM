-- ============================================================
-- TTTI Clearance System — Stage 2 Migration
-- Run this against your Supabase PostgreSQL database.
-- Safe to run multiple times (all use IF NOT EXISTS).
-- ============================================================

-- 1. clearance_approvals: new columns for 3-stage parallel flow
ALTER TABLE clearance_approvals
  ADD COLUMN IF NOT EXISTS clearance_stage      INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS approver_category    TEXT,
  ADD COLUMN IF NOT EXISTS is_waived            BOOLEAN DEFAULT FALSE,
  ADD COLUMN IF NOT EXISTS waived_by            TEXT,
  ADD COLUMN IF NOT EXISTS waived_at            TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS approved_at          TIMESTAMPTZ;

-- 2. clearance_requests: stage tracking + return-for-correction + serial
ALTER TABLE clearance_requests
  ADD COLUMN IF NOT EXISTS stage           INTEGER DEFAULT 1,
  ADD COLUMN IF NOT EXISTS serial_number   TEXT,
  ADD COLUMN IF NOT EXISTS return_reason   TEXT,
  ADD COLUMN IF NOT EXISTS returned_at     TIMESTAMPTZ;

-- 3. Index: fast serial verification lookups
CREATE INDEX IF NOT EXISTS idx_clearance_requests_serial
  ON clearance_requests (serial_number)
  WHERE serial_number IS NOT NULL;

-- 4. Index: fast approver dashboard queries
CREATE INDEX IF NOT EXISTS idx_clearance_approvals_category
  ON clearance_approvals (approver_category)
  WHERE approver_category IS NOT NULL;

-- 5. Index: completion checks per stage
CREATE INDEX IF NOT EXISTS idx_clearance_approvals_stage
  ON clearance_approvals (clearance_stage);

-- ============================================================
-- Optional backfill: populate approver_category from stage names
-- Uncomment and run only if you have existing records.
-- ============================================================
-- UPDATE clearance_approvals ca
-- SET approver_category =
--   CASE
--     WHEN cs.approver_role = 'trainer'             THEN 'trainer'
--     WHEN cs.approver_role = 'workshop_technician' THEN 'tech_1'
--     WHEN cs.approver_role = 'dept_admin'          THEN 'hod_other'
--     WHEN cd.name ILIKE '%kenya%'   OR cd.name ILIKE '%knls%'     THEN 'ext_knls'
--     WHEN cd.name ILIKE '%community%' OR cd.name ILIKE '%county%' THEN 'ext_community'
--     WHEN cd.name ILIKE '%library%' OR cd.name ILIKE '%lib%'      THEN 'svc_library'
--     WHEN cd.name ILIKE '%ict%'     OR cd.name ILIKE '%computer%' THEN 'svc_ict'
--     WHEN cd.name ILIKE '%games%'   OR cd.name ILIKE '%sports%'   THEN 'svc_games'
--     WHEN cd.name ILIKE '%kitchen%' OR cd.name ILIKE '%cafeteria%'THEN 'svc_kitchen'
--     WHEN cd.name ILIKE '%store%'   OR cd.name ILIKE '%stores%'   THEN 'svc_store'
--     ELSE NULL
--   END
-- FROM clearance_stages cs
-- JOIN clearance_departments cd ON cs.clearance_department_id = cd.id
-- WHERE ca.clearance_stage_id = cs.id
--   AND ca.approver_category IS NULL;
