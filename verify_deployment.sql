-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFICATION SCRIPT: Check "My Documents" Feature Deployment
-- Run this after migration to verify everything is set up correctly
-- ═══════════════════════════════════════════════════════════════════════════

\echo '──────────────────────────────────────────────────────────────────────'
\echo '1. Checking if student_personal_documents table exists...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    CASE 
        WHEN EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'student_personal_documents'
        ) 
        THEN '✅ Table EXISTS'
        ELSE '❌ Table DOES NOT EXIST - Run migration script first!'
    END as table_status;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '2. Checking table columns (should be 14 columns)...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    ordinal_position as "#",
    column_name as "Column",
    data_type as "Type",
    CASE WHEN is_nullable = 'NO' THEN 'NOT NULL' ELSE 'NULL' END as "Nullable",
    column_default as "Default"
FROM information_schema.columns 
WHERE table_name = 'student_personal_documents'
ORDER BY ordinal_position;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '3. Checking indexes...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    indexname as "Index Name",
    indexdef as "Definition"
FROM pg_indexes 
WHERE tablename = 'student_personal_documents'
ORDER BY indexname;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '4. Checking RLS (Row Level Security) status...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    schemaname as "Schema",
    tablename as "Table",
    CASE WHEN rowsecurity THEN '✅ ENABLED' ELSE '❌ DISABLED' END as "RLS Status"
FROM pg_tables 
WHERE tablename = 'student_personal_documents';

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '5. Checking RLS policies (should be 3 policies)...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    policyname as "Policy Name",
    cmd as "Operation",
    roles as "Roles",
    CASE WHEN permissive = 'PERMISSIVE' THEN '✅' ELSE '❌' END as "Permissive"
FROM pg_policies 
WHERE tablename = 'student_personal_documents'
ORDER BY policyname;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '6. Checking table constraints...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    constraint_name as "Constraint",
    constraint_type as "Type"
FROM information_schema.table_constraints 
WHERE table_name = 'student_personal_documents'
ORDER BY constraint_type, constraint_name;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '7. Checking storage bucket (assessment-evidence)...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    id as "Bucket ID",
    name as "Bucket Name",
    CASE WHEN public THEN '✅ PUBLIC' ELSE '❌ PRIVATE' END as "Access",
    created_at as "Created At"
FROM storage.buckets 
WHERE id = 'assessment-evidence';

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '8. Checking storage policies for assessment-evidence bucket...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    policyname as "Policy Name",
    roles as "Roles",
    cmd as "Operation"
FROM pg_policies 
WHERE tablename = 'objects' 
  AND (policyname ILIKE '%assessment%' OR policyname ILIKE '%evidence%')
ORDER BY policyname;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '9. Checking trigger for updated_at...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    trigger_name as "Trigger",
    event_manipulation as "Event",
    action_timing as "Timing",
    action_statement as "Action"
FROM information_schema.triggers 
WHERE event_object_table = 'student_personal_documents'
ORDER BY trigger_name;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '10. Testing data operations (INSERT, SELECT, UPDATE)...'
\echo '──────────────────────────────────────────────────────────────────────'

DO $$
DECLARE
    test_student_id UUID;
    test_doc_id UUID;
    insert_success BOOLEAN := FALSE;
    select_success BOOLEAN := FALSE;
    update_success BOOLEAN := FALSE;
    delete_success BOOLEAN := FALSE;
