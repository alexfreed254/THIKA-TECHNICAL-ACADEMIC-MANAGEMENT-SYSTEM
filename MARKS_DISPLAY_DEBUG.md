# Marks Display Debug Guide

## Current Status
Enhanced debugging has been added to diagnose why marks are not displaying in the purple badge next to the Approve button in Trainer POE Review.

## Changes Made

### Backend: `routes/trainer.py` (lines 504-565)
- ✅ Added comprehensive debug logging for marks lookup
- ✅ Query explicitly converts term (INTEGER) to string to match marks table (TEXT)
- ✅ Logs show: assessment details, query execution, results found, marks attached
- ✅ Added error traceback for debugging issues

### Frontend: `templates/trainer/assessments.html`
- ✅ Enhanced console logging in `allAssessments()` function
- ✅ Logs show: assessment ID, student info, unit, year/term/cycle, marks data
- ✅ Added render-time logging in `fileRow()` and `fileCard()` functions
- ✅ Purple badge always renders with marks data (defaults to 0/100 if not found)

## How to Debug

### Step 1: Restart Flask Application
Restart your Flask server to load the updated code.

### Step 2: Open Trainer Assessments Page
1. Login as trainer
2. Navigate to: Trainer Dashboard → Trainee POE Review

### Step 3: Check Backend Logs (Server Console)
Look for output like:
```
=== Looking for marks ===
Assessment ID: abc-123-xyz
Student ID: student-uuid
Unit ID: unit-uuid
Year: 2024
Term: 1 (type: <class 'int'>)
Assessment Type: PRACTICAL
Query executed - Found 1 marks rows
✓ Attached marks: 85.0/100.0
```

**If you see "No marks found"**: The marks table doesn't have a matching entry for this student/unit/year/term.

### Step 4: Check Frontend Logs (Browser Console)
Press F12 → Console tab, look for:
```
=== Assessment Debug ===
ID: abc-123-xyz
Student: student-uuid
Student Name: John Doe
Marks Data: 85 / 100
Has marks? true
```

Then look for render logs:
```
Rendering marks badge for assessment: abc-123-xyz Marks: 85 / 100 Percentage: 85.0%
```

### Step 5: Verify Purple Badge Display
The purple badge should appear between Approve and Reject buttons showing:
⭐ 85/100 (85.0%)

## Troubleshooting

### Issue: Backend shows "No marks found"
**Cause**: No matching entry in `marks` table for this assessment.

**Solution**: 
1. Check if marks were entered through "Marks Entry" menu
2. Verify the marks entry has matching:
   - student_id
   - unit_id
   - year
   - term (must match as string: "1", "2", or "3")

**SQL Query to Check**:
```sql
SELECT * FROM marks 
WHERE student_id = 'your-student-uuid'
  AND unit_id = 'your-unit-uuid'
  AND year = 2024
  AND term = '1';
```

### Issue: Backend shows marks but frontend doesn't
**Cause**: Data serialization or JSON encoding issue.

**Check**: Server logs should show the marks being attached. Frontend `classesData` should include marks_obtained and max_marks fields.

### Issue: Frontend shows marks in console but not in UI
**Cause**: Rendering logic issue.

**Check**: Look for the "Rendering marks badge" console log. If present, the badge HTML is being generated. Inspect the DOM to see if it's hidden by CSS.

## Database Schema Reference

### `marks` table (where marks come from):
- `student_id` UUID
- `unit_id` UUID
- `year` INTEGER
- `term` TEXT (stores "1", "2", or "3")
- `marks_obtained` NUMERIC(5,2)
- `max_marks` NUMERIC(5,2)
- `assessment_type` TEXT
- `assessment_name` TEXT

### `assessments` table (POE uploads):
- `student_id` UUID
- `unit_id` UUID
- `year` INTEGER
- `term` INTEGER (stores 1, 2, or 3)
- `assessment_type` TEXT
- `assessment_no` INTEGER
- `cycle` INTEGER

## Join Logic
The backend joins these tables by:
1. `student_id` (exact match)
2. `unit_id` (exact match)
3. `year` (exact match)
4. `term` (converted to string for comparison)

## Next Actions

After reviewing the logs, you can:
1. **If no marks in database**: Enter marks through Marks Entry menu first
2. **If data mismatch**: Adjust the join logic to include assessment_type or cycle
3. **If rendering issue**: Check CSS or JavaScript logic

Once working, remove debug `console.log` and `print` statements for production.
