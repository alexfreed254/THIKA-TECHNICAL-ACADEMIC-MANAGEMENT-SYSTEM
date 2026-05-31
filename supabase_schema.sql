-- ============================================================
-- THIKA TECHNICAL TRAINING INSTITUTE
-- Unified Academic Management System — Supabase Schema
-- Combines Attendance Management + E-Portfolio Management
-- Run this entire file in the Supabase SQL Editor
-- ============================================================

-- ────────────────────────────────────────────────────────────
-- 0. EXTENSIONS
-- ────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ────────────────────────────────────────────────────────────
-- 1. CORE LOOKUP TABLES
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS departments (
    id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(50) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS courses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    code            TEXT NOT NULL,
    department_id   UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    created_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(code, department_id)
);

CREATE TABLE IF NOT EXISTS classes (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL UNIQUE,
    course_id       UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    department_id   UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    intake_year     INTEGER,
    intake_month    TEXT,
    level           TEXT CHECK (level IN ('Level 3','Level 4','Level 5','Level 6')),
    cycle           TEXT CHECK (cycle IN ('Cycle 1','Cycle 2','Cycle 3','Cycle 3 Moderated')),
    created_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS units (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    code          VARCHAR(50)  NOT NULL,
    name          VARCHAR(200) NOT NULL,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    course_id     UUID REFERENCES courses(id) ON DELETE CASCADE,
    created_by    UUID,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(code, department_id)
);

-- ────────────────────────────────────────────────────────────
-- 2. USER PROFILE TABLE
--    Mirrors auth.users; one row per Supabase Auth user.
--    role: 'super_admin' | 'dept_admin' | 'trainer' | 'student'
--    Hybrid auth: Staff use Supabase Auth, Students use password_hash
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS user_profiles (
    id                  UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email               VARCHAR(100) NOT NULL UNIQUE,
    full_name           VARCHAR(200) NOT NULL,
    role                VARCHAR(20)  NOT NULL CHECK (role IN ('super_admin','dept_admin','trainer','student','employer','examination_officer','industry_mentor','internal_verifier','sports_hod','environment_hod','dean_students','library_hod','finance_officer','registrar','deputy_principal','quality_assurance_officer')),
    department_id       UUID REFERENCES departments(id) ON DELETE SET NULL,
    admission_no        VARCHAR(50)  UNIQUE,
    mobile_number       VARCHAR(20),
    staff_no            VARCHAR(50)  UNIQUE,
    password_hash       TEXT,
    must_change_password BOOLEAN DEFAULT FALSE,
    passport_file_path  TEXT,
    passport_file_name  TEXT,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_by          UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login          TIMESTAMPTZ
);

-- Keep updated_at current automatically
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS trg_user_profiles_updated_at ON user_profiles;

CREATE TRIGGER trg_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ────────────────────────────────────────────────────────────
-- ADD FOREIGN KEY CONSTRAINTS FOR TABLES CREATED BEFORE user_profiles
-- ────────────────────────────────────────────────────────────

ALTER TABLE courses DROP CONSTRAINT IF EXISTS courses_created_by_fkey;
ALTER TABLE courses ADD CONSTRAINT courses_created_by_fkey 
    FOREIGN KEY (created_by) REFERENCES user_profiles(id) ON DELETE SET NULL;

ALTER TABLE classes DROP CONSTRAINT IF EXISTS classes_created_by_fkey;
ALTER TABLE classes ADD CONSTRAINT classes_created_by_fkey 
    FOREIGN KEY (created_by) REFERENCES user_profiles(id) ON DELETE SET NULL;

ALTER TABLE units DROP CONSTRAINT IF EXISTS units_created_by_fkey;
ALTER TABLE units ADD CONSTRAINT units_created_by_fkey 
    FOREIGN KEY (created_by) REFERENCES user_profiles(id) ON DELETE SET NULL;

-- ────────────────────────────────────────────────────────────
-- 3. CLASS–UNIT ASSIGNMENTS
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS class_units (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    class_id   UUID NOT NULL REFERENCES classes(id)   ON DELETE CASCADE,
    unit_id    UUID NOT NULL REFERENCES units(id)     ON DELETE CASCADE,
    trainer_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    year       INT NOT NULL DEFAULT EXTRACT(YEAR FROM NOW())::INT,
    term       INT NOT NULL DEFAULT 1,
    UNIQUE (class_id, unit_id, year, term)
);

-- ────────────────────────────────────────────────────────────
-- 4. TRAINER ↔ UNIT ASSIGNMENTS
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trainer_units (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trainer_id  UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id     UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(trainer_id, unit_id)
);

-- ────────────────────────────────────────────────────────────
-- 5. STUDENT ENROLLMENT
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS enrollments (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id  UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    class_id    UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id, class_id)
);

