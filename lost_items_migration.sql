-- ============================================================
-- TTTI Clearance System — Lost Items Migration
-- Run once in Supabase Dashboard → SQL Editor
-- Safe to run multiple times (uses IF NOT EXISTS).
-- ============================================================

CREATE TABLE IF NOT EXISTS clearance_lost_items (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    clearance_approval_id UUID NOT NULL REFERENCES clearance_approvals(id) ON DELETE CASCADE,
    item_name             TEXT NOT NULL,
    quantity              INTEGER NOT NULL DEFAULT 1,
    notes                 TEXT,
    added_by              UUID REFERENCES user_profiles(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_lost_items_approval
    ON clearance_lost_items(clearance_approval_id);

-- RLS: service client (used by Flask) bypasses RLS; students can read their own
ALTER TABLE clearance_lost_items ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS lost_items_all_service ON clearance_lost_items;
CREATE POLICY lost_items_all_service ON clearance_lost_items
    USING (true) WITH CHECK (true);
