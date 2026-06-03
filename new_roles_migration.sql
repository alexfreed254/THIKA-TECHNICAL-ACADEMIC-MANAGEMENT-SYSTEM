-- ─────────────────────────────────────────────────────────────────
--  Migration: Add 4 new user roles to user_profiles CHECK constraint
--  Run once in Supabase SQL Editor
-- ─────────────────────────────────────────────────────────────────

-- Step 1: Drop the existing role CHECK constraint
ALTER TABLE user_profiles
  DROP CONSTRAINT IF EXISTS user_profiles_role_check;

-- Step 2: Re-add it with the 4 new roles included
ALTER TABLE user_profiles
  ADD CONSTRAINT user_profiles_role_check CHECK (role IN (
    'super_admin',
    'dept_admin',
    'trainer',
    'student',
    'employer',
    'examination_officer',
    'industry_mentor',
    'internal_verifier',
    'sports_hod',
    'environment_hod',
    'dean_students',
    'library_hod',
    'finance_officer',
    'registrar',
    'deputy_principal',
    'quality_assurance_officer',
    -- New roles added 2026-06-03
    'workshop_technician',
    'liaison_officer',
    'cdacc_verifier',
    'industry_supervisor'
  ));

-- Step 3: Ensure role column is wide enough (TEXT is already fine;
--         if still VARCHAR(20) this widens it to accommodate existing long roles)
ALTER TABLE user_profiles
  ALTER COLUMN role TYPE VARCHAR(50);