-- ────────────────────────────────────────────────────────────
-- 6. ATTENDANCE (from Attendance System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS attendance (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id      UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id         UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    unit_code       VARCHAR(50),
    trainer_id      UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    lesson          VARCHAR(10) NOT NULL,
    week            INT NOT NULL,
    year            INT NOT NULL DEFAULT EXTRACT(YEAR FROM NOW())::INT,
    term            INT NOT NULL DEFAULT 1,
    status          VARCHAR(10) NOT NULL CHECK (status IN ('present','absent')),
    attendance_date TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 7. CLASS EVENTS (holidays / academic trips)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS class_events (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    class_id   UUID NOT NULL REFERENCES classes(id)   ON DELETE CASCADE,
    unit_id    UUID REFERENCES units(id) ON DELETE SET NULL,
    trainer_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    event_type VARCHAR(30) NOT NULL CHECK (event_type IN ('holiday','academic_trip')),
    week       INT NOT NULL,
    lesson     VARCHAR(10) NOT NULL,
    year       INT NOT NULL DEFAULT EXTRACT(YEAR FROM NOW())::INT,
    term       INT NOT NULL DEFAULT 1,
    note       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (class_id, unit_id, trainer_id, week, lesson, year, term)
);

-- ────────────────────────────────────────────────────────────
-- 8. ASSESSMENTS (from E-Portfolio System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assessments (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id      UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    class_id        UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    unit_id         UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    assessment_type TEXT NOT NULL CHECK (assessment_type IN ('PRACTICAL','THEORY','ORAL','oral','practical','theory','written','Formative','Summative')),
    assessment_no   INTEGER NOT NULL,
    term            INTEGER NOT NULL CHECK (term IN (1,2,3)),
    cycle           INTEGER NOT NULL CHECK (cycle IN (1,2,3)),
    year            INTEGER NOT NULL,
    -- PDF script file (stored in Supabase Storage)
    script_file_path    TEXT,
    script_file_name    TEXT,
    script_file_size    BIGINT,
    -- Status
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','approved','rejected')),
    reviewed_by     UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    review_note     TEXT,
    -- Metadata
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for assessments updated_at
DROP TRIGGER IF EXISTS trg_assessments_updated_at ON assessments;
CREATE TRIGGER trg_assessments_updated_at
    BEFORE UPDATE ON assessments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ────────────────────────────────────────────────────────────
-- 9. EVIDENCE (photos/videos linked to an assessment)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS evidence (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    assessment_id   UUID NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
    student_id      UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    file_path       TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_type       TEXT NOT NULL CHECK (file_type IN ('photo','video')),
    file_size       BIGINT,
    caption         TEXT,
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 10. EMPLOYERS (Job Portal System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS employers (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    profile_id UUID UNIQUE REFERENCES user_profiles(id) ON DELETE CASCADE,
    company_name TEXT NOT NULL,
    official_email TEXT NOT NULL UNIQUE,
    phone TEXT,
    location TEXT,
    website TEXT,
    industry TEXT,
    is_verified BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger for employers updated_at
DROP TRIGGER IF EXISTS trg_employers_updated_at ON employers;
CREATE TRIGGER trg_employers_updated_at
    BEFORE UPDATE ON employers
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ────────────────────────────────────────────────────────────
-- 11. EMPLOYER VERIFICATIONS
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS employer_verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trainee_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    employer_id UUID REFERENCES employers(id) ON DELETE SET NULL,
    verification_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected')),
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    review_note TEXT
);

-- ────────────────────────────────────────────────────────────
-- 12. JOB POSTINGS (Job Portal System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_postings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    employer_id UUID REFERENCES employers(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('job', 'internship', 'attachment', 'apprenticeship')),
    description TEXT NOT NULL,
    requirements TEXT,
    skills_required TEXT[],
    department_preference TEXT,
    location TEXT,
    salary_range TEXT,
    deadline DATE,
    slots INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Trigger for job_postings updated_at
DROP TRIGGER IF EXISTS trg_job_postings_updated_at ON job_postings;
CREATE TRIGGER trg_job_postings_updated_at
    BEFORE UPDATE ON job_postings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_jobs_employer ON job_postings(employer_id);
CREATE INDEX IF NOT EXISTS idx_jobs_active ON job_postings(is_active, created_at DESC);

-- ────────────────────────────────────────────────────────────
-- 13. JOB APPLICATIONS (Job Portal System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS job_applications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    job_id UUID NOT NULL REFERENCES job_postings(id) ON DELETE CASCADE,
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    cover_note TEXT,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'reviewed', 'shortlisted', 'rejected', 'accepted')),
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (job_id, student_id)
);

-- Trigger for job_applications updated_at
DROP TRIGGER IF EXISTS trg_job_applications_updated_at ON job_applications;
CREATE TRIGGER trg_job_applications_updated_at
    BEFORE UPDATE ON job_applications
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_applications_job ON job_applications(job_id);
CREATE INDEX IF NOT EXISTS idx_applications_student ON job_applications(student_id);
CREATE INDEX IF NOT EXISTS idx_applications_status ON job_applications(status);

-- ────────────────────────────────────────────────────────────
-- 14. SYSTEM AUDIT LOG
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS system_logs (
    id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    actor_id   UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    actor_role VARCHAR(20),
    action     VARCHAR(100) NOT NULL,
    target     VARCHAR(200),
    detail     JSONB,
    ip_address INET,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ────────────────────────────────────────────────────────────
-- 15. NOTIFICATIONS (In-App Notification System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    message     TEXT NOT NULL,
    type        TEXT NOT NULL CHECK (type IN ('info','success','warning','error')),
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    action_url  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, is_read, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id) WHERE is_read = FALSE;

-- ────────────────────────────────────────────────────────────
-- 16. EXAM BOOKINGS (Exam Booking System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS exam_bookings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id UUID REFERENCES units(id) ON DELETE CASCADE,
    exam_date DATE NOT NULL,
    exam_session TEXT CHECK (exam_session IN ('morning','afternoon','evening')),
    exam_venue TEXT,
    purpose TEXT NOT NULL,
    special_requirements TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','rejected','completed')),
    approved_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    rejection_reason TEXT,
    serial_number TEXT UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id, unit_id, exam_date)
);

-- Trigger for exam_bookings updated_at
DROP TRIGGER IF EXISTS trg_exam_bookings_updated_at ON exam_bookings;
CREATE TRIGGER trg_exam_bookings_updated_at
    BEFORE UPDATE ON exam_bookings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_exam_bookings_student ON exam_bookings(student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_exam_bookings_unit ON exam_bookings(unit_id);
CREATE INDEX IF NOT EXISTS idx_exam_bookings_status ON exam_bookings(status);
CREATE INDEX IF NOT EXISTS idx_exam_bookings_date ON exam_bookings(exam_date);

-- ────────────────────────────────────────────────────────────
-- 17. MARKS (Assessment Marks System)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS marks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    trainer_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE SET NULL,
    class_id UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    assessment_type TEXT NOT NULL CHECK (assessment_type IN ('oral','practical','theory','written')),
    assessment_name TEXT NOT NULL,
    term TEXT NOT NULL,
    cycle TEXT,
    year INTEGER NOT NULL,
    marks_obtained NUMERIC(5,2) NOT NULL CHECK (marks_obtained >= 0 AND marks_obtained <= 100),
    max_marks NUMERIC(5,2) DEFAULT 100,
    grade TEXT,
    remarks TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id, unit_id, assessment_name, term, cycle, year)
);

-- Trigger for marks updated_at
DROP TRIGGER IF EXISTS trg_marks_updated_at ON marks;
CREATE TRIGGER trg_marks_updated_at
    BEFORE UPDATE ON marks
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Function to calculate grade based on marks (Competency-Based Grading)
CREATE OR REPLACE FUNCTION calculate_grade(marks NUMERIC)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE
        WHEN marks >= 85 THEN 'M'
        WHEN marks >= 70 THEN 'P'
        WHEN marks >= 50 THEN 'C'
        ELSE 'NYC'
    END;
$$;

-- Function to auto-calculate grade
CREATE OR REPLACE FUNCTION set_grade()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.grade = calculate_grade(NEW.marks_obtained);
    RETURN NEW;
END;
$$;

-- Trigger to auto-calculate grade
DROP TRIGGER IF EXISTS trg_marks_calculate_grade ON marks;
CREATE TRIGGER trg_marks_calculate_grade
    BEFORE INSERT OR UPDATE ON marks
    FOR EACH ROW
    WHEN (NEW.marks_obtained IS NOT NULL)
    EXECUTE FUNCTION set_grade();

CREATE INDEX IF NOT EXISTS idx_marks_student ON marks(student_id, unit_id, year DESC);
CREATE INDEX IF NOT EXISTS idx_marks_unit ON marks(unit_id, year DESC);
CREATE INDEX IF NOT EXISTS idx_marks_trainer ON marks(trainer_id);
CREATE INDEX IF NOT EXISTS idx_marks_class ON marks(class_id);
CREATE INDEX IF NOT EXISTS idx_marks_term ON marks(term, year);

-- ────────────────────────────────────────────────────────────
-- 18. TRAINER DOCUMENTS (Portfolio)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trainer_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trainer_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id UUID REFERENCES units(id) ON DELETE SET NULL,
    class_id UUID REFERENCES classes(id) ON DELETE SET NULL,
    document_type TEXT NOT NULL CHECK (document_type IN (
        'assessment_plan',
        'competency_standard',
        'assessment_tools',
        'marking_guide',
        'written_oral_mark_sheets',
        'observation_checklist',
        'product_checklist',
        'assessment_records',
        'evidence_register',
        'feedback_forms',
        'internal_verification_report',
        'moderation_report',
        'industrial_attachment_plan',
        'mentoring_tools',
        'industrial_attachment_report',
        'trainee_attendance_records',
        'communication_records',
        'assessment_schedule'
    )),
    document_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    file_type TEXT,
    description TEXT,
    academic_year INTEGER,
    term TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for trainer_documents updated_at
DROP TRIGGER IF EXISTS trg_trainer_documents_updated_at ON trainer_documents;
CREATE TRIGGER trg_trainer_documents_updated_at
    BEFORE UPDATE ON trainer_documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_trainer_documents_trainer ON trainer_documents(trainer_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trainer_documents_unit ON trainer_documents(unit_id);
CREATE INDEX IF NOT EXISTS idx_trainer_documents_type ON trainer_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_trainer_documents_year ON trainer_documents(academic_year, term);

-- ────────────────────────────────────────────────────────────
-- 19. TRAINEE DOCUMENTS (Portfolio of Evidence - PoE)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS trainee_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id UUID REFERENCES units(id) ON DELETE SET NULL,
    document_type TEXT NOT NULL CHECK (document_type IN (
        'marked_scripts',
        'practical_products',
        'oral_responses',
        'video_clips',
        'audio_recordings',
        'photo_evidence',
        'self_assessment_forms',
        'industrial_attachment_logbook',
        'workplace_feedback_forms',
        'mentoring_assessment',
        'attachment_attendance_records',
        'poe_compilation'
    )),
    document_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    file_type TEXT,
    description TEXT,
    academic_year INTEGER,
    term TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for trainee_documents updated_at
DROP TRIGGER IF EXISTS trg_trainee_documents_updated_at ON trainee_documents;
CREATE TRIGGER trg_trainee_documents_updated_at
    BEFORE UPDATE ON trainee_documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_trainee_documents_student ON trainee_documents(student_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trainee_documents_unit ON trainee_documents(unit_id);
CREATE INDEX IF NOT EXISTS idx_trainee_documents_type ON trainee_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_trainee_documents_year ON trainee_documents(academic_year, term);

-- ────────────────────────────────────────────────────────────
-- 20. COMPANIES / INDUSTRY PARTNERS (Dual Training)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    industry_classification TEXT NOT NULL CHECK (industry_classification IN (
        'Electrical Engineering',
        'Mechanical Engineering',
        'Information Technology',
        'Civil Engineering',
        'Automotive Engineering',
        'Hospitality',
        'Business Management',
        'Health Sciences',
        'Agriculture',
        'Construction',
        'Manufacturing',
        'Other'
    )),
    address TEXT,
    city TEXT,
    country TEXT DEFAULT 'Kenya',
    postal_code TEXT,
    phone_number TEXT,
    email TEXT,
    website TEXT,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    geofence_radius_meters INTEGER DEFAULT 300,
    available_slots INTEGER DEFAULT 0,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    contact_person TEXT,
    contact_phone TEXT,
    contact_email TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for companies updated_at
DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies;
CREATE TRIGGER trg_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_companies_industry ON companies(industry_classification);
CREATE INDEX IF NOT EXISTS idx_companies_department ON companies(department_id);
CREATE INDEX IF NOT EXISTS idx_companies_location ON companies(latitude, longitude);

-- ────────────────────────────────────────────────────────────
-- 21. INDUSTRY MENTORS
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mentors (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    specialization TEXT,
    years_of_experience INTEGER,
    qualification TEXT,
    license_number TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, company_id)
);

-- Trigger for mentors updated_at
DROP TRIGGER IF EXISTS trg_mentors_updated_at ON mentors;
CREATE TRIGGER trg_mentors_updated_at
    BEFORE UPDATE ON mentors
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_mentors_user ON mentors(user_id);
CREATE INDEX IF NOT EXISTS idx_mentors_company ON mentors(company_id);

-- ────────────────────────────────────────────────────────────
-- 22. INDUSTRIAL ATTACHMENTS
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS industrial_attachments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    mentor_id UUID REFERENCES mentors(id) ON DELETE SET NULL,
    unit_id UUID REFERENCES units(id) ON DELETE SET NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'active', 'completed', 'terminated')) DEFAULT 'pending',
    attachment_goals TEXT,
    learning_objectives TEXT,
    supervisor_notes TEXT,
    final_report TEXT,
    final_grade TEXT CHECK (final_grade IN ('NYC', 'C', 'P', 'M')),
    approved_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    approved_at TIMESTAMPTZ,
    created_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for industrial_attachments updated_at
DROP TRIGGER IF EXISTS trg_industrial_attachments_updated_at ON industrial_attachments;
CREATE TRIGGER trg_industrial_attachments_updated_at
    BEFORE UPDATE ON industrial_attachments
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_industrial_attachments_student ON industrial_attachments(student_id);
CREATE INDEX IF NOT EXISTS idx_industrial_attachments_company ON industrial_attachments(company_id);
CREATE INDEX IF NOT EXISTS idx_industrial_attachments_mentor ON industrial_attachments(mentor_id);
CREATE INDEX IF NOT EXISTS idx_industrial_attachments_status ON industrial_attachments(status);
CREATE INDEX IF NOT EXISTS idx_industrial_attachments_dates ON industrial_attachments(start_date, end_date);

-- ────────────────────────────────────────────────────────────
-- 23. LOCATION LOGS (GPS Tracking)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS location_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    attachment_id UUID REFERENCES industrial_attachments(id) ON DELETE CASCADE,
    latitude DECIMAL(10, 8) NOT NULL,
    longitude DECIMAL(11, 8) NOT NULL,
    accuracy_meters DECIMAL(10, 2),
    is_within_geofence BOOLEAN NOT NULL,
    check_in_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    check_out_time TIMESTAMPTZ,
    location_method TEXT CHECK (location_method IN ('gps', 'network', 'manual')),
    device_info TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_location_logs_student ON location_logs(student_id, check_in_time DESC);
CREATE INDEX IF NOT EXISTS idx_location_logs_attachment ON location_logs(attachment_id);
CREATE INDEX IF NOT EXISTS idx_location_logs_geofence ON location_logs(is_within_geofence);

-- ────────────────────────────────────────────────────────────
-- 24. DIGITAL LOGBOOK
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS digital_logbook (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    attachment_id UUID NOT NULL REFERENCES industrial_attachments(id) ON DELETE CASCADE,
    log_date DATE NOT NULL,
    tasks_performed TEXT NOT NULL,
    skills_applied TEXT,
    hours_worked DECIMAL(5, 2),
    challenges_encountered TEXT,
    achievements TEXT,
    evidence_urls TEXT[],
    mentor_comments TEXT,
    mentor_approval_status TEXT CHECK (mentor_approval_status IN ('pending', 'approved', 'rejected')) DEFAULT 'pending',
    mentor_approved_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    mentor_approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for digital_logbook updated_at
DROP TRIGGER IF EXISTS trg_digital_logbook_updated_at ON digital_logbook;
CREATE TRIGGER trg_digital_logbook_updated_at
    BEFORE UPDATE ON digital_logbook
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_digital_logbook_student ON digital_logbook(student_id, log_date DESC);
CREATE INDEX IF NOT EXISTS idx_digital_logbook_attachment ON digital_logbook(attachment_id);
CREATE INDEX IF NOT EXISTS idx_digital_logbook_approval ON digital_logbook(mentor_approval_status);

-- ────────────────────────────────────────────────────────────
-- 25. COMPETENCY TRACKING
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS competency_tracking (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    attachment_id UUID REFERENCES industrial_attachments(id) ON DELETE CASCADE,
    unit_id UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    competency_element TEXT NOT NULL,
    performance_criteria TEXT,
    evidence_provided TEXT,
    assessment_method TEXT CHECK (assessment_method IN ('observation', 'product', 'oral', 'written')),
    competency_status TEXT NOT NULL CHECK (competency_status IN ('NYC', 'C', 'P', 'M')) DEFAULT 'NYC',
    assessed_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    assessment_date DATE,
    assessor_comments TEXT,
    verification_status TEXT CHECK (verification_status IN ('pending', 'verified', 'rejected')) DEFAULT 'pending',
    verified_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    verified_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger for competency_tracking updated_at
DROP TRIGGER IF EXISTS trg_competency_tracking_updated_at ON competency_tracking;
CREATE TRIGGER trg_competency_tracking_updated_at
    BEFORE UPDATE ON competency_tracking
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_competency_tracking_student ON competency_tracking(student_id);
CREATE INDEX IF NOT EXISTS idx_competency_tracking_attachment ON competency_tracking(attachment_id);
CREATE INDEX IF NOT EXISTS idx_competency_tracking_unit ON competency_tracking(unit_id);
CREATE INDEX IF NOT EXISTS idx_competency_tracking_status ON competency_tracking(competency_status);

-- ────────────────────────────────────────────────────────────
-- 11. HELPER FUNCTIONS (used by RLS policies)
-- ────────────────────────────────────────────────────────────

-- Returns the role of the currently authenticated user
CREATE OR REPLACE FUNCTION current_user_role()
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT role FROM user_profiles WHERE id = auth.uid();
$$;

-- Returns the department_id of the currently authenticated user
CREATE OR REPLACE FUNCTION current_user_dept()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT department_id FROM user_profiles WHERE id = auth.uid();
$$;

-- Returns TRUE if the current user is active
CREATE OR REPLACE FUNCTION current_user_active()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER AS $$
    SELECT COALESCE(is_active, FALSE) FROM user_profiles WHERE id = auth.uid();
$$;

-- ────────────────────────────────────────────────────────────
-- 12. ROW LEVEL SECURITY
-- ────────────────────────────────────────────────────────────

ALTER TABLE departments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE courses       ENABLE ROW LEVEL SECURITY;
ALTER TABLE classes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE units         ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE class_units   ENABLE ROW LEVEL SECURITY;
ALTER TABLE trainer_units ENABLE ROW LEVEL SECURITY;
ALTER TABLE enrollments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE attendance    ENABLE ROW LEVEL SECURITY;
ALTER TABLE class_events  ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE evidence      ENABLE ROW LEVEL SECURITY;
ALTER TABLE employers     ENABLE ROW LEVEL SECURITY;
ALTER TABLE employer_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_postings  ENABLE ROW LEVEL SECURITY;
ALTER TABLE job_applications ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_logs   ENABLE ROW LEVEL SECURITY;

-- ── departments ──────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS dept_super_admin ON departments;
CREATE POLICY dept_super_admin ON departments
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Dept admin: read own department
DROP POLICY IF EXISTS dept_dept_admin_read ON departments;
CREATE POLICY dept_dept_admin_read ON departments
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = id);

-- ── user_profiles ─────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS user_profiles_super_admin ON user_profiles;
CREATE POLICY user_profiles_super_admin ON user_profiles
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Dept admin: read users in own department
DROP POLICY IF EXISTS user_profiles_dept_admin_read ON user_profiles;
CREATE POLICY user_profiles_dept_admin_read ON user_profiles
    FOR SELECT TO authenticated
    USING (current_user_role() IN ('dept_admin', 'trainer') AND current_user_dept() = department_id);

-- Users can read own profile
DROP POLICY IF EXISTS user_profiles_own_read ON user_profiles;
CREATE POLICY user_profiles_own_read ON user_profiles
    FOR SELECT TO authenticated
    USING (id = auth.uid());

-- ── courses ─────────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS courses_super_admin ON courses;
CREATE POLICY courses_super_admin ON courses
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Dept admin: read courses in own department
DROP POLICY IF EXISTS courses_dept_admin_read ON courses;
CREATE POLICY courses_dept_admin_read ON courses
    FOR SELECT TO authenticated
    USING (current_user_role() IN ('dept_admin', 'trainer') AND current_user_dept() = department_id);

-- ── classes ─────────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS classes_super_admin ON classes;
CREATE POLICY classes_super_admin ON classes
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Dept admin: full access to own department
DROP POLICY IF EXISTS classes_dept_admin ON classes;
CREATE POLICY classes_dept_admin ON classes
    FOR ALL TO authenticated
    USING (current_user_role() IN ('dept_admin', 'trainer') AND current_user_dept() = department_id)
    WITH CHECK (current_user_role() IN ('dept_admin', 'trainer') AND current_user_dept() = department_id);

-- Students: read own class
DROP POLICY IF EXISTS classes_student_read ON classes;
CREATE POLICY classes_student_read ON classes
    FOR SELECT TO authenticated
    USING (current_user_role() = 'student' AND id IN (
        SELECT class_id FROM enrollments WHERE student_id = auth.uid()
    ));

-- ── units ───────────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS units_super_admin ON units;
CREATE POLICY units_super_admin ON units
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Dept admin/trainer: read units in own department
DROP POLICY IF EXISTS units_dept_read ON units;
CREATE POLICY units_dept_read ON units
    FOR SELECT TO authenticated
    USING (current_user_role() IN ('dept_admin', 'trainer') AND current_user_dept() = department_id);

-- ── attendance ──────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS attendance_super_admin ON attendance;
CREATE POLICY attendance_super_admin ON attendance
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Trainer: full access to own units
DROP POLICY IF EXISTS attendance_trainer ON attendance;
CREATE POLICY attendance_trainer ON attendance
    FOR ALL TO authenticated
    USING (current_user_role() = 'trainer' AND trainer_id = auth.uid())
    WITH CHECK (current_user_role() = 'trainer' AND trainer_id = auth.uid());

-- Dept admin: read attendance in own department
DROP POLICY IF EXISTS attendance_dept_admin_read ON attendance;
CREATE POLICY attendance_dept_admin_read ON attendance
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM units WHERE id = attendance.unit_id
    ));

-- Student: read own attendance
DROP POLICY IF EXISTS attendance_student_read ON attendance;
CREATE POLICY attendance_student_read ON attendance
    FOR SELECT TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid());

-- ── assessments ─────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS assessments_super_admin ON assessments;
CREATE POLICY assessments_super_admin ON assessments
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Trainer: full access to assigned units
DROP POLICY IF EXISTS assessments_trainer ON assessments;
CREATE POLICY assessments_trainer ON assessments
    FOR ALL TO authenticated
    USING (current_user_role() = 'trainer' AND unit_id IN (
        SELECT unit_id FROM trainer_units WHERE trainer_id = auth.uid()
    ))
    WITH CHECK (current_user_role() = 'trainer' AND unit_id IN (
        SELECT unit_id FROM trainer_units WHERE trainer_id = auth.uid()
    ));

-- Dept admin: read assessments in own department
DROP POLICY IF EXISTS assessments_dept_admin_read ON assessments;
CREATE POLICY assessments_dept_admin_read ON assessments
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM units WHERE id = assessments.unit_id
    ));

