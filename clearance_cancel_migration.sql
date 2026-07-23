-- Allow trainees to stop/cancel their own clearance process.
-- Safe to re-run.

DO $$
BEGIN
  ALTER TABLE clearance_requests DROP CONSTRAINT IF EXISTS clearance_requests_status_check;
  ALTER TABLE clearance_requests
    ADD CONSTRAINT clearance_requests_status_check
    CHECK (status IN (
      'pending', 'in_progress', 'completed', 'rejected', 'returned', 'cancelled'
    ));
EXCEPTION
  WHEN others THEN
    RAISE NOTICE 'clearance_requests status check update skipped: %', SQLERRM;
END $$;

ALTER TABLE clearance_requests
  ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS cancelled_by UUID REFERENCES user_profiles(id);
