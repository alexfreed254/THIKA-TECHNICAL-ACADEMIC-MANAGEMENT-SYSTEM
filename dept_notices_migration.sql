-- ─────────────────────────────────────────────────────────────────
--  Migration: dept_notices table
--  Run once in Supabase SQL Editor or via psql
-- ─────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS dept_notices (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    department_id  UUID NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    sent_by        UUID NOT NULL REFERENCES user_profiles(id) ON DELETE SET NULL,
    title          TEXT NOT NULL,
    message        TEXT NOT NULL,
    notice_type    TEXT NOT NULL DEFAULT 'info'
                       CHECK (notice_type IN ('info','success','warning','error')),
    class_id       UUID REFERENCES classes(id) ON DELETE SET NULL,
    sent_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index for fast retrieval by department
CREATE INDEX IF NOT EXISTS idx_dept_notices_dept
    ON dept_notices (department_id, sent_at DESC);

-- Optional: Row Level Security (allow authenticated service role only)
ALTER TABLE dept_notices ENABLE ROW LEVEL SECURITY;

-- Policy: service-role bypass (used by Flask backend via service key)
CREATE POLICY "service_role_all" ON dept_notices
    FOR ALL TO service_role USING (true) WITH CHECK (true);