-- Student: full access to own assessments
DROP POLICY IF EXISTS assessments_student ON assessments;
CREATE POLICY assessments_student ON assessments
    FOR ALL TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid())
    WITH CHECK (current_user_role() = 'student' AND student_id = auth.uid());

-- ── evidence ────────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS evidence_super_admin ON evidence;
CREATE POLICY evidence_super_admin ON evidence
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Trainer: read evidence for assigned units
DROP POLICY IF EXISTS evidence_trainer_read ON evidence;
CREATE POLICY evidence_trainer_read ON evidence
    FOR SELECT TO authenticated
    USING (current_user_role() = 'trainer' AND assessment_id IN (
        SELECT id FROM assessments WHERE unit_id IN (
            SELECT unit_id FROM trainer_units WHERE trainer_id = auth.uid()
        )
    ));

-- Student: full access to own evidence
DROP POLICY IF EXISTS evidence_student ON evidence;
CREATE POLICY evidence_student ON evidence
    FOR ALL TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid())
    WITH CHECK (current_user_role() = 'student' AND student_id = auth.uid());

-- ── system_logs ─────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS system_logs_super_admin ON system_logs;
CREATE POLICY system_logs_super_admin ON system_logs
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── employers ───────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS employers_super_admin ON employers;
CREATE POLICY employers_super_admin ON employers
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Employers can view and update own record
DROP POLICY IF EXISTS employers_own_read ON employers;
CREATE POLICY employers_own_read ON employers
    FOR SELECT TO authenticated
    USING (profile_id = auth.uid());

