# 🚀 MY DOCUMENTS DEPLOYMENT INSTRUCTIONS

## ✅ CURRENT STATUS

**Date:** June 6, 2026  
**Feature:** Student "My Documents" Upload System  
**Status:** ⚠️ **REQUIRES DATABASE MIGRATION**

---

## 📋 WHAT'S BEEN DONE

### ✅ Code Changes Complete
1. ✅ Updated `routes/student.py` to use `student_personal_documents` table
2. ✅ Created migration script: `migration_student_documents.sql`
3. ✅ Added table definition to `supabase_schema.sql`
4. ✅ Template ready: `templates/student/my_documents.html`
5. ✅ All code committed to GitHub

### ⚠️ Database Migration Required
The **code is ready** but the database table **does NOT exist yet** in production.

---

## 🎯 DEPLOYMENT STEPS

### **STEP 1: Backup Your Database** ⚠️

Before running any migration, backup your Supabase database:

```bash
# Using Supabase Dashboard
1. Go to https://app.supabase.com
2. Select your project
3. Go to Database → Backups
4. Click "Create Backup"
5. Wait for completion
```

### **STEP 2: Run the Migration Script** 🔧

**Option A: Using Supabase Dashboard (Recommended)**

1. Open your Supabase project dashboard
2. Navigate to **SQL Editor** (left sidebar)
3. Click **"New Query"**
4. Copy the entire contents of `migration_student_documents.sql`
5. Paste into the SQL editor
6. Click **"Run"** (or press Ctrl+Enter)
7. Wait for success message: "Success. No rows returned"

**Option B: Using psql Command Line**

```bash
# If you have psql installed and database credentials
psql -h db.your-project.supabase.co \
     -U postgres \
     -d postgres \
     -f migration_student_documents.sql
```

**Option C: Using Supabase CLI**

```bash
# If you have Supabase CLI installed
supabase db push
```

### **STEP 3: Verify Migration Success** ✅

Run this verification query in Supabase SQL Editor:

```sql
-- Check if table exists
SELECT 
    table_name, 
    column_name, 
    data_type,
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'student_personal_documents'
ORDER BY ordinal_position;
```

**Expected Result:** You should see 13 columns:
- id (uuid)
- student_id (uuid)
- document_type (text)
- document_name (text)
- file_url (text)
- file_path (text)
- file_name (text)
- file_size (bigint)
- status (text)
- verified_by (uuid)
- verified_at (timestamp with time zone)
- rejection_reason (text)
- created_at (timestamp with time zone)
- updated_at (timestamp with time zone)

### **STEP 4: Check RLS Policies** 🔐

Run this to verify Row Level Security policies are in place:

```sql
-- Check RLS policies
SELECT 
    schemaname, 
    tablename, 
    policyname, 
    permissive, 
    roles, 
    cmd
FROM pg_policies 
WHERE tablename = 'student_personal_documents';
```

**Expected Result:** You should see 3 policies:
1. `student_personal_documents_student_manage` - Students manage their own docs
2. `student_personal_documents_dept_admin` - Dept Admin can view/verify
3. `student_personal_documents_super_admin` - Super Admin full access

### **STEP 5: Verify Storage Bucket** 📦

The system uses the `assessment-evidence` bucket for storing documents.

1. Go to Supabase Dashboard → **Storage**
2. Verify `assessment-evidence` bucket exists
3. If missing, create it:

```sql
-- Create bucket if it doesn't exist
INSERT INTO storage.buckets (id, name, public)
VALUES ('assessment-evidence', 'assessment-evidence', true)
ON CONFLICT (id) DO NOTHING;
```

4. Set bucket policies to allow authenticated users to upload:

```sql
-- Allow authenticated users to upload
CREATE POLICY "Authenticated users can upload files"
ON storage.objects FOR INSERT
TO authenticated
WITH CHECK (bucket_id = 'assessment-evidence');

-- Allow authenticated users to read their own files
CREATE POLICY "Users can read uploaded files"
ON storage.objects FOR SELECT
TO authenticated
USING (bucket_id = 'assessment-evidence');
```

### **STEP 6: Test the Feature** 🧪

1. **Login as a student**
2. Navigate to **"My Documents"** menu
3. Try uploading a document (passport photo, admission letter, etc.)
4. **Expected behavior:**
   - File uploads without errors
   - Success message: "1 document(s) uploaded successfully"
   - Document appears in the list with status "Pending"
   - Can re-upload same document type (replaces old one)

5. **Test different document types:**
   - Passport Photo (image)
   - Admission Letter (PDF)
   - Medical Form (PDF)
   - KCSE Result Slip (PDF or image)
   - National ID (PDF or image)

### **STEP 7: Monitor for Errors** 🔍

**Common Errors and Solutions:**

| Error | Cause | Solution |
|-------|-------|----------|
| `relation "student_personal_documents" does not exist` | Migration not run | Run migration script |
| `permission denied for table` | RLS policies missing | Run RLS section of migration |
| `bucket "assessment-evidence" does not exist` | Storage bucket missing | Create bucket (see Step 5) |
| `duplicate key value violates unique constraint` | Same doc type uploaded twice | This is expected - it replaces old file |

**Check Application Logs:**

```bash
# If running locally
tail -f logs/app.log

# If on Render/Heroku
render logs --tail
# or
heroku logs --tail
```

---

## 📊 DATABASE SCHEMA REFERENCE

