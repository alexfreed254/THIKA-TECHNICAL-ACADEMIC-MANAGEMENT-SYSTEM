# Marks Display Testing Guide

## Overview
This guide helps you test the marks display feature in the Trainer POE Review system.

## What Was Implemented

### 1. Marks Display Location
Marks are now displayed as a **purple badge with star icon** between the Approve and Reject buttons in:
- ✅ **Trainee POE Review** (main assessment list page)
- ✅ **Individual Assessment Review** page

### 2. Data Source
- Marks come from the **`marks` table** (Marks Entry menu)
- NOT from the `assessments` table (POE upload)

### 3. Badge Format
```
⭐ 85/100 (85.0%)
```
- Shows: marks_obtained / max_marks (percentage)
- Color: Purple background (#7b1fa2)
- Position: Between Approve and Reject buttons
- Only visible for: **pending assessments**

## Testing Steps

### Prerequisites
1. **Restart Flask Server** to load updated code
2. Have access to both:
   - Marks Entry menu (to enter marks)
   - Trainee POE Review menu (to view assessments)

### Step 1: Enter Marks Through Marks Entry Menu

1. Login as trainer
2. Navigate to: **Trainer Dashboard → Marks Entry**
3. Select:
   - Class
   - Unit
   - Student
   - Year
   - Term
   - Assessment Type (PRACTICAL, THEORY, etc.)
4. Enter marks (e.g., 85 out of 100)
5. Save the marks

**Note the values you entered:**
- Student: _____________
- Unit: _____________
- Year: _____________
- Term: _____________
- Marks: _______ / _______

### Step 2: Upload POE Assessment (if not already uploaded)

1. Login as student (or use existing assessment)
2. Upload POE with **matching details**:
   - Same Unit
   - Same Year
   - Same Term
   - Assessment Type
3. Status should be "Pending"

### Step 3: View in Trainee POE Review

1. Login as trainer
2. Navigate to: **Trainer Dashboard → Trainee POE Review**
3. Look for the assessment you uploaded

**Expected Result:**
```
[Approve Button] ⭐ 85/100 (85.0%) [Reject Button] [Review Button] [Delete Button]
```

### Step 4: Check Browser Console

1. Press **F12** (or right-click → Inspect)
2. Go to **Console** tab
3. Look for debug output:

```
=== Assessment Debug ===
ID: abc-123-xyz
Student: student-uuid
Student Name: John Doe
Unit: unit-uuid Unit Name
Year/Term/Cycle: 2024 / 1 / 1
Assessment Type/No: PRACTICAL # 1
Marks Data: 85 / 100
Has marks? true
========================

Rendering marks badge for assessment: abc-123-xyz Marks: 85 / 100 Percentage: 85.0%
```

### Step 5: Check Server Console

Look for backend debug output in your terminal/command prompt:

```
=== Looking for marks ===
Assessment ID: abc-123-xyz
Student ID: student-uuid
Unit ID: unit-uuid
Year: 2024
Term: 1 (type: <class 'int'>)
Assessment Type: PRACTICAL
Query executed - Found 1 marks rows
Marks data: [{'marks_obtained': 85.0, 'max_marks': 100.0, ...}]
✓ Attached marks: 85.0/100.0
```

### Step 6: Test Individual Review Page

1. Click the **[Review]** button on any assessment
2. Scroll to "Review Decision" section
3. Look for purple marks badge between Approve and Reject buttons

**Expected Result:**
```
[Approve Button] ⭐ Marks: 85/100 (85.0%) [Reject Button] [Delete Button]
```

## Troubleshooting

### Issue 1: Purple Badge Shows "0/100 (0.0%)"

**Possible Causes:**
1. No marks entered in Marks Entry menu
2. Marks entry doesn't match assessment (different student/unit/year/term)
3. Term field mismatch

**Solution:**
1. Check server console for: `"✗ No marks found, defaulting to 0/100"`
2. Verify marks exist in database:
   ```sql
   SELECT * FROM marks 
   WHERE student_id = 'your-student-uuid'
     AND unit_id = 'your-unit-uuid'
     AND year = 2024
     AND term = '1';
   ```
3. Ensure marks were saved correctly in Marks Entry menu
4. Re-enter marks with exact matching details

### Issue 2: Purple Badge Not Visible At All

**Possible Causes:**
1. Assessment status is not "pending" (only shows for pending assessments)
2. JavaScript error preventing render
3. CSS hiding the badge

**Solution:**
1. Check browser console for JavaScript errors
2. Verify assessment status is "pending" in database
3. Try different browser or clear cache
4. Inspect element to see if badge HTML exists but is hidden

### Issue 3: Backend Shows "Found 0 marks rows"

**Possible Causes:**
1. Term field type mismatch (INTEGER vs TEXT)
2. No matching marks entry in database
3. Query filtering too strict

**Solution:**
1. Backend already converts term to string: `str(assessment["term"])`
2. Check if marks table has term as "1", "2", "3" (TEXT)
3. Verify exact match on all fields: student_id, unit_id, year, term

### Issue 4: Marks Display Different Values Than Expected

**Possible Causes:**
1. Multiple marks entries for same student/unit/year/term
2. Wrong assessment type selected
3. Data updated but cache not cleared

**Solution:**
1. Backend uses first matching row
2. Consider adding assessment_type to join condition
3. Refresh page with Ctrl+F5 (hard refresh)

## Database Queries for Debugging

### Check if marks exist:
```sql
SELECT 
    m.id,
    m.student_id,
    m.unit_id,
    m.year,
    m.term,
    m.assessment_type,
    m.assessment_name,
    m.marks_obtained,
    m.max_marks,
    up.full_name as student_name,
    u.name as unit_name
FROM marks m
JOIN user_profiles up ON m.student_id = up.id
JOIN units u ON m.unit_id = u.id
WHERE m.year = 2024 
  AND m.term = '1'
ORDER BY m.created_at DESC;
```

### Check assessments:
```sql
SELECT 
    a.id,
    a.student_id,
    a.unit_id,
    a.year,
    a.term,
    a.assessment_type,
    a.assessment_no,
    a.status,
    up.full_name as student_name,
    u.name as unit_name
FROM assessments a
JOIN user_profiles up ON a.student_id = up.id
JOIN units u ON a.unit_id = u.id
WHERE a.status = 'pending'
ORDER BY a.uploaded_at DESC;
```

### Find matching marks for assessments:
```sql
SELECT 
    a.id as assessment_id,
    up.full_name,
    u.name as unit,
    a.year,
    a.term as assessment_term,
    a.assessment_type,
    a.status,
    m.term as marks_term,
    m.marks_obtained,
    m.max_marks
FROM assessments a
JOIN user_profiles up ON a.student_id = up.id
JOIN units u ON a.unit_id = u.id
LEFT JOIN marks m ON (
    m.student_id = a.student_id 
    AND m.unit_id = a.unit_id
    AND m.year = a.year
    AND m.term = CAST(a.term AS TEXT)
)
WHERE a.status = 'pending'
ORDER BY a.uploaded_at DESC;
```

## Success Criteria

✅ Marks badge displays correctly with actual marks from Marks Entry menu
✅ Badge appears between Approve and Reject buttons
✅ Badge shows correct format: ⭐ XX/YY (ZZ.Z%)
✅ Badge only appears for pending assessments
✅ Backend logs show marks being fetched successfully
✅ Frontend console shows marks data in assessment objects
✅ Works on both main list page and individual review page

## Next Steps After Testing

Once testing confirms everything works:

1. **Remove debug logging**:
   - Remove `console.log` statements from `templates/trainer/assessments.html`
   - Remove `print` statements from `routes/trainer.py`

2. **Commit changes**:
   ```bash
   git add routes/trainer.py templates/trainer/assessments.html
   git commit -m "feat: Display marks from Marks Entry in Trainer POE Review"
   git push origin main
   ```

3. **Optional enhancements**:
   - Add color coding based on marks (green for high, yellow for medium, red for low)
   - Add tooltip showing assessment name from marks table
   - Match on assessment_type for more precise matching

## Contact & Support

If issues persist after following this guide:
1. Check both server console AND browser console logs
2. Verify database schema matches expected structure
3. Ensure Supabase connection is working
4. Test with fresh data entry