DROP POLICY IF EXISTS employers_own_update ON employers;
CREATE POLICY employers_own_update ON employers
    FOR UPDATE TO authenticated
    USING (profile_id = auth.uid());

-- Public can view verified employers
DROP POLICY IF EXISTS employers_public_read ON employers;
CREATE POLICY employers_public_read ON employers
    FOR SELECT TO authenticated
    USING (is_verified = true);

-- ── employer_verifications ─────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS employer_verifications_super_admin ON employer_verifications;
CREATE POLICY employer_verifications_super_admin ON employer_verifications
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Students can view own verifications
DROP POLICY IF EXISTS employer_verifications_student_read ON employer_verifications;
CREATE POLICY employer_verifications_student_read ON employer_verifications
    FOR SELECT TO authenticated
    USING (trainee_id = auth.uid());

-- Employers can view verifications for their company
DROP POLICY IF EXISTS employer_verifications_employer_read ON employer_verifications;
CREATE POLICY employer_verifications_employer_read ON employer_verifications
    FOR SELECT TO authenticated
    USING (employer_id IN (SELECT id FROM employers WHERE profile_id = auth.uid()));

-- Anyone can submit a verification
DROP POLICY IF EXISTS employer_verifications_insert ON employer_verifications;
CREATE POLICY employer_verifications_insert ON employer_verifications
    FOR INSERT TO authenticated
    WITH CHECK (true);

