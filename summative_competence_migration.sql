-- ============================================================
-- TTTI Summative Competence Assessment
-- Competence per unit per trainee for graduation list generation.
-- Run against Supabase PostgreSQL (safe to re-run).
-- ============================================================

CREATE TABLE IF NOT EXISTS summative_competences (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id    UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    unit_id       UUID NOT NULL REFERENCES units(id) ON DELETE CASCADE,
    class_id      UUID NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    department_id UUID REFERENCES departments(id) ON DELETE SET NULL,
    competence    TEXT NOT NULL
                    CHECK (competence IN (
                        'proficient',
                        'competent',
                        'not_yet_competent',
                        'exempt'
                    )),
    assessed_by   UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    assessment_date DATE DEFAULT CURRENT_DATE,
    term          INTEGER CHECK (term IS NULL OR term IN (1, 2, 3)),
    year          INTEGER,
    remarks       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (student_id, unit_id, class_id)
);

DROP TRIGGER IF EXISTS trg_summative_competences_updated_at ON summative_competences;
CREATE TRIGGER trg_summative_competences_updated_at
    BEFORE UPDATE ON summative_competences
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_summative_class
    ON summative_competences (class_id);
CREATE INDEX IF NOT EXISTS idx_summative_student
    ON summative_competences (student_id);
CREATE INDEX IF NOT EXISTS idx_summative_unit
    ON summative_competences (unit_id);
CREATE INDEX IF NOT EXISTS idx_summative_competence
    ON summative_competences (competence);

COMMENT ON TABLE summative_competences IS
  'Summative competence outcome per trainee per unit (CDACC: proficient / competent / not yet competent)';

-- Allow clearance_requests.status = 'returned' (used by return-for-correction)
DO $$
BEGIN
  ALTER TABLE clearance_requests DROP CONSTRAINT IF EXISTS clearance_requests_status_check;
  ALTER TABLE clearance_requests
    ADD CONSTRAINT clearance_requests_status_check
    CHECK (status IN ('pending', 'in_progress', 'completed', 'rejected', 'returned'));
EXCEPTION WHEN others THEN
  RAISE NOTICE 'clearance_requests status check update skipped: %', SQLERRM;
END $$;
