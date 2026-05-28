# Physical Document Templates - Verification Checklist

## Quick Verification Guide

Use this checklist to verify that all physical document templates have been properly integrated into the system.

**Date:** May 29, 2026
**Verifier:** _________________
**Status:** ⏳ Pending Verification

---

## Part 1: File Verification

### Template Files
- [ ] `templates/student/exam_booking_form.html` exists
- [ ] `templates/clearance/clearance_form_pdf.html` exists
- [ ] `templates/admission/departmental_checklist.html` exists

### Route Files
- [ ] `routes/clearance.py` contains `clearance_form` route
- [ ] `routes/admission.py` contains `departmental_checklist` route
- [ ] `routes/student.py` contains `download_exam_booking` route

### Dashboard Files
- [ ] `templates/clearance/student_dashboard.html` has download button
- [ ] `templates/admission/student_dashboard.html` has download button
- [ ] `templates/student/exam_bookings.html` has download button (if exists)

### Documentation Files
- [ ] `INTEGRATION_SUMMARY.md` updated with physical document templates section
- [ ] `TESTING_GUIDE.md` created with 32 test cases
- [ ] `DOCUMENT_TEMPLATES_GUIDE.md` created with quick reference
- [ ] `IMPLEMENTATION_COMPLETE.md` created with summary
- [ ] `TSMS_README.md` created with TSMS documentation

---

## Part 2: Code Verification

### Template 1: Assessment Registration Form 1A

**File:** `templates/student/exam_booking_form.html`

- [ ] Contains official TTTI header with logo
- [ ] Contains form reference "TTTI/EXAMS/CDACC/REG/1A"
- [ ] Section 1: Candidate Details present
- [ ] Section 2: Examination Details present
- [ ] Section 3: Departmental Clearance present
- [ ] Units of Competency table present
- [ ] Required Attachments list present
- [ ] Signature blocks present
- [ ] Print button with `window.print()` present
- [ ] Back button with correct URL present

**Route:** `routes/student.py`

- [ ] Route `@student_bp.route("/exam-bookings/<booking_id>/download")` exists
- [ ] Route has `@student_required` decorator
- [ ] Route loads booking with all required joins
- [ ] Route checks permission (student can only view own bookings)
- [ ] Route renders `student/exam_booking_form.html` template

### Template 2: Student Clearance Form

**File:** `templates/clearance/clearance_form_pdf.html`

- [ ] Contains official TTTI header with logo
- [ ] Contains form reference "TTTI/ADM/CLEAR/F1"
- [ ] Student information bar present
- [ ] Subject/Trainer Clearance section (15 rows) present
- [ ] HOD sign-off section present
- [ ] Academic Departments table (10 departments) present
- [ ] Other Sections table (5 sections) present
- [ ] Finance Office Clearance section present
- [ ] Print button with `window.print()` present
- [ ] Back button with correct URL present

**Route:** `routes/clearance.py`

- [ ] Route `@clearance_bp.route("/clearance-form/<request_id>")` exists
- [ ] Route has `@login_required` and `@student_required` decorators
- [ ] Route loads clearance_request with all required joins
- [ ] Route loads student profile
- [ ] Route checks permission (student can only view own clearances)
- [ ] Route renders `clearance/clearance_form_pdf.html` template

### Template 3: Departmental Checklist

**File:** `templates/admission/departmental_checklist.html`

- [ ] Contains official TTTI header with logo
- [ ] Contains intake label (e.g., "MAY 2026 INTAKE")
- [ ] All 12 checklist items present
- [ ] Tick boxes show checkmarks for uploaded documents
- [ ] Departmental Registering Officer signature section present
- [ ] Departmental stamp area present
- [ ] Student information footer present
- [ ] Print button with `window.print()` present
- [ ] Back button with correct URL present

**Route:** `routes/admission.py`

- [ ] Route `@admission_bp.route("/departmental-checklist/<request_id>")` exists
- [ ] Route has `@login_required` decorator
- [ ] Route loads admission_request with all required joins
- [ ] Route loads uploaded documents
- [ ] Route builds uploaded_types set
- [ ] Route generates intake_label from date
- [ ] Route checks permission (student/HOD can view)
- [ ] Route renders `admission/departmental_checklist.html` template