-- ── job_postings ────────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS job_postings_super_admin ON job_postings;
CREATE POLICY job_postings_super_admin ON job_postings
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Employers can manage own postings
DROP POLICY IF EXISTS job_postings_employer_manage ON job_postings;
CREATE POLICY job_postings_employer_manage ON job_postings
    FOR ALL TO authenticated
    USING (employer_id IN (SELECT id FROM employers WHERE profile_id = auth.uid()))
    WITH CHECK (employer_id IN (SELECT id FROM employers WHERE profile_id = auth.uid()));

-- Public can view active job postings
DROP POLICY IF EXISTS job_postings_public_read ON job_postings;
CREATE POLICY job_postings_public_read ON job_postings
    FOR SELECT TO authenticated
    USING (is_active = true);

-- ── job_applications ──────────────────────────────────────────

-- Super admin: full access
DROP POLICY IF EXISTS job_applications_super_admin ON job_applications;
CREATE POLICY job_applications_super_admin ON job_applications
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Students can view own applications
DROP POLICY IF EXISTS job_applications_student_read ON job_applications;
CREATE POLICY job_applications_student_read ON job_applications
    FOR SELECT TO authenticated
    USING (student_id = auth.uid());

-- Students can apply to jobs
DROP POLICY IF EXISTS job_applications_student_insert ON job_applications;
CREATE POLICY job_applications_student_insert ON job_applications
    FOR INSERT TO authenticated
    WITH CHECK (student_id = auth.uid());

-- Employers can view applications for their jobs
DROP POLICY IF EXISTS job_applications_employer_read ON job_applications;
CREATE POLICY job_applications_employer_read ON job_applications
    FOR SELECT TO authenticated
    USING (job_id IN (
        SELECT id FROM job_postings
        WHERE employer_id IN (SELECT id FROM employers WHERE profile_id = auth.uid())
    ));

-- Employers can update application status
DROP POLICY IF EXISTS job_applications_employer_update ON job_applications;
CREATE POLICY job_applications_employer_update ON job_applications
    FOR UPDATE TO authenticated
    USING (job_id IN (
        SELECT id FROM job_postings
        WHERE employer_id IN (SELECT id FROM employers WHERE profile_id = auth.uid())
    ));

-- ── notifications ─────────────────────────────────────────────

-- Users can view their own notifications
DROP POLICY IF EXISTS notifications_user_read ON notifications;
CREATE POLICY notifications_user_read ON notifications
    FOR SELECT TO authenticated
    USING (user_id = auth.uid());

-- Users can mark their own notifications as read
DROP POLICY IF EXISTS notifications_user_update ON notifications;
CREATE POLICY notifications_user_update ON notifications
    FOR UPDATE TO authenticated
    USING (user_id = auth.uid());

-- System can insert notifications for any user
DROP POLICY IF EXISTS notifications_insert ON notifications;
CREATE POLICY notifications_insert ON notifications
    FOR INSERT TO authenticated
    WITH CHECK (true);

-- Super admin: full access
DROP POLICY IF EXISTS notifications_super_admin ON notifications;
CREATE POLICY notifications_super_admin ON notifications
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── exam_bookings ─────────────────────────────────────────────

-- Students can view their own exam bookings
DROP POLICY IF EXISTS exam_bookings_student_read ON exam_bookings;
CREATE POLICY exam_bookings_student_read ON exam_bookings
    FOR SELECT TO authenticated
    USING (student_id = auth.uid());

-- Students can create exam bookings
DROP POLICY IF EXISTS exam_bookings_student_insert ON exam_bookings;
CREATE POLICY exam_bookings_student_insert ON exam_bookings
    FOR INSERT TO authenticated
    WITH CHECK (student_id = auth.uid());

-- Dept admin can view exam bookings in their department
DROP POLICY IF EXISTS exam_bookings_dept_admin_read ON exam_bookings;
CREATE POLICY exam_bookings_dept_admin_read ON exam_bookings
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM user_profiles WHERE id = exam_bookings.student_id
    ));

-- Dept admin can approve/reject exam bookings in their department
DROP POLICY IF EXISTS exam_bookings_dept_admin_update ON exam_bookings;
CREATE POLICY exam_bookings_dept_admin_update ON exam_bookings
    FOR UPDATE TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM user_profiles WHERE id = exam_bookings.student_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS exam_bookings_super_admin ON exam_bookings;
CREATE POLICY exam_bookings_super_admin ON exam_bookings
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── marks ─────────────────────────────────────────────────────

-- Students can view their own marks
DROP POLICY IF EXISTS marks_student_read ON marks;
CREATE POLICY marks_student_read ON marks
    FOR SELECT TO authenticated
    USING (student_id = auth.uid());

-- Trainers can view marks for their assigned units
DROP POLICY IF EXISTS marks_trainer_read ON marks;
CREATE POLICY marks_trainer_read ON marks
    FOR SELECT TO authenticated
    USING (current_user_role() = 'trainer' AND trainer_id = auth.uid());

-- Trainers can insert marks for their assigned units and classes
DROP POLICY IF EXISTS marks_trainer_insert ON marks;
CREATE POLICY marks_trainer_insert ON marks
    FOR INSERT TO authenticated
    WITH CHECK (current_user_role() = 'trainer' AND trainer_id = auth.uid());

-- Trainers can update marks they entered
DROP POLICY IF EXISTS marks_trainer_update ON marks;
CREATE POLICY marks_trainer_update ON marks
    FOR UPDATE TO authenticated
    USING (current_user_role() = 'trainer' AND trainer_id = auth.uid());

-- Dept admin can view marks in their department
DROP POLICY IF EXISTS marks_dept_admin_read ON marks;
CREATE POLICY marks_dept_admin_read ON marks
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM units WHERE id = marks.unit_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS marks_super_admin ON marks;
CREATE POLICY marks_super_admin ON marks
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── trainer_documents ───────────────────────────────────────────────

-- Trainers can manage their own documents
DROP POLICY IF EXISTS trainer_documents_trainer_manage ON trainer_documents;
CREATE POLICY trainer_documents_trainer_manage ON trainer_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'trainer' AND trainer_id = auth.uid())
    WITH CHECK (current_user_role() = 'trainer' AND trainer_id = auth.uid());

-- Dept admin can view trainer documents in their department
DROP POLICY IF EXISTS trainer_documents_dept_admin_read ON trainer_documents;
CREATE POLICY trainer_documents_dept_admin_read ON trainer_documents
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM units WHERE id = trainer_documents.unit_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS trainer_documents_super_admin ON trainer_documents;
CREATE POLICY trainer_documents_super_admin ON trainer_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── trainee_documents ───────────────────────────────────────────────

-- Students can manage their own documents
DROP POLICY IF EXISTS trainee_documents_student_manage ON trainee_documents;
CREATE POLICY trainee_documents_student_manage ON trainee_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid())
    WITH CHECK (current_user_role() = 'student' AND student_id = auth.uid());

-- Trainers can view trainee documents for their assigned units
DROP POLICY IF EXISTS trainee_documents_trainer_read ON trainee_documents;
CREATE POLICY trainee_documents_trainer_read ON trainee_documents
    FOR SELECT TO authenticated
    USING (current_user_role() = 'trainer' AND unit_id IN (
        SELECT unit_id FROM trainer_units WHERE trainer_id = auth.uid()
    ));

