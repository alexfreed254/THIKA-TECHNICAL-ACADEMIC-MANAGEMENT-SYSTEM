-- ============================================================
-- BIOMETRIC ATTENDANCE SYSTEM - Database Migration
-- Adds fingerprint_id field to user_profiles table
-- ============================================================

-- Add fingerprint_id column to user_profiles
ALTER TABLE user_profiles 
ADD COLUMN IF NOT EXISTS fingerprint_id TEXT UNIQUE;

-- Create index for fast lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_fingerprint 
ON user_profiles(fingerprint_id) WHERE fingerprint_id IS NOT NULL;

-- Add comment
COMMENT ON COLUMN user_profiles.fingerprint_id IS 
'Unique fingerprint sensor ID for biometric attendance. Used to identify students during fingerprint scans.';

-- Verification query
SELECT 
    'fingerprint_id column added' AS status,
    COUNT(*) AS total_users,
    COUNT(fingerprint_id) AS users_with_fingerprint
FROM user_profiles;

-- Sample query to check students without fingerprint IDs
SELECT 
    id,
    full_name,
    admission_no,
    role,
    fingerprint_id
FROM user_profiles
WHERE role = 'student' 
AND fingerprint_id IS NULL
ORDER BY full_name
LIMIT 10;
