# Trainer Portfolio - New Document Types

## Summary of Changes

Added 7 new document types to the Trainer Portfolio system for curriculum planning and training management.

## New Document Types

### 1. **Occupational Standards (OS)**
- **Value**: `occupational_standards`
- **Purpose**: National or industry occupational standards that define competencies
- **Examples**: NITA Occupational Standards, CDACC competency frameworks

### 2. **Modularized Curricula / Syllabus**
- **Value**: `modularized_curricula`
- **Purpose**: Modular curriculum documents and course syllabi
- **Examples**: Module breakdown, syllabus documents, curriculum guides

### 3. **Course Outline**
- **Value**: `course_outline`
- **Purpose**: Detailed course outlines showing topics, objectives, and structure
- **Examples**: Unit outlines, course structure documents

### 4. **Modularized Training Schedules**
- **Value**: `modularized_training_schedules`
- **Purpose**: Schedules showing training delivery by modules
- **Examples**: Term schedules, module timing plans

### 5. **Learning Plans**
- **Value**: `learning_plans`
- **Purpose**: Individual or class learning plans
- **Examples**: Trainee learning plans, personalized learning pathways

### 6. **Session Plans**
- **Value**: `session_plans`
- **Purpose**: Detailed lesson/session plans for individual training sessions
- **Examples**: Daily lesson plans, session guides

### 7. **Training Timetables**
- **Value**: `training_timetables`
- **Purpose**: Timetables showing class schedules
- **Examples**: Weekly timetables, term schedules

## Files Modified

### 1. `templates/trainer/portfolio.html`
- ✅ Added 7 new options to the **Filter Documents** dropdown
- ✅ Added 7 new options to the **Upload Document** dropdown
- ✅ Placed new types at the top of both dropdowns for easy access

### 2. `supabase_schema.sql`
- ✅ Updated `trainer_documents` table CHECK constraint
- ✅ Added new document types to the allowed values

### 3. `trainer_documents_update_migration.sql` (NEW)
- ✅ Migration script to update existing database
- ✅ Drops old constraint and creates new one
- ✅ Includes verification query

## Database Migration Required

### Step 1: Run the Migration
Execute the migration in your **Supabase SQL Editor**:

**File**: `trainer_documents_update_migration.sql`

**Steps**:
1. Open Supabase project → SQL Editor
2. Copy contents of `trainer_documents_update_migration.sql`
3. Paste and click **Run**

### Step 2: Verify
The migration includes a verification query that shows:
- Total documents in the system
- Count of documents using new types

## Usage Instructions for Trainers

### Uploading New Document Types

1. Navigate to **Trainer Dashboard** → **Portfolio**
2. Scroll to **Upload New Document** section
3. Select **Document Type** from dropdown:
   - New types appear at the top of the list
   - E.g., "Occupational Standards (OS)", "Session Plans"
4. Fill in remaining fields:
   - Document Name (required)
   - Unit (optional - link to specific unit)
   - Academic Year (required)
   - Term (optional)
   - Description (optional)
5. Click to upload file
6. Click **Upload Document**

### Filtering by New Types

1. Use the **Filter Documents** section at the top
2. Select **Document Type** → Choose one of the new types
3. Optionally filter by Year and Term
4. Click **Apply**

## Document Organization Recommendations

### Suggested Workflow

1. **Start of Academic Year**:
   - Upload **Occupational Standards** for reference
   - Upload **Modularized Curricula** for each unit
   - Upload **Course Outlines** for all units

2. **Term Planning**:
   - Upload **Modularized Training Schedules** for the term
   - Upload **Training Timetables** for class schedules
   - Create **Learning Plans** for trainees

3. **Daily/Weekly Teaching**:
   - Upload **Session Plans** before each lesson
   - Update as needed throughout the term

4. **Assessment & Evaluation** (existing types):
   - Continue using existing types like Assessment Plans, Marking Guides, etc.

## Complete Document Type List (Updated)

### Curriculum & Planning (NEW)
1. Occupational Standards (OS)
2. Modularized Curricula / Syllabus
3. Course Outline
4. Modularized Training Schedules
5. Learning Plans
6. Session Plans
7. Training Timetables

### Assessment Planning
8. Assessment Plan
9. Competency Standard
10. Assessment Tools
11. Marking Guide
12. Written/Oral Mark Sheets
13. Observation Checklist
14. Product Checklist

### Assessment Records
15. Assessment Records
16. Evidence Register
17. Feedback Forms

### Verification & Moderation
18. Internal Verification Report
19. Moderation Report

### Industrial Attachment
20. Industrial Attachment Plan
21. Mentoring Tools
22. Industrial Attachment Report

### Administrative Records
23. Trainee Attendance Records
24. Communication Records
25. Assessment Schedule

## Benefits

### For Trainers
- ✅ Centralized storage for all training documents
- ✅ Easy categorization and retrieval
- ✅ Better planning and organization
- ✅ Audit trail for compliance

### For Management
- ✅ Oversight of curriculum delivery
- ✅ Quality assurance monitoring
- ✅ Compliance with NITA/CDACC requirements
- ✅ Easy document verification during audits

### For Quality Assurance
- ✅ Complete portfolio review capability
- ✅ Evidence of systematic planning
- ✅ Standards compliance verification

## Technical Notes

### Database Constraint
```sql
CHECK (document_type IN (
    'occupational_standards',
    'modularized_curricula',
    'course_outline',
    'modularized_training_schedules',
    'learning_plans',
    'session_plans',
    'training_timetables',
    -- ... existing types
))
```

### Backend Compatibility
The existing backend (`routes/trainer.py`) requires no changes:
- Uses dynamic field values
- No hardcoded document type checks
- Display uses `replace('_', ' ')|title` filter

## Testing Checklist

After deployment, verify:

- [ ] Can select new document types in filter dropdown
- [ ] Can select new document types in upload dropdown
- [ ] Can successfully upload documents with new types
- [ ] Documents display correctly in the grid
- [ ] Filter works for new document types
- [ ] Document type badge shows correctly formatted name

## Rollback Plan

If issues occur, rollback the database constraint:

```sql
ALTER TABLE trainer_documents 
DROP CONSTRAINT trainer_documents_document_type_check;

-- Add back old constraint (without new types)
ALTER TABLE trainer_documents 
ADD CONSTRAINT trainer_documents_document_type_check 
CHECK (document_type IN (
    'assessment_plan',
    'competency_standard',
    -- ... old types only
));
```

## Support

For questions or issues:
1. Check that migration was run successfully
2. Verify dropdown options are visible
3. Test upload with one new document type
4. Contact system administrator if errors persist

---

**Last Updated**: June 2026  
**Status**: Ready for deployment  
**Impact**: Low risk - additive changes only
