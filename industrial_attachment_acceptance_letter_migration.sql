ALTER TABLE industrial_attachments
  ADD COLUMN IF NOT EXISTS attachment_term TEXT,
  ADD COLUMN IF NOT EXISTS attachment_year INTEGER,
  ADD COLUMN IF NOT EXISTS trainee_role TEXT,
  ADD COLUMN IF NOT EXISTS acceptance_letter_url TEXT,
  ADD COLUMN IF NOT EXISTS acceptance_letter_name TEXT,
  ADD COLUMN IF NOT EXISTS acceptance_letter_path TEXT,
  ADD COLUMN IF NOT EXISTS acceptance_letter_status TEXT DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS dept_review_comments TEXT,
  ADD COLUMN IF NOT EXISTS dept_reviewed_by UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS dept_reviewed_at TIMESTAMPTZ;

ALTER TABLE industrial_attachments
  DROP CONSTRAINT IF EXISTS industrial_attachments_status_check;

ALTER TABLE industrial_attachments
  ADD CONSTRAINT industrial_attachments_status_check
  CHECK (status IN ('pending', 'approved', 'active', 'completed', 'terminated', 'rejected'));

ALTER TABLE industrial_attachments
  DROP CONSTRAINT IF EXISTS industrial_attachments_acceptance_letter_status_check;

ALTER TABLE industrial_attachments
  ADD CONSTRAINT industrial_attachments_acceptance_letter_status_check
  CHECK (acceptance_letter_status IN ('pending', 'approved', 'rejected'));

CREATE INDEX IF NOT EXISTS idx_industrial_attachments_letter_status
  ON industrial_attachments(acceptance_letter_status);