BEGIN
    -- Get a real student ID from database (if exists)
    SELECT id INTO test_student_id 
    FROM user_profiles 
    WHERE role = 'student' 
    LIMIT 1;
    
    IF test_student_id IS NULL THEN
        RAISE NOTICE '⚠️  No student found in database - skipping data operation tests';
        RETURN;
    END IF;
    
    -- Test INSERT
    BEGIN
        INSERT INTO student_personal_documents (
            student_id,
            document_type,
            document_name,
            file_url,
            file_path,
            file_name,
            file_size,
            status
        ) VALUES (
            test_student_id,
            'test_document_verification',
            'Test Document',
            'https://test.com/file.pdf',
            'test/file.pdf',
            'file.pdf',
            1024,
            'pending'
        ) RETURNING id INTO test_doc_id;
        
        insert_success := TRUE;
        RAISE NOTICE '✅ INSERT successful - Document ID: %', test_doc_id;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE '❌ INSERT failed: %', SQLERRM;
    END;
    
    -- Test SELECT
    IF insert_success THEN
        BEGIN
            PERFORM * FROM student_personal_documents WHERE id = test_doc_id;
            select_success := TRUE;
            RAISE NOTICE '✅ SELECT successful';
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE '❌ SELECT failed: %', SQLERRM;
        END;
    END IF;
    
    -- Test UPDATE
    IF select_success THEN
        BEGIN
            UPDATE student_personal_documents 
            SET status = 'approved' 
            WHERE id = test_doc_id;
            update_success := TRUE;
            RAISE NOTICE '✅ UPDATE successful';
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE '❌ UPDATE failed: %', SQLERRM;
        END;
    END IF;
    
    -- Test DELETE (cleanup)
    IF insert_success THEN
        BEGIN
            DELETE FROM student_personal_documents WHERE id = test_doc_id;
            delete_success := TRUE;
            RAISE NOTICE '✅ DELETE successful (test cleanup completed)';
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE '❌ DELETE failed: %', SQLERRM;
        END;
    END IF;
    
    -- Summary
    RAISE NOTICE '';
    RAISE NOTICE 'Test Summary:';
    RAISE NOTICE '  INSERT: %', CASE WHEN insert_success THEN '✅ PASS' ELSE '❌ FAIL' END;
    RAISE NOTICE '  SELECT: %', CASE WHEN select_success THEN '✅ PASS' ELSE '❌ FAIL' END;
    RAISE NOTICE '  UPDATE: %', CASE WHEN update_success THEN '✅ PASS' ELSE '❌ FAIL' END;
    RAISE NOTICE '  DELETE: %', CASE WHEN delete_success THEN '✅ PASS' ELSE '❌ FAIL' END;
END $$;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '11. Checking for any existing documents...'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    COUNT(*) as "Total Documents",
    COUNT(DISTINCT student_id) as "Students with Documents",
    COUNT(CASE WHEN status = 'pending' THEN 1 END) as "Pending",
    COUNT(CASE WHEN status = 'approved' THEN 1 END) as "Approved",
    COUNT(CASE WHEN status = 'rejected' THEN 1 END) as "Rejected"
FROM student_personal_documents;

\echo ''
\echo '──────────────────────────────────────────────────────────────────────'
\echo '12. Final Summary'
\echo '──────────────────────────────────────────────────────────────────────'

SELECT 
    '✅ Verification Complete!' as "Status",
    'Check results above for any ❌ failures' as "Next Step";

\echo ''
\echo '═══════════════════════════════════════════════════════════════════════'
\echo 'DEPLOYMENT CHECKLIST:'
\echo '═══════════════════════════════════════════════════════════════════════'
\echo '  [ ] Table exists with 14 columns'
\echo '  [ ] 3 indexes created'
\echo '  [ ] RLS enabled'
\echo '  [ ] 3 RLS policies active'
\echo '  [ ] Unique constraint on (student_id, document_type)'
\echo '  [ ] Storage bucket "assessment-evidence" exists'
\echo '  [ ] Trigger for updated_at working'
\echo '  [ ] INSERT operation succeeds'
\echo '  [ ] SELECT operation succeeds'
\echo '  [ ] UPDATE operation succeeds'
\echo ''
\echo 'If all checks pass ✅, deployment is successful!'
\echo 'If any check fails ❌, review the migration script and re-run.'
\echo '═══════════════════════════════════════════════════════════════════════'
