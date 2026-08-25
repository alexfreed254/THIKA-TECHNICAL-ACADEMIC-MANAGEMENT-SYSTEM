-- ============================================================
-- Clearance: Digital → Final Clearance Form → Physical Sign-off
-- Run in Supabase SQL Editor. Safe to re-run (IF NOT EXISTS).
-- ============================================================
-- After all digital clearances (Stage 1 + Home HOD) are approved:
--   status = digital_complete, Final Clearance Form unlocks for download.
-- Physical offices (Dean, Finance, Principal) are recorded in
-- final_clearance_approvals by Registrar / authorized admin.
-- Only then status = completed (FINAL CLEARANCE APPROVED).
-- ============================================================

-- 1. Status values
DO $$
BEGIN
  ALTER TABLE clearance_requests DROP CONSTRAINT IF EXISTS clearance_requests_status_check;
  ALTER TABLE clearance_requests
    ADD CONSTRAINT clearance_requests_status_check
    CHECK (status IN (
      'pending', 'in_progress', 'returned', 'rejected', 'cancelled',
      'digital_complete', 'completed'
    ));
EXCEPTION WHEN others THEN
  RAISE NOTICE 'clearance_requests status check update skipped: %', SQLERRM;
END $$;

-- 2. Form + final-status columns on clearance_requests
ALTER TABLE clearance_requests
  ADD COLUMN IF NOT EXISTS form_generated_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS form_downloaded_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS final_status TEXT;

-- final_status values (soft enum via check when possible)
DO $$
BEGIN
  ALTER TABLE clearance_requests DROP CONSTRAINT IF EXISTS clearance_requests_final_status_check;
  ALTER TABLE clearance_requests
    ADD CONSTRAINT clearance_requests_final_status_check
    CHECK (
      final_status IS NULL
      OR final_status IN (
        'form_generated',
        'form_downloaded',
        'physical_in_progress',
        'final_clearance_approved'
      )
    );
EXCEPTION WHEN others THEN
  RAISE NOTICE 'final_status check skipped: %', SQLERRM;
END $$;

-- 3. Physical / senior-office approvals (Dean, Finance, Principal)
CREATE TABLE IF NOT EXISTS final_clearance_approvals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    clearance_request_id UUID NOT NULL
        REFERENCES clearance_requests(id) ON DELETE CASCADE,
    office TEXT NOT NULL
        CHECK (office IN (
            'dean_of_students',
            'finance',
            'principal',
            'deputy_principal_academics'
        )),
    approved BOOLEAN NOT NULL DEFAULT FALSE,
    officer_name TEXT,
    comment TEXT,
    approved_at TIMESTAMPTZ,
    recorded_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (clearance_request_id, office)
);

CREATE INDEX IF NOT EXISTS idx_final_clearance_approvals_request
    ON final_clearance_approvals(clearance_request_id);

DROP TRIGGER IF EXISTS trg_final_clearance_approvals_updated_at ON final_clearance_approvals;
CREATE TRIGGER trg_final_clearance_approvals_updated_at
    BEFORE UPDATE ON final_clearance_approvals
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- 4. RLS
ALTER TABLE final_clearance_approvals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS final_clearance_approvals_super_admin ON final_clearance_approvals;
CREATE POLICY final_clearance_approvals_super_admin ON final_clearance_approvals
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

DROP POLICY IF EXISTS final_clearance_approvals_oversight ON final_clearance_approvals;
CREATE POLICY final_clearance_approvals_oversight ON final_clearance_approvals
    FOR ALL TO authenticated
    USING (
        current_user_role() IN (
            'registrar', 'deputy_principal', 'dean_students',
            'finance_officer', 'super_admin'
        )
        AND current_user_active()
    )
    WITH CHECK (
        current_user_role() IN (
            'registrar', 'deputy_principal', 'dean_students',
            'finance_officer', 'super_admin'
        )
        AND current_user_active()
    );

DROP POLICY IF EXISTS final_clearance_approvals_student_read ON final_clearance_approvals;
CREATE POLICY final_clearance_approvals_student_read ON final_clearance_approvals
    FOR SELECT TO authenticated
    USING (
        current_user_role() = 'student'
        AND clearance_request_id IN (
            SELECT id FROM clearance_requests WHERE student_id = auth.uid()
        )
    );

-- 5. Backfill: existing status=completed stay completed (already fully done).
--    No automatic rewrite to digital_complete — those already had certificates issued.