-- Dept admin can view trainee documents in their department
DROP POLICY IF EXISTS trainee_documents_dept_admin_read ON trainee_documents;
CREATE POLICY trainee_documents_dept_admin_read ON trainee_documents
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM units WHERE id = trainee_documents.unit_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS trainee_documents_super_admin ON trainee_documents;
CREATE POLICY trainee_documents_super_admin ON trainee_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── companies ────────────────────────────────────────────────────────

-- Dept admin can manage companies in their department
DROP POLICY IF EXISTS companies_dept_admin_manage ON companies;
CREATE POLICY companies_dept_admin_manage ON companies
    FOR ALL TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = department_id)
    WITH CHECK (current_user_role() = 'dept_admin' AND current_user_dept() = department_id);

-- Super admin: full access
DROP POLICY IF EXISTS companies_super_admin ON companies;
CREATE POLICY companies_super_admin ON companies
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- All authenticated users can view companies
DROP POLICY IF EXISTS companies_read ON companies;
CREATE POLICY companies_read ON companies
    FOR SELECT TO authenticated
    USING (true);

-- ── mentors ───────────────────────────────────────────────────────────

-- Industry mentors can view their own records
DROP POLICY IF EXISTS mentors_read ON mentors;
CREATE POLICY mentors_read ON mentors
    FOR SELECT TO authenticated
    USING (current_user_role() = 'industry_mentor' AND user_id = auth.uid());

-- Dept admin can manage mentors in their department
DROP POLICY IF EXISTS mentors_dept_admin_manage ON mentors;
CREATE POLICY mentors_dept_admin_manage ON mentors
    FOR ALL TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM companies WHERE id = mentors.company_id
    ))
    WITH CHECK (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM companies WHERE id = mentors.company_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS mentors_super_admin ON mentors;
CREATE POLICY mentors_super_admin ON mentors
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── industrial_attachments ─────────────────────────────────────────────

-- Students can view their own attachments
DROP POLICY IF EXISTS industrial_attachments_student_read ON industrial_attachments;
CREATE POLICY industrial_attachments_student_read ON industrial_attachments
    FOR SELECT TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid());

-- Industry mentors can view attachments for their company
DROP POLICY IF EXISTS industrial_attachments_mentor_read ON industrial_attachments;
CREATE POLICY industrial_attachments_mentor_read ON industrial_attachments
    FOR SELECT TO authenticated
    USING (current_user_role() = 'industry_mentor' AND company_id IN (
        SELECT company_id FROM mentors WHERE user_id = auth.uid()
    ));

-- Dept admin can manage attachments in their department
DROP POLICY IF EXISTS industrial_attachments_dept_admin_manage ON industrial_attachments;
CREATE POLICY industrial_attachments_dept_admin_manage ON industrial_attachments
    FOR ALL TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM companies WHERE id = industrial_attachments.company_id
    ))
    WITH CHECK (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM companies WHERE id = industrial_attachments.company_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS industrial_attachments_super_admin ON industrial_attachments;
CREATE POLICY industrial_attachments_super_admin ON industrial_attachments
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── location_logs ─────────────────────────────────────────────────────

-- Students can create their own location logs
DROP POLICY IF EXISTS location_logs_student_create ON location_logs;
CREATE POLICY location_logs_student_create ON location_logs
    FOR INSERT TO authenticated
    WITH CHECK (current_user_role() = 'student' AND student_id = auth.uid());

-- Students can view their own location logs
DROP POLICY IF EXISTS location_logs_student_read ON location_logs;
CREATE POLICY location_logs_student_read ON location_logs
    FOR SELECT TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid());

-- Industry mentors can view location logs for their company
DROP POLICY IF EXISTS location_logs_mentor_read ON location_logs;
CREATE POLICY location_logs_mentor_read ON location_logs
    FOR SELECT TO authenticated
    USING (current_user_role() = 'industry_mentor' AND attachment_id IN (
        SELECT id FROM industrial_attachments WHERE company_id IN (
            SELECT company_id FROM mentors WHERE user_id = auth.uid()
        )
    ));

-- Dept admin can view location logs in their department
DROP POLICY IF EXISTS location_logs_dept_admin_read ON location_logs;
CREATE POLICY location_logs_dept_admin_read ON location_logs
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM companies WHERE id = (
            SELECT company_id FROM industrial_attachments WHERE id = location_logs.attachment_id
        )
    ));

-- Super admin: full access
DROP POLICY IF EXISTS location_logs_super_admin ON location_logs;
CREATE POLICY location_logs_super_admin ON location_logs
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── digital_logbook ───────────────────────────────────────────────────

-- Students can manage their own logbook entries
DROP POLICY IF EXISTS digital_logbook_student_manage ON digital_logbook;
CREATE POLICY digital_logbook_student_manage ON digital_logbook
    FOR ALL TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid())
    WITH CHECK (current_user_role() = 'student' AND student_id = auth.uid());

-- Industry mentors can view and approve logbook entries for their company
DROP POLICY IF EXISTS digital_logbook_mentor_manage ON digital_logbook;
CREATE POLICY digital_logbook_mentor_manage ON digital_logbook
    FOR SELECT TO authenticated
    USING (current_user_role() = 'industry_mentor' AND attachment_id IN (
        SELECT id FROM industrial_attachments WHERE company_id IN (
            SELECT company_id FROM mentors WHERE user_id = auth.uid()
        )
    ));

DROP POLICY IF EXISTS digital_logbook_mentor_approve ON digital_logbook;
CREATE POLICY digital_logbook_mentor_approve ON digital_logbook
    FOR UPDATE TO authenticated
    USING (current_user_role() = 'industry_mentor' AND attachment_id IN (
        SELECT id FROM industrial_attachments WHERE company_id IN (
            SELECT company_id FROM mentors WHERE user_id = auth.uid()
        )
    ))
    WITH CHECK (current_user_role() = 'industry_mentor' AND mentor_approved_by = auth.uid());

-- Dept admin can view logbook entries in their department
DROP POLICY IF EXISTS digital_logbook_dept_admin_read ON digital_logbook;
CREATE POLICY digital_logbook_dept_admin_read ON digital_logbook
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM companies WHERE id = (
            SELECT company_id FROM industrial_attachments WHERE id = digital_logbook.attachment_id
        )
    ));

-- Super admin: full access
DROP POLICY IF EXISTS digital_logbook_super_admin ON digital_logbook;
CREATE POLICY digital_logbook_super_admin ON digital_logbook
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ── competency_tracking ───────────────────────────────────────────────

-- Students can view their own competency tracking
DROP POLICY IF EXISTS competency_tracking_student_read ON competency_tracking;
CREATE POLICY competency_tracking_student_read ON competency_tracking
    FOR SELECT TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid());

-- Industry mentors can assess competencies for their company
DROP POLICY IF EXISTS competency_tracking_mentor_assess ON competency_tracking;
CREATE POLICY competency_tracking_mentor_assess ON competency_tracking
    FOR ALL TO authenticated
    USING (current_user_role() = 'industry_mentor' AND attachment_id IN (
        SELECT id FROM industrial_attachments WHERE company_id IN (
            SELECT company_id FROM mentors WHERE user_id = auth.uid()
        )
    ))
    WITH CHECK (current_user_role() = 'industry_mentor' AND assessed_by = auth.uid());

-- Internal verifiers can verify competencies
DROP POLICY IF EXISTS competency_tracking_verifier_verify ON competency_tracking;
CREATE POLICY competency_tracking_verifier_verify ON competency_tracking
    FOR UPDATE TO authenticated
    USING (current_user_role() = 'internal_verifier')
    WITH CHECK (current_user_role() = 'internal_verifier' AND verified_by = auth.uid());

