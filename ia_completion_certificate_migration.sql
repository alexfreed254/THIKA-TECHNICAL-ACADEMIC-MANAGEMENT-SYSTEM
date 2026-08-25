-- Industrial Attachment Completion Certificate
-- Run in Supabase SQL Editor after backup.
-- Adds mentor completion confirmation + certificate registry with dual status:
--   system: attachment completed (industrial_attachments.status = 'completed')
--   company: pending_company_stamp | company_stamped | verified

-- ── 1. Mentor completion confirmation on attachment ──────────────────────────
ALTER TABLE industrial_attachments
    ADD COLUMN IF NOT EXISTS mentor_completion_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mentor_completion_confirmed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS mentor_completion_confirmed_by UUID
        REFERENCES user_profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS mentor_completion_notes TEXT;

-- ── 2. Certificate registry (immutable snapshot + verification) ───────────────
CREATE TABLE IF NOT EXISTS attachment_certificates (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    attachment_id UUID NOT NULL UNIQUE
        REFERENCES industrial_attachments(id) ON DELETE CASCADE,
    certificate_number TEXT NOT NULL UNIQUE,

    -- Snapshot at issuance (survives later profile/company edits)
    trainee_name TEXT NOT NULL,
    admission_no TEXT,
    programme TEXT,
    department_name TEXT,
    institution_name TEXT NOT NULL DEFAULT 'Thika Technical Training Institute',
    company_name TEXT NOT NULL,
    company_department TEXT,
    attachment_start DATE,
    attachment_end DATE,
    supervisor_name TEXT,
    liaison_officer_name TEXT,

    -- Dual status model
    -- system_status mirrors attachment completion; kept for verify page clarity
    system_status TEXT NOT NULL DEFAULT 'attachment_completed'
        CHECK (system_status IN ('attachment_completed')),
    company_certification_status TEXT NOT NULL DEFAULT 'pending_company_stamp'
        CHECK (company_certification_status IN (
            'pending_company_stamp', 'company_stamped', 'verified'
        )),

    -- Digital verification record
    issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    issued_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    company_confirmed_at TIMESTAMPTZ,
    company_confirmed_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    company_signed_url TEXT,
    company_signed_path TEXT,
    company_signed_uploaded_at TIMESTAMPTZ,
    verified_at TIMESTAMPTZ,
    verified_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    verification_notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_attachment_certificates_number
    ON attachment_certificates(certificate_number);
CREATE INDEX IF NOT EXISTS idx_attachment_certificates_company_status
    ON attachment_certificates(company_certification_status);
CREATE INDEX IF NOT EXISTS idx_attachment_certificates_issued
    ON attachment_certificates(issued_at DESC);

DROP TRIGGER IF EXISTS trg_attachment_certificates_updated_at ON attachment_certificates;
CREATE TRIGGER trg_attachment_certificates_updated_at
    BEFORE UPDATE ON attachment_certificates
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── 3. Yearly sequence helper for TTTI-IA-YYYY-NNNNNN ────────────────────────
CREATE TABLE IF NOT EXISTS attachment_certificate_sequences (
    year INTEGER PRIMARY KEY,
    last_value INTEGER NOT NULL DEFAULT 0
);

-- ── 4. RLS (service role used by Flask; policies for authenticated safety) ────
ALTER TABLE attachment_certificates ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS attachment_certificates_super_admin ON attachment_certificates;
CREATE POLICY attachment_certificates_super_admin ON attachment_certificates
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

DROP POLICY IF EXISTS attachment_certificates_liaison ON attachment_certificates;
CREATE POLICY attachment_certificates_liaison ON attachment_certificates
    FOR ALL TO authenticated
    USING (current_user_role() = 'liaison_officer' AND current_user_active())
    WITH CHECK (current_user_role() = 'liaison_officer' AND current_user_active());

DROP POLICY IF EXISTS attachment_certificates_student_read ON attachment_certificates;
CREATE POLICY attachment_certificates_student_read ON attachment_certificates
    FOR SELECT TO authenticated
    USING (
        current_user_role() = 'student'
        AND attachment_id IN (
            SELECT id FROM industrial_attachments WHERE student_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS attachment_certificates_mentor_read ON attachment_certificates;
CREATE POLICY attachment_certificates_mentor_read ON attachment_certificates
    FOR SELECT TO authenticated
    USING (
        current_user_role() = 'industry_mentor'
        AND attachment_id IN (
            SELECT id FROM industrial_attachments
            WHERE company_id IN (
                SELECT company_id FROM mentors WHERE user_id = auth.uid()
            )
        )
    );

-- Public verification is done via Flask service_role; no anon SELECT needed.