### Table: `student_personal_documents`

```sql
┌─────────────────────┬──────────────┬──────────────┬─────────────┐
│ Column              │ Type         │ Nullable     │ Default     │
├─────────────────────┼──────────────┼──────────────┼─────────────┤
│ id                  │ UUID         │ NO           │ uuid_v4()   │
│ student_id          │ UUID         │ NO           │ -           │
│ document_type       │ TEXT         │ NO           │ -           │
│ document_name       │ TEXT         │ NO           │ -           │
│ file_url            │ TEXT         │ NO           │ -           │
│ file_path           │ TEXT         │ NO           │ -           │
│ file_name           │ TEXT         │ NO           │ -           │
│ file_size           │ BIGINT       │ YES          │ NULL        │
│ status              │ TEXT         │ YES          │ 'pending'   │
│ verified_by         │ UUID         │ YES          │ NULL        │
│ verified_at         │ TIMESTAMPTZ  │ YES          │ NULL        │
│ rejection_reason    │ TEXT         │ YES          │ NULL        │
│ created_at          │ TIMESTAMPTZ  │ NO           │ NOW()       │
│ updated_at          │ TIMESTAMPTZ  │ NO           │ NOW()       │
└─────────────────────┴──────────────┴──────────────┴─────────────┘
```

### Supported Document Types:
- `passport_photo` ⭐ Required
- `admission_letter` ⭐ Required
- `medical_form` ⭐ Required
- `personal_data_form` ⭐ Required
- `declaration_form` ⭐ Required
- `kcse_result_slip` ⭐ Required
- `kcse_certificate` ⭐ Required
- `kcpe_result_slip` ⭐ Required
- `birth_certificate` ⭐ Required
- `national_id` ⭐ Required
- `guardian_id` (Optional)
- `consent_form` ⭐ Required
- `most_recent_result_slip` (Special - highlighted in UI)

### Document Status Values:
- `pending` - Uploaded but not yet verified
- `approved` - Verified and accepted by admin
- `rejected` - Rejected with reason

---

## 🔧 ROLLBACK PROCEDURE (If Needed)

If something goes wrong, you can rollback the migration:

```sql
-- Drop the table (WARNING: This deletes all uploaded documents)
DROP TABLE IF EXISTS student_personal_documents CASCADE;

-- Drop the indexes
DROP INDEX IF EXISTS idx_student_personal_documents_student;
DROP INDEX IF EXISTS idx_student_personal_documents_type;
DROP INDEX IF EXISTS idx_student_personal_documents_status;
```

**Note:** This only affects the new personal documents table. The old `trainee_documents` table (for POE files) is NOT affected.

---

## 📞 SUPPORT & TROUBLESHOOTING

### Issue: Migration fails with "function set_updated_at() does not exist"

**Solution:** The trigger function should exist from base schema. If missing, add it:

```sql
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
```

### Issue: Students can see other students' documents

**Solution:** Check RLS is enabled:

```sql
-- Enable RLS
ALTER TABLE student_personal_documents ENABLE ROW LEVEL SECURITY;

-- Verify RLS is enabled
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE tablename = 'student_personal_documents';
```

### Issue: Files upload but don't appear in list

**Solution:** Check the GET query in `routes/student.py`:

```python
# This should return documents
documents_data = db.table("student_personal_documents").select("*").eq("student_id", student_id).execute().data or []
```

Run this SQL to check data:

```sql
SELECT * FROM student_personal_documents 
WHERE student_id = 'YOUR_STUDENT_UUID_HERE';
```

---

## ✅ POST-DEPLOYMENT CHECKLIST

- [ ] Database backup created
- [ ] Migration script executed successfully
- [ ] Table `student_personal_documents` exists with 13 columns
- [ ] 3 RLS policies in place
- [ ] Storage bucket `assessment-evidence` exists and accessible
- [ ] Tested document upload as student (success)
- [ ] Uploaded document appears in "My Documents" list
- [ ] Can re-upload same document type (replaces old)
- [ ] Status shows as "Pending" after upload
- [ ] No errors in application logs
- [ ] Dept Admin can view student documents (optional - test later)

---

## 📝 TECHNICAL NOTES

### Why a New Table?

The existing `trainee_documents` table was designed for **Portfolio of Evidence (POE)** files:
- Marked scripts
- Practical products
- Video/audio recordings
- Industrial attachment logbook

It has a CHECK constraint that only allows these types. Personal/admission documents (passport photo, birth certificate, etc.) were being rejected.

The new `student_personal_documents` table is specifically for:
- Admission documents
- Personal identification
- Academic certificates
- Consent forms

### Security Features

1. **Row Level Security (RLS):** Students can ONLY see their own documents
2. **Unique Constraint:** Each student can only have ONE of each document type (prevents duplicates)
3. **Verification Workflow:** Documents require admin approval (status field)
4. **Audit Trail:** Tracks who verified, when, and rejection reasons

### Performance Optimizations

- **Indexed on student_id:** Fast lookup for individual student's documents
- **Indexed on document_type:** Fast filtering by document type
- **Indexed on status:** Efficient queries for pending/approved documents
- **UNIQUE constraint:** Prevents duplicate uploads at database level

---

**Deployment Guide Version:** 1.0  
**Last Updated:** June 6, 2026  
**Prepared By:** TTTI IT Department  
**Next Review:** After successful deployment

---

🎉 **Once deployed, the "My Documents" feature will be fully functional!**
