-- ═══════════════════════════════════════════════════════════════════════════
-- MIGRATION: Add student_personal_documents table
-- Date: May 29, 2026
-- Purpose: Fix "My Documents" upload feature for students
-- ═══════════════════════════════════════════════════════════════════════════

-- Create the student_personal_documents table
CREATE TABLE IF NOT EXISTS student_personal_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    student_id UUID NOT NULL REFERENCES user_profiles(id) ON DELETE CASCADE,
    document_type TEXT NOT NULL,
    document_name TEXT NOT NULL,
    file_url TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    verified_by UUID REFERENCES user_profiles(id),
    verified_at TIMESTAMPTZ,
    rejection_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id, document_type)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_student_personal_documents_student ON student_personal_documents(student_id);
CREATE INDEX IF NOT EXISTS idx_student_personal_documents_type ON student_personal_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_student_personal_documents_status ON student_personal_documents(status);

-- Create trigger for updated_at
DROP TRIGGER IF EXISTS trg_student_personal_documents_updated_at ON student_personal_documents;
CREATE TRIGGER trg_student_personal_documents_updated_at
    BEFORE UPDATE ON student_personal_documents
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Enable RLS
ALTER TABLE student_personal_documents ENABLE ROW LEVEL SECURITY;

-- RLS Policies

-- Students can manage their own personal documents
DROP POLICY IF EXISTS student_personal_documents_student_manage ON student_personal_documents;
CREATE POLICY student_personal_documents_student_manage ON student_personal_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'student' AND student_id = auth.uid())
    WITH CHECK (current_user_role() = 'student' AND student_id = auth.uid());

-- Dept admin can view and verify student documents in their department
DROP POLICY IF EXISTS student_personal_documents_dept_admin ON student_personal_documents;
CREATE POLICY student_personal_documents_dept_admin ON student_personal_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM user_profiles WHERE id = student_personal_documents.student_id
    ))
    WITH CHECK (current_user_role() = 'dept_admin' AND current_user_dept() = (
        SELECT department_id FROM user_profiles WHERE id = student_personal_documents.student_id
    ));

-- Super admin: full access
DROP POLICY IF EXISTS student_personal_documents_super_admin ON student_personal_documents;
CREATE POLICY student_personal_documents_super_admin ON student_personal_documents
    FOR ALL TO authenticated
    USING (current_user_role() = 'super_admin' AND current_user_active())
    WITH CHECK (current_user_role() = 'super_admin' AND current_user_active());

-- ═══════════════════════════════════════════════════════════════════════════
-- END OF MIGRATION
-- ═══════════════════════════════════════════════════════════════════════════

-- Verification Query
-- Run this to verify the table was created successfully:
-- SELECT * FROM student_personal_documents LIMIT 1;