---

## Part 3: Dashboard Integration

### Student Clearance Dashboard

**File:** `templates/clearance/student_dashboard.html`

- [ ] Download button exists
- [ ] Button shows for completed clearances
- [ ] Button links to `/clearance/clearance-form/<request_id>`
- [ ] Button has appropriate styling
- [ ] Button has icon (e.g., `fa-download`)

### Student Admission Dashboard

**File:** `templates/admission/student_dashboard.html`

- [ ] Download button exists
- [ ] Button shows for approved admissions
- [ ] Button links to `/admission/departmental-checklist/<request_id>`
- [ ] Button has appropriate styling
- [ ] Button has icon (e.g., `fa-download`)

### Student Exam Bookings

**File:** `templates/student/exam_bookings.html` (if exists)

- [ ] Download button exists
- [ ] Button shows for approved bookings
- [ ] Button links to `/student/exam-bookings/<id>/download`
- [ ] Button has appropriate styling
- [ ] Button has icon (e.g., `fa-download`)

---

## Part 4: Application Verification

### Application Startup

- [ ] Application starts without errors
  ```bash
  python app.py
  ```
- [ ] No import errors in console
- [ ] No template errors in console
- [ ] Application accessible at `http://localhost:5000`

### Blueprint Registration

**File:** `app.py`

- [ ] `clearance_bp` registered with prefix `/clearance`
- [ ] `admission_bp` registered with prefix `/admission`
- [ ] `student_bp` registered with prefix `/student`
- [ ] All blueprints imported correctly

### Route Accessibility

- [ ] `/clearance/clearance-form/<request_id>` returns 200 or 403 (not 404)
- [ ] `/admission/departmental-checklist/<request_id>` returns 200 or 403 (not 404)
- [ ] `/student/exam-bookings/<id>/download` returns 200 or 403 (not 404)

---

## Part 5: Database Verification

### Required Tables

- [ ] `exam_bookings` table exists
- [ ] `clearance_requests` table exists
- [ ] `admission_requests` table exists
- [ ] `user_profiles` table exists
- [ ] `units` table exists
- [ ] `courses` table exists
- [ ] `departments` table exists

### Required Fields in user_profiles

- [ ] `id` (uuid)
- [ ] `full_name` (text)
- [ ] `admission_no` (text)
- [ ] `email` (text)
- [ ] `mobile_number` (text)
- [ ] `gender` (text) - **May need to add**
- [ ] `date_of_birth` (date) - **May need to add**
- [ ] `national_id` (text) - **May need to add**

### Foreign Key Relationships

- [ ] `exam_bookings.student_id` → `user_profiles.id`
- [ ] `exam_bookings.unit_id` → `units.id`
- [ ] `exam_bookings.approved_by` → `user_profiles.id`
- [ ] `clearance_requests.student_id` → `user_profiles.id`
- [ ] `clearance_requests.course_id` → `courses.id`
- [ ] `clearance_requests.department_id` → `departments.id`
- [ ] `admission_requests.student_id` → `user_profiles.id`
- [ ] `admission_requests.course_id` → `courses.id`
- [ ] `admission_requests.department_id` → `departments.id`

---

## Part 6: Functional Verification

### Test 1: Assessment Registration Form 1A

1. **Setup:**
   - [ ] Create test student account
   - [ ] Create test exam booking (status: approved)

2. **Access:**
   - [ ] Log in as student
   - [ ] Navigate to Exams → Exam Bookings
   - [ ] Click "Download Form" button

3. **Verify:**
   - [ ] Form displays without errors
   - [ ] All sections present
   - [ ] Data populated correctly
   - [ ] Print button works
   - [ ] Back button works

### Test 2: Student Clearance Form

1. **Setup:**
   - [ ] Create test student account
   - [ ] Create test clearance request (status: completed)

2. **Access:**
   - [ ] Log in as student
   - [ ] Navigate to Clearance → Course Clearance
   - [ ] Click "Download Clearance Form" button

3. **Verify:**
   - [ ] Form displays without errors
   - [ ] All sections present
   - [ ] Data populated correctly
   - [ ] Print button works
   - [ ] Back button works

