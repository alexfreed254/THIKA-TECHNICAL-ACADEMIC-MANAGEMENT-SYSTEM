-- Attachment workflow: placement-first model (trainee finds company externally)
-- Run in Supabase SQL editor after backup.

-- ── 1. Attachment application periods (liaison opens window) ─────────────────
CREATE TABLE IF NOT EXISTS attachment_periods (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    term TEXT NOT NULL CHECK (term IN ('Jan-Apr', 'May-Aug', 'Sept-Dec')),
    year INTEGER NOT NULL,
    application_opens DATE NOT NULL,
    application_closes DATE NOT NULL,
    placement_deadline DATE,
    introduction_letter_url TEXT,
    introduction_letter_path TEXT,
    notes TEXT,
    is_open BOOLEAN NOT NULL DEFAULT FALSE,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(term, year)
);

CREATE TABLE IF NOT EXISTS attachment_period_eligibility (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    period_id UUID NOT NULL REFERENCES attachment_periods(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    is_eligible BOOLEAN NOT NULL DEFAULT TRUE,
    introduction_letter_issued BOOLEAN NOT NULL DEFAULT FALSE,
    approved_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(period_id, student_id)
);

CREATE INDEX IF NOT EXISTS idx_attachment_period_eligibility_student
    ON attachment_period_eligibility(student_id);

-- ── 2. Extend companies & attachments ───────────────────────────────────────
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS county TEXT,
    ADD COLUMN IF NOT EXISTS company_department TEXT;

ALTER TABLE industrial_attachments
    ADD COLUMN IF NOT EXISTS period_id UUID REFERENCES attachment_periods(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS institute_trainer_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS placement_status TEXT DEFAULT 'pending_verification',
    ADD COLUMN IF NOT EXISTS liaison_review_comments TEXT,
    ADD COLUMN IF NOT EXISTS liaison_reviewed_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS liaison_reviewed_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS supervisor_email TEXT,
    ADD COLUMN IF NOT EXISTS supervisor_position TEXT,
    ADD COLUMN IF NOT EXISTS expected_working_hours TEXT,
    ADD COLUMN IF NOT EXISTS introduction_letter_url TEXT,
    ADD COLUMN IF NOT EXISTS offer_letter_url TEXT,
    ADD COLUMN IF NOT EXISTS company_stamp_url TEXT,
    ADD COLUMN IF NOT EXISTS signed_acceptance_form_url TEXT,
    ADD COLUMN IF NOT EXISTS placement_details JSONB DEFAULT '{}'::jsonb;

ALTER TABLE industrial_attachments
    DROP CONSTRAINT IF EXISTS industrial_attachments_placement_status_check;

ALTER TABLE industrial_attachments
    ADD CONSTRAINT industrial_attachments_placement_status_check
    CHECK (placement_status IN (
        'pending_verification', 'needs_info', 'verified', 'rejected'
    ));

-- ── 3. Weekly attendance (industry mentor / supervisor) ─────────────────────
CREATE TABLE IF NOT EXISTS attachment_weekly_attendance (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    attachment_id UUID NOT NULL REFERENCES industrial_attachments(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    days_present INTEGER NOT NULL DEFAULT 0 CHECK (days_present >= 0 AND days_present <= 7),
    days_absent INTEGER NOT NULL DEFAULT 0 CHECK (days_absent >= 0 AND days_absent <= 7),
    mentor_comments TEXT,
    marked_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    marked_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'submitted'
        CHECK (status IN ('pending', 'submitted', 'approved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(attachment_id, week_start)
);

-- ── 4. Final grading (configurable weightings) ─────────────────────────────
CREATE TABLE IF NOT EXISTS attachment_grading_config (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_id UUID REFERENCES departments(id) ON DELETE CASCADE,
    weight_gps_attendance NUMERIC(5,2) NOT NULL DEFAULT 10,
    weight_logbook NUMERIC(5,2) NOT NULL DEFAULT 20,
    weight_mentor_eval NUMERIC(5,2) NOT NULL DEFAULT 30,
    weight_trainer_assessment NUMERIC(5,2) NOT NULL DEFAULT 30,
    weight_final_report NUMERIC(5,2) NOT NULL DEFAULT 10,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attachment_grades (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    attachment_id UUID NOT NULL UNIQUE REFERENCES industrial_attachments(id) ON DELETE CASCADE,
    score_gps_attendance NUMERIC(5,2),
    score_logbook NUMERIC(5,2),
    score_mentor_eval NUMERIC(5,2),
    score_trainer_assessment NUMERIC(5,2),
    score_final_report NUMERIC(5,2),
    mentor_practical_skills NUMERIC(5,2),
    mentor_theory_application NUMERIC(5,2),
    mentor_problem_solving NUMERIC(5,2),
    mentor_safety NUMERIC(5,2),
    mentor_communication NUMERIC(5,2),
    mentor_attendance NUMERIC(5,2),
    mentor_professionalism NUMERIC(5,2),
    weighted_total NUMERIC(6,2),
    final_grade TEXT CHECK (final_grade IN ('NYC', 'C', 'P', 'M')),
    graded_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    graded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO attachment_grading_config (department_id, is_active)
SELECT NULL, TRUE
WHERE NOT EXISTS (SELECT 1 FROM attachment_grading_config WHERE department_id IS NULL);

-- ── 5. Mentoring tool / hardcopy logbook uploads ─────────────────────────────
-- Allows a trainee to upload multiple scanned PDFs of their mentoring tool
-- or hardcopy logbook for review by the liaison officer, dept admin & super admin.
CREATE TABLE IF NOT EXISTS mentoring_tool_uploads (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id    UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    attachment_id UUID REFERENCES industrial_attachments(id) ON DELETE SET NULL,
    title         TEXT NOT NULL,
    description   TEXT,
    file_url      TEXT NOT NULL,
    storage_path  TEXT NOT NULL,
    file_name     TEXT NOT NULL,
    file_size     BIGINT,
    uploaded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_mentoring_tool_uploads_student
    ON mentoring_tool_uploads(student_id, uploaded_at DESC);

-- ── 6. Exam bookings: persist year, series and term ──────────────────────────
-- exam_session had constraint ('morning','afternoon','evening') which prevented
-- storing the numeric series (1/2/3).  Add dedicated columns instead.
ALTER TABLE exam_bookings
    ADD COLUMN IF NOT EXISTS exam_year     INTEGER,
    ADD COLUMN IF NOT EXISTS exam_series_no INTEGER,
    ADD COLUMN IF NOT EXISTS exam_term      INTEGER;