-- Dept admin can view competency tracking in their department
DROP POLICY IF EXISTS competency_tracking_dept_admin_read ON competency_tracking;
CREATE POLICY competency_tracking_dept_admin_read ON competency_tracking
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM units WHERE id = competency_tracking.unit_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS competency_tracking_super_admin ON competency_tracking;
CREATE POLICY competency_tracking_super_admin ON competency_tracking
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ────────────────────────────────────────────────────────────
-- 17. SEED DATA (Departments and Courses)
-- ────────────────────────────────────────────────────────────
-- NOTE: Departments and courses should be added by Super Admin through the admin interface
-- No pre-seeded data - Super Admin manages all departments and courses

-- ────────────────────────────────────────────────────────────
-- 18. TVET ONLINE TRAINEE CLEARANCE SYSTEM
-- ────────────────────────────────────────────────────────────

-- Clearance departments table
CREATE TABLE IF NOT EXISTS clearance_departments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,
    code VARCHAR(20) NOT NULL UNIQUE,
    clearance_type VARCHAR(20) NOT NULL CHECK (clearance_type IN ('department', 'institutional', 'central')),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Clearance stages table (defines workflow steps)
CREATE TABLE IF NOT EXISTS clearance_stages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clearance_department_id UUID NOT NULL REFERENCES clearance_departments(id) ON DELETE CASCADE,
    stage_order INTEGER NOT NULL,
    stage_name VARCHAR(100) NOT NULL,
    approver_role VARCHAR(50) NOT NULL,
    is_optional BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(clearance_department_id, stage_order)
);

-- Clearance requests table (main clearance request per student)
CREATE TABLE IF NOT EXISTS clearance_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'rejected')),
    initiated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    certificate_issued BOOLEAN DEFAULT false,
    certificate_issued_at TIMESTAMPTZ,
    created_by UUID REFERENCES user_profiles(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Clearance approvals table (individual approval records)
CREATE TABLE IF NOT EXISTS clearance_approvals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clearance_request_id UUID NOT NULL REFERENCES clearance_requests(id) ON DELETE CASCADE,
    clearance_stage_id UUID NOT NULL REFERENCES clearance_stages(id) ON DELETE CASCADE,
    approver_id UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'skipped')),
    comments TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for clearance tables
DROP INDEX IF EXISTS idx_clearance_requests_student;
CREATE INDEX idx_clearance_requests_student ON clearance_requests(student_id);
DROP INDEX IF EXISTS idx_clearance_requests_status;
CREATE INDEX idx_clearance_requests_status ON clearance_requests(status);
DROP INDEX IF EXISTS idx_clearance_requests_department;
CREATE INDEX idx_clearance_requests_department ON clearance_requests(department_id);
DROP INDEX IF EXISTS idx_clearance_approvals_request;
CREATE INDEX idx_clearance_approvals_request ON clearance_approvals(clearance_request_id);
DROP INDEX IF EXISTS idx_clearance_approvals_stage;
CREATE INDEX idx_clearance_approvals_stage ON clearance_approvals(clearance_stage_id);
DROP INDEX IF EXISTS idx_clearance_approvals_approver;
CREATE INDEX idx_clearance_approvals_approver ON clearance_approvals(approver_id);

-- Trigger for updated_at on clearance tables
DROP TRIGGER IF EXISTS update_clearance_departments_updated_at ON clearance_departments;
CREATE TRIGGER update_clearance_departments_updated_at BEFORE UPDATE ON clearance_departments
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_clearance_stages_updated_at ON clearance_stages;
CREATE TRIGGER update_clearance_stages_updated_at BEFORE UPDATE ON clearance_stages
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_clearance_requests_updated_at ON clearance_requests;
CREATE TRIGGER update_clearance_requests_updated_at BEFORE UPDATE ON clearance_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_clearance_approvals_updated_at ON clearance_approvals;
CREATE TRIGGER update_clearance_approvals_updated_at BEFORE UPDATE ON clearance_approvals
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- RLS Policies for clearance tables
ALTER TABLE clearance_departments ENABLE ROW LEVEL SECURITY;
ALTER TABLE clearance_stages ENABLE ROW LEVEL SECURITY;
ALTER TABLE clearance_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE clearance_approvals ENABLE ROW LEVEL SECURITY;

-- Clearance departments: Super admin full access, others read-only
DROP POLICY IF EXISTS clearance_departments_super_admin ON clearance_departments;
CREATE POLICY clearance_departments_super_admin ON clearance_departments
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

DROP POLICY IF EXISTS clearance_departments_read ON clearance_departments;
CREATE POLICY clearance_departments_read ON clearance_departments
    FOR SELECT TO authenticated
    USING (current_user_active());

-- Clearance stages: Super admin full access, others read-only
DROP POLICY IF EXISTS clearance_stages_super_admin ON clearance_stages;
CREATE POLICY clearance_stages_super_admin ON clearance_stages
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

DROP POLICY IF EXISTS clearance_stages_read ON clearance_stages;
CREATE POLICY clearance_stages_read ON clearance_stages
    FOR SELECT TO authenticated
    USING (current_user_active());

-- Clearance requests: Students can see their own, approvers can see pending approvals
DROP POLICY IF EXISTS clearance_requests_student_read ON clearance_requests;
CREATE POLICY clearance_requests_student_read ON clearance_requests
    FOR SELECT TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid());

DROP POLICY IF EXISTS clearance_requests_approver_read ON clearance_requests;
CREATE POLICY clearance_requests_approver_read ON clearance_requests
    FOR SELECT TO authenticated
    USING (
        current_user_active() AND EXISTS (
            SELECT 1 FROM clearance_approvals ca
            JOIN clearance_stages cs ON ca.clearance_stage_id = cs.id
            WHERE ca.clearance_request_id = clearance_requests.id
            AND cs.approver_role = current_user_role()
            AND ca.status = 'pending'
        )
    );