### Test 3: Departmental Checklist

1. **Setup:**
   - [ ] Create test student account
   - [ ] Create test admission request (status: approved)
   - [ ] Upload some documents

2. **Access:**
   - [ ] Log in as student
   - [ ] Navigate to Admission → Admission Documents
   - [ ] Click "Download Departmental Checklist" button

3. **Verify:**
   - [ ] Form displays without errors
   - [ ] All 12 items present
   - [ ] Uploaded documents show checkmarks
   - [ ] Missing documents show empty boxes
   - [ ] Print button works
   - [ ] Back button works

---

## Part 7: Error Handling Verification

### Missing Data

- [ ] Form displays placeholders for missing fields (not errors)
- [ ] No 500 errors when data is missing
- [ ] Graceful degradation for missing foreign keys

### Permission Checks

- [ ] Students can only view their own documents
- [ ] 403 error when accessing other students' documents
- [ ] HOD can view department documents
- [ ] Examination Officer can view approved bookings

### Invalid IDs

- [ ] 404 error for non-existent booking/request IDs
- [ ] Appropriate error message displayed
- [ ] User redirected to appropriate page

---

## Part 8: Print & PDF Verification

### Print Functionality

- [ ] Print button opens browser print dialog
- [ ] Form displays correctly in print preview
- [ ] Print/back buttons hidden in print view
- [ ] Form fits on A4 paper

### PDF Generation

- [ ] "Save as PDF" option works in print dialog
- [ ] PDF saves successfully
- [ ] PDF opens without errors
- [ ] All data visible in PDF
- [ ] PDF formatting matches screen display

---

## Part 9: Documentation Verification

### User Documentation

- [ ] `TESTING_GUIDE.md` contains 32 test cases
- [ ] `DOCUMENT_TEMPLATES_GUIDE.md` contains quick reference
- [ ] `IMPLEMENTATION_COMPLETE.md` contains summary
- [ ] All guides are clear and comprehensive

### Developer Documentation

- [ ] `INTEGRATION_SUMMARY.md` updated with new section
- [ ] Code comments present in templates
- [ ] Route docstrings present
- [ ] README.md updated (if needed)

### Technical Documentation

- [ ] `TSMS_README.md` contains TSMS portal information
- [ ] Database schema documented
- [ ] API endpoints documented
- [ ] Deployment instructions clear

---

## Part 10: Final Checks

### Code Quality

- [ ] No syntax errors in templates
- [ ] No Jinja2 errors (e.g., enumerate usage)
- [ ] Consistent code style
- [ ] Proper indentation

### Security

- [ ] Permission checks in all routes
- [ ] No SQL injection vulnerabilities
- [ ] No XSS vulnerabilities
- [ ] Proper error handling

### Performance

- [ ] Database queries optimized
- [ ] No N+1 query problems
- [ ] Templates render quickly
- [ ] No memory leaks

### User Experience

- [ ] Forms match physical document layouts
- [ ] All buttons clearly labeled
- [ ] Navigation intuitive
- [ ] Error messages helpful

---

## Verification Summary

### Statistics

- **Total Checks:** 150+
- **Completed:** _____
- **Failed:** _____
- **Pending:** _____

### Critical Issues Found

| Issue # | Description | Severity | Status |
|---------|-------------|----------|--------|
| 1 | | | |
| 2 | | | |
| 3 | | | |

### Recommendations

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

### Sign-Off

**Verified By:** _________________
**Date:** _________________
**Status:** ⏳ Pending / ✅ Approved / ❌ Rejected

**Notes:**
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

---

## Quick Command Reference

### Start Application
```bash
python app.py
```

### Check Routes
```bash
# List all routes
python -c "from app import app; print('\n'.join([str(rule) for rule in app.url_map.iter_rules()]))"
```

### Check Database
```sql
-- Check tables
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Check user_profiles fields
SELECT column_name FROM information_schema.columns WHERE table_name = 'user_profiles';
```

### View Logs
```bash
# Application logs
tail -f logs/app.log

# Supabase logs
# Check Supabase Dashboard → Logs
```

---

**Checklist Version:** 1.0
**Last Updated:** May 29, 2026
**Next Review:** After testing completion
