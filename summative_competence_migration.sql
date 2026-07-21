-- ============================================================
-- TTTI Summative Competence Assessment (TVET CDACC grading)
-- Competence per unit per trainee for graduation list generation.
-- Levels: mastery | proficient | competent | not_yet_competent | crnm
--   M    80-100%  Mastery
--   P    65-79%   Proficient
--   C    50-64%   Competent
--   NYC  0-49%    Not Yet Competent
--   CRNM          Course Requirement Not Met
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
                        'mastery',
                        'proficient',
                        'competent',
                        'not_yet_competent',
                        'crnm'
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

-- Migrate legacy values ('exempt' → NYC, 'fail' → CRNM) and refresh CHECK
-- constraint to the TVET CDACC scale (adds 'mastery' and 'crnm').
DO $$
BEGIN
  ALTER TABLE summative_competences DROP CONSTRAINT IF EXISTS summative_competences_competence_check;

  UPDATE summative_competences
     SET competence = 'not_yet_competent'
   WHERE competence = 'exempt';

  UPDATE summative_competences
     SET competence = 'crnm'
   WHERE competence = 'fail';

  ALTER TABLE summative_competences
    ADD CONSTRAINT summative_competences_competence_check
    CHECK (competence IN (
      'mastery',
      'proficient',
      'competent',
      'not_yet_competent',
      'crnm'
    ));
EXCEPTION WHEN others THEN
  RAISE NOTICE 'summative competence check update skipped: %', SQLERRM;
END $$;

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
  'Summative competence per trainee per unit: proficient / competent / not yet competent / fail';

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