DROP POLICY IF EXISTS clearance_requests_super_admin ON clearance_requests;
CREATE POLICY clearance_requests_super_admin ON clearance_requests
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Clearance approvals: Approvers can update their assigned approvals
DROP POLICY IF EXISTS clearance_approvals_student_read ON clearance_approvals;
CREATE POLICY clearance_approvals_student_read ON clearance_approvals
    FOR SELECT TO authenticated
    USING (
        current_user_role() = 'student' AND EXISTS (
            SELECT 1 FROM clearance_requests cr WHERE cr.id = clearance_approvals.clearance_request_id AND cr.student_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS clearance_approvals_approver_update ON clearance_approvals;
CREATE POLICY clearance_approvals_approver_update ON clearance_approvals
    FOR UPDATE TO authenticated
    USING (
        current_user_active() AND EXISTS (
            SELECT 1 FROM clearance_stages cs
            WHERE cs.id = clearance_approvals.clearance_stage_id
            AND cs.approver_role = current_user_role()
        )
    );

DROP POLICY IF EXISTS clearance_approvals_super_admin ON clearance_approvals;
CREATE POLICY clearance_approvals_super_admin ON clearance_approvals
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- Seed clearance departments
INSERT INTO clearance_departments (name, code, clearance_type) VALUES
    ('Department Clearance', 'DEPT', 'department'),
    ('Sports Department', 'SPORTS', 'institutional'),
    ('Environment Department', 'ENV', 'institutional'),
    ('Dean of Students', 'DOS', 'institutional'),
    ('Library', 'LIB', 'institutional'),
    ('Finance Office', 'FINANCE', 'central'),
    ('Registrar Office', 'REGISTRAR', 'central'),
    ('Deputy Principal Academics', 'DPA', 'central')
ON CONFLICT (code) DO NOTHING;

-- Seed clearance stages for department clearance (full workflow)
INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Trainer Approval', 'trainer'
FROM clearance_departments cd WHERE cd.code = 'DEPT'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 2, 'Workshop Technician Approval', 'trainer'
FROM clearance_departments cd WHERE cd.code = 'DEPT'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 3, 'Trainer Approval', 'trainer'
FROM clearance_departments cd WHERE cd.code = 'DEPT'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 4, 'Department HOD Approval', 'dept_admin'
FROM clearance_departments cd WHERE cd.code = 'DEPT'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

-- Seed clearance stages for institutional departments (HOD-only)
INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Sports HOD Approval', 'sports_hod'
FROM clearance_departments cd WHERE cd.code = 'SPORTS'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Environment HOD Approval', 'environment_hod'
FROM clearance_departments cd WHERE cd.code = 'ENV'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Dean of Students Approval', 'dean_students'
FROM clearance_departments cd WHERE cd.code = 'DOS'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Library HOD Approval', 'library_hod'
FROM clearance_departments cd WHERE cd.code = 'LIB'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

-- Seed clearance stages for central authority (sequential)
INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Finance Clearance', 'finance_officer'
FROM clearance_departments cd WHERE cd.code = 'FINANCE'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Registrar Clearance', 'registrar'
FROM clearance_departments cd WHERE cd.code = 'REGISTRAR'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO clearance_stages (clearance_department_id, stage_order, stage_name, approver_role)
SELECT cd.id, 1, 'Deputy Principal Academics Clearance', 'deputy_principal'
FROM clearance_departments cd WHERE cd.code = 'DPA'
ON CONFLICT (clearance_department_id, stage_order) DO NOTHING;

INSERT INTO courses (name, code, department_id)
SELECT 'Certificate in Welding', 'CW', id
FROM departments WHERE code = 'WF'
ON CONFLICT (code, department_id) DO NOTHING;

INSERT INTO courses (name, code, department_id)
SELECT 'Certificate in Plumbing', 'CP', id
FROM departments WHERE code = 'PL'
ON CONFLICT (code, department_id) DO NOTHING;

INSERT INTO courses (name, code, department_id)
SELECT 'Certificate in Carpentry', 'CC', id
FROM departments WHERE code = 'CA'
ON CONFLICT (code, department_id) DO NOTHING;

-- ────────────────────────────────────────────────────────────
-- 15. ADMISSION DOCUMENTS AND REQUESTS
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS admission_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
    department_id UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    reviewed_by UUID REFERENCES user_profiles(id),
    comments TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admission_requests_student ON admission_requests(student_id);
CREATE INDEX IF NOT EXISTS idx_admission_requests_course ON admission_requests(course_id);
CREATE INDEX IF NOT EXISTS idx_admission_requests_status ON admission_requests(status);

CREATE TABLE IF NOT EXISTS admission_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    admission_request_id UUID NOT NULL REFERENCES admission_requests(id) ON DELETE CASCADE,
    document_type VARCHAR(50) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_size BIGINT,
    uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    verified BOOLEAN DEFAULT FALSE,
    verified_at TIMESTAMP WITH TIME ZONE,
    verified_by UUID REFERENCES user_profiles(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_admission_documents_request ON admission_documents(admission_request_id);
CREATE INDEX IF NOT EXISTS idx_admission_documents_type ON admission_documents(document_type);

-- RLS for admission_requests
ALTER TABLE admission_requests ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS admission_requests_student_read ON admission_requests;
CREATE POLICY admission_requests_student_read ON admission_requests
    FOR SELECT TO authenticated
    USING (student_id = auth.uid());

DROP POLICY IF EXISTS admission_requests_hod_read ON admission_requests;
CREATE POLICY admission_requests_hod_read ON admission_requests
    FOR SELECT TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = department_id);

DROP POLICY IF EXISTS admission_requests_student_insert ON admission_requests;
CREATE POLICY admission_requests_student_insert ON admission_requests
    FOR INSERT TO authenticated
    WITH CHECK (student_id = auth.uid());

DROP POLICY IF EXISTS admission_requests_hod_update ON admission_requests;
CREATE POLICY admission_requests_hod_update ON admission_requests
    FOR UPDATE TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = department_id);

DROP POLICY IF EXISTS admission_requests_super_admin ON admission_requests;
CREATE POLICY admission_requests_super_admin ON admission_requests
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active());

-- RLS for admission_documents
ALTER TABLE admission_documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS admission_documents_student_read ON admission_documents;
CREATE POLICY admission_documents_student_read ON admission_documents
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM admission_requests WHERE id = admission_documents.admission_request_id AND student_id = auth.uid()
    ));

DROP POLICY IF EXISTS admission_documents_hod_read ON admission_documents;
CREATE POLICY admission_documents_hod_read ON admission_documents
    FOR SELECT TO authenticated
    USING (EXISTS (
        SELECT 1 FROM admission_requests ar
        WHERE ar.id = admission_documents.admission_request_id
        AND current_user_role() = 'dept_admin'
        AND current_user_dept() = ar.department_id
    ));

DROP POLICY IF EXISTS admission_documents_student_insert ON admission_documents;
CREATE POLICY admission_documents_student_insert ON admission_documents
    FOR INSERT TO authenticated
    WITH CHECK (EXISTS (
        SELECT 1 FROM admission_requests WHERE id = admission_documents.admission_request_id AND student_id = auth.uid()
    ));

DROP POLICY IF EXISTS admission_documents_hod_update ON admission_documents;
CREATE POLICY admission_documents_hod_update ON admission_documents
    FOR UPDATE TO authenticated
    USING (EXISTS (
        SELECT 1 FROM admission_requests ar
        WHERE ar.id = admission_documents.admission_request_id
        AND current_user_role() = 'dept_admin'
        AND current_user_dept() = ar.department_id
    ));

DROP POLICY IF EXISTS admission_documents_super_admin ON admission_documents;
CREATE POLICY admission_documents_super_admin ON admission_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active());

-- Trigger for updated_at on admission_requests
DROP TRIGGER IF EXISTS update_admission_requests_updated_at ON admission_requests;
CREATE TRIGGER update_admission_requests_updated_at
    BEFORE UPDATE ON admission_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for updated_at on admission_documents
DROP TRIGGER IF EXISTS update_admission_documents_updated_at ON admission_documents;
CREATE TRIGGER update_admission_documents_updated_at
    BEFORE UPDATE ON admission_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ────────────────────────────────────────────────────────────
-- 15a. COURSE APPLICATIONS (public pre-registration)
-- ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS course_applications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    full_name       TEXT NOT NULL,
    email           TEXT NOT NULL,
    phone           TEXT,
    department_id   UUID REFERENCES departments(id),
    course_name     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    document_paths  TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reviewed_at     TIMESTAMPTZ,
    reviewed_by     UUID REFERENCES user_profiles(id),
    review_notes    TEXT
);

ALTER TABLE course_applications ENABLE ROW LEVEL SECURITY;

-- Public can insert (no auth required)
DROP POLICY IF EXISTS course_applications_insert ON course_applications;
CREATE POLICY course_applications_insert ON course_applications
    FOR INSERT TO anon, authenticated
    WITH CHECK (true);

-- Authenticated staff can view
DROP POLICY IF EXISTS course_applications_select ON course_applications;
CREATE POLICY course_applications_select ON course_applications
    FOR SELECT TO authenticated
    USING (true);

-- Dept admin / super admin can update (review)
DROP POLICY IF EXISTS course_applications_update ON course_applications;
CREATE POLICY course_applications_update ON course_applications
    FOR UPDATE TO authenticated
    USING (current_user_role() IN ('dept_admin', 'super_admin') AND current_user_active());

-- ────────────────────────────────────────────────────────────
-- 16. STORAGE BUCKETS (create manually in Supabase Dashboard)
-- ────────────────────────────────────────────────────────────
-- Create these buckets in Supabase Storage and set to PUBLIC:
-- - assessment-scripts (for PDF uploads)
-- - assessment-evidence (for photos/videos)
-- - application-documents (for course application file uploads)
