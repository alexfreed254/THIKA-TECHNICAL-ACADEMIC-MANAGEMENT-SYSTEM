-- Optional safety net: allow category-based approvals without a stage FK.
-- Prefer keeping a real clearance_stage_id (app resolves one); this only
-- helps if stages are missing. Safe to run multiple times.

ALTER TABLE clearance_approvals
  ALTER COLUMN clearance_stage_id DROP NOT NULL;
