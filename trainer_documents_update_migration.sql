-- ============================================================
-- TRAINER DOCUMENTS - ADD NEW DOCUMENT TYPES
-- Migration to add curriculum and planning documents
-- ============================================================

-- Drop the existing CHECK constraint
ALTER TABLE trainer_documents 
DROP CONSTRAINT IF EXISTS trainer_documents_document_type_check;

-- Add the new CHECK constraint with additional document types
ALTER TABLE trainer_documents 
ADD CONSTRAINT trainer_documents_document_type_check 
CHECK (document_type IN (
    -- NEW: Curriculum & Planning Documents (added at the top)
    'occupational_standards',
    'modularized_curricula',
    'course_outline',
    'modularized_training_schedules',
    'learning_plans',
    'session_plans',
    'training_timetables',
    -- Existing: Assessment Planning
    'assessment_plan',
    'competency_standard',
    'assessment_tools',
    'marking_guide',
    'written_oral_mark_sheets',
    'observation_checklist',
    'product_checklist',
    -- Existing: Assessment Records
    'assessment_records',
    'evidence_register',
    'feedback_forms',
    -- Existing: Verification & Moderation
    'internal_verification_report',
    'moderation_report',
    -- Existing: Industrial Attachment
    'industrial_attachment_plan',
    'mentoring_tools',
    'industrial_attachment_report',
    -- Existing: Administrative Records
    'trainee_attendance_records',
    'communication_records',
    'assessment_schedule'
));

-- Add comment to document the new types
COMMENT ON COLUMN trainer_documents.document_type IS 
'Document type classification. New types added 2026-06: occupational_standards, modularized_curricula, course_outline, modularized_training_schedules, learning_plans, session_plans, training_timetables';

-- Verification query
SELECT 
    'trainer_documents table updated' AS status,
    COUNT(*) AS total_documents,
    COUNT(CASE WHEN document_type IN (
        'occupational_standards',
        'modularized_curricula',
        'course_outline',
        'modularized_training_schedules',
        'learning_plans',
        'session_plans',
        'training_timetables'
    ) THEN 1 END) AS new_type_documents
FROM trainer_documents;
