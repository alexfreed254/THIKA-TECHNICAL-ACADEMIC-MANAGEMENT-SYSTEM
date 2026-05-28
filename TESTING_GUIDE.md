# TTTI Academic Management System - Testing Guide

## Overview

This guide provides step-by-step instructions for testing all features of the Thika Technical Training Institute Academic Management System, with special focus on the newly integrated physical document templates.

**Testing Date:** May 29, 2026
**System Version:** Unified Academic Management System v2.0
**Focus Areas:** Physical Document Templates, Navigation, Workflows

---

## Pre-Testing Setup

### 1. Environment Verification

```bash
# Verify Python environment
python --version  # Should be 3.11+

# Verify dependencies
pip list | grep -E "flask|supabase|werkzeug"

# Check environment variables
cat .env | grep -E "SUPABASE_URL|SUPABASE_KEY|SECRET_KEY"
```

### 2. Database Verification

```sql
-- In Supabase SQL Editor, verify tables exist:
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- Verify user_profiles has required fields:
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'user_profiles';

-- Check for missing fields:
-- Expected: gender, date_of_birth, national_id, mobile_number
```

### 3. Test User Accounts

Create test accounts for each role:

```sql
-- Super Admin (via Supabase Auth + user_profiles)
-- Dept Admin (via Supabase Auth + user_profiles)
-- Trainer (via Supabase Auth + user_profiles)
-- Student (via user_profiles with password_hash)
-- Examination Officer (via Supabase Auth + user_profiles)
-- Employer (via Supabase Auth + user_profiles)
```

### 4. Start Application

```bash
# Local development
python app.py

# Or with gunicorn
gunicorn app:app --bind 0.0.0.0:5000 --reload
```

---

## Test Suite 1: Physical Document Templates

### Test 1.1: Assessment Registration Form 1A

**Objective:** Verify the Assessment Registration Form 1A renders correctly and matches the physical document.

**Prerequisites:**
- Student account with exam booking
- Exam booking approved by HOD

**Steps:**
1. Log in as Student
2. Navigate to **Exams → Exam Bookings**
3. Locate an approved exam booking
4. Click **"Download Form"** button
5. Verify form displays correctly

**Expected Results:**
- ✅ Official TTTI header with logo appears
- ✅ Form reference "TTTI/EXAMS/CDACC/REG/1A" is visible
- ✅ Section 1: Candidate Details populated with student data
- ✅ Section 2: Examination Details populated with booking data
- ✅ Section 3: Departmental Clearance shows HOD approval
- ✅ Units of Competency table shows booked unit
- ✅ Required Attachments list is visible
- ✅ Signature blocks present (Student, HOD, Exam Officer)
- ✅ Print button works (opens print dialog)
- ✅ Back button returns to exam bookings list

**Data Field Verification:**
- [ ] Full Name: `{{ booking.user_profiles.full_name }}`
- [ ] Admission Number: `{{ booking.user_profiles.admission_no }}`
- [ ] Gender: `{{ booking.user_profiles.gender }}` (may show placeholder)
- [ ] Date of Birth: `{{ booking.user_profiles.date_of_birth }}` (may show placeholder)
- [ ] Mobile Number: `{{ booking.user_profiles.mobile_number }}`
- [ ] Email: `{{ booking.user_profiles.email }}`
- [ ] Course Code: `{{ booking.units.code }}`
- [ ] Course Name: `{{ booking.units.name }}`
- [ ] Exam Date: `{{ booking.exam_date }}`
- [ ] Exam Session: `{{ booking.exam_session }}`
- [ ] Exam Venue: `{{ booking.exam_venue }}`
- [ ] Department: `{{ booking.user_profiles.classes.departments.name }}`
- [ ] HOD Name: `{{ booking.approved_by_user.full_name }}`
- [ ] Approval Date: `{{ booking.approved_at }}`

**Issues to Check:**
- Missing fields show placeholders (e.g., "_______________")
- No 500 errors on missing data
- PDF generation works correctly

---

### Test 1.2: Student Clearance Form

**Objective:** Verify the Student Clearance Form renders correctly and matches the physical document.

**Prerequisites:**
- Student account with completed clearance request
- Clearance request status: "completed" or "certificate_issued"

**Steps:**
1. Log in as Student
2. Navigate to **Clearance → Course Clearance**
3. Locate a completed clearance request
4. Click **"Download Clearance Form"** button
5. Verify form displays correctly

**Expected Results:**
- ✅ Official TTTI header with logo appears
- ✅ Form reference "TTTI/ADM/CLEAR/F1" is visible
- ✅ Student info bar populated (name, admission no, ID, phone, email)
- ✅ Department and Course names displayed
- ✅ Subject/Trainer Clearance section (15 rows) present
- ✅ HOD sign-off section present
- ✅ Academic Departments table (10 departments) present
- ✅ Other Sections table (5 sections) present
- ✅ Finance Office Clearance section present
- ✅ Print button works
- ✅ Back button returns to clearance dashboard

**Data Field Verification:**
- [ ] Student Name: `{{ student.full_name }}`
- [ ] Admission Number: `{{ student.admission_no }}`
- [ ] National ID: `{{ student.national_id }}` (may show placeholder)
- [ ] Phone Number: `{{ student.mobile_number }}`
- [ ] Email: `{{ student.email }}`
- [ ] Department: `{{ clearance_request.departments.name }}`
- [ ] Course: `{{ clearance_request.courses.name }}`

**Issues to Check:**
- All 10 academic departments listed correctly
- All 5 other sections listed correctly
- Empty rows for manual filling are present
- No 500 errors on missing data

---

### Test 1.3: Departmental Checklist

**Objective:** Verify the Departmental Checklist renders correctly and matches the physical document.

**Prerequisites:**
- Student account with admission request
- Admission request approved by HOD

**Steps:**
1. Log in as Student
2. Navigate to **Admission → Admission Documents**
3. Locate an approved admission request
4. Click **"Download Departmental Checklist"** button
5. Verify form displays correctly

**Expected Results:**
- ✅ Official TTTI header with logo appears
- ✅ Intake label displays (e.g., "MAY 2026 INTAKE")
- ✅ All 12 checklist items present
- ✅ Tick boxes show checkmarks for uploaded documents
- ✅ Departmental Registering Officer signature section present
- ✅ Departmental stamp area present
- ✅ Student info footer populated
- ✅ Print button works
- ✅ Back button returns to admission dashboard

**Data Field Verification:**
- [ ] Intake Label: Generated from `admission_request.reviewed_at` or `submitted_at`
- [ ] Student Name: `{{ admission_request.user_profiles.full_name }}`
- [ ] Admission Number: `{{ admission_request.user_profiles.admission_no }}`
- [ ] Course: `{{ admission_request.courses.name }} ({{ admission_request.courses.code }})`
- [ ] Department: `{{ admission_request.departments.name }}`

**Checklist Items Verification:**
- [ ] Item 1: Two colored passport photos (tick if uploaded)
- [ ] Item 2: Admission Letter (Form A)
- [ ] Item 3: Medical Examination form (Form B)
- [ ] Item 4: Personal Data Form (Form C)
- [ ] Item 5: Declaration form (Form D)
- [ ] Item 6: KCSE Result slip (tick if uploaded)
- [ ] Item 7: KCSE Leaving certificate
- [ ] Item 8: KCPE Result slip
- [ ] Item 9: Birth Certificate (tick if uploaded)
- [ ] Item 10: National Identity Card (tick if uploaded)
- [ ] Item 11: Guardian copies of ID
- [ ] Item 12: Consent form

**Issues to Check:**
- Uploaded documents show checkmarks (✓)
- Missing documents show empty tick boxes
- No 500 errors on missing data

---

## Test Suite 2: Navigation & Submenus

### Test 2.1: Student Portal Navigation

**Objective:** Verify all student portal submenus work without errors.

**Steps:**
1. Log in as Student
2. Test each submenu:

**Admission Submenu:**
- [ ] Click **Admission → Admission Documents**
- [ ] Verify page loads without errors
- [ ] Check "Initiate Admission" button works
- [ ] Check "Upload Document" functionality
- [ ] Check "Download Departmental Checklist" button (if approved)

**Clearance Submenu:**
- [ ] Click **Clearance → Course Clearance**
- [ ] Verify page loads without errors
- [ ] Check "Initiate Clearance" button works
- [ ] Check clearance status display
- [ ] Check "Download Clearance Form" button (if completed)

**Exams Submenu:**
- [ ] Click **Exams → Exam Bookings**
- [ ] Verify page loads without errors
- [ ] Check "New Exam Booking" button works
- [ ] Check booking list displays correctly
- [ ] Check "Download Form" button (if approved)

**Assessments Submenu:**
- [ ] Click **Assessments → My Assessments**
- [ ] Verify page loads without errors
- [ ] Check "Upload Assessment" button works
- [ ] Check assessment list displays correctly

**Attendance Submenu:**
- [ ] Click **Attendance → My Attendance**
- [ ] Verify page loads without errors
- [ ] Check attendance records display correctly
- [ ] Check attendance percentage calculation

**Profile Submenu:**
- [ ] Click **Profile → My Profile**
- [ ] Verify page loads without errors
- [ ] Check profile update functionality
- [ ] Check password change functionality

---

### Test 2.2: Department Admin Portal Navigation

**Objective:** Verify all dept admin portal submenus work without errors.

**Steps:**
1. Log in as Department Admin (HOD)
2. Test each submenu:

**Admissions Submenu:**
- [ ] Click **Admissions → Admission Requests**
- [ ] Verify page loads without errors
- [ ] Check pending/approved/rejected tabs work
- [ ] Check "Review Request" button works
- [ ] Check document verification functionality
- [ ] Check approve/reject buttons work

**Examinations Submenu:**
- [ ] Click **Examinations → Exam Booking Approvals**
- [ ] Verify page loads without errors
- [ ] Check pending/approved/rejected tabs work
- [ ] Check "Review Booking" button works
- [ ] Check approve/reject buttons work

**Classes Submenu:**
- [ ] Click **Classes → Manage Classes**
- [ ] Verify page loads without errors
- [ ] Check "Add Class" functionality
- [ ] Check "Edit Class" functionality
- [ ] Check "Delete Class" functionality

**Units Submenu:**
- [ ] Click **Units → Manage Units**
- [ ] Verify page loads without errors
- [ ] Check "Add Unit" functionality
- [ ] Check "Edit Unit" functionality
- [ ] Check "Delete Unit" functionality

**Trainers Submenu:**
- [ ] Click **Trainers → Manage Trainers**
- [ ] Verify page loads without errors
- [ ] Check "Add Trainer" functionality
- [ ] Check trainer list displays correctly

**Students Submenu:**
- [ ] Click **Students → Manage Students**
- [ ] Verify page loads without errors
- [ ] Check "Add Student" functionality
- [ ] Check student list displays correctly

---

### Test 2.3: Examination Officer Portal Navigation

**Objective:** Verify all examination officer portal submenus work without errors.

**Steps:**
1. Log in as Examination Officer
2. Test each submenu:

**Approved Bookings Submenu:**
- [ ] Click **Examinations → Approved Bookings**
- [ ] Verify page loads without errors
- [ ] Check filter functionality (admission no, class, name, year)
- [ ] Check booking list displays correctly
- [ ] Check "Confirm Booking" button works
- [ ] Check "View Details" button works

**Marks Report Submenu:**
- [ ] Click **Examinations → Marks Report**
- [ ] Verify page loads without errors
- [ ] Check filter functionality (year, term, class, unit)
- [ ] Check marks list displays correctly
- [ ] Check "Download PDF" button works

---

## Test Suite 3: End-to-End Workflows

### Test 3.1: Student Admission Workflow

**Objective:** Test complete admission workflow from initiation to document download.

**Steps:**
1. **Student Initiates Admission:**
   - [ ] Log in as Student
   - [ ] Navigate to **Admission → Admission Documents**
   - [ ] Click **"Initiate Admission"**
   - [ ] Select course from dropdown
   - [ ] Click **"Submit"**
   - [ ] Verify admission request created

2. **Student Uploads Documents:**
   - [ ] Click **"Upload Document"** for each required document type
   - [ ] Upload files (birth certificate, national ID, KCSE certificate, etc.)
   - [ ] Verify documents appear in uploaded list
   - [ ] Verify missing documents list updates

3. **Student Submits for Review:**
   - [ ] Click **"Submit for HOD Review"** (after all documents uploaded)
   - [ ] Verify status changes to "pending"
   - [ ] Verify notification sent to HOD

4. **HOD Reviews Admission:**
   - [ ] Log in as Department Admin (HOD)
   - [ ] Navigate to **Admissions → Admission Requests**
   - [ ] Click **"Review"** on pending request
   - [ ] Verify all documents display correctly
   - [ ] Click **"Verify"** on each document
   - [ ] Add comments (optional)
   - [ ] Click **"Approve Admission"**
   - [ ] Verify status changes to "approved"
   - [ ] Verify notification sent to student

5. **Student Downloads Forms:**
   - [ ] Log in as Student
   - [ ] Navigate to **Admission → Admission Documents**
   - [ ] Click **"Download Approval Form"**
   - [ ] Verify approval form displays correctly
   - [ ] Click **"Download Departmental Checklist"**
   - [ ] Verify checklist displays correctly with ticked items
   - [ ] Verify both forms are printable

**Expected Results:**
- ✅ Complete workflow executes without errors
- ✅ Status transitions correctly (pending → approved)
- ✅ Notifications sent at each stage
- ✅ Documents uploaded successfully
- ✅ HOD can verify documents
- ✅ Student can download both forms
- ✅ Forms display correct data

---

### Test 3.2: Exam Booking Workflow

**Objective:** Test complete exam booking workflow from creation to form download.

**Steps:**
1. **Student Creates Exam Booking:**
   - [ ] Log in as Student
   - [ ] Navigate to **Exams → Exam Bookings**
   - [ ] Click **"New Exam Booking"**
   - [ ] Select unit from dropdown
   - [ ] Enter exam date
   - [ ] Select exam session (morning/afternoon/evening)
   - [ ] Enter exam venue
   - [ ] Enter purpose
   - [ ] Click **"Submit Booking"**
   - [ ] Verify booking created with status "pending"

2. **HOD Approves Booking:**
   - [ ] Log in as Department Admin (HOD)
   - [ ] Navigate to **Examinations → Exam Booking Approvals**
   - [ ] Click **"Review"** on pending booking
   - [ ] Verify booking details display correctly
   - [ ] Add comments (optional)
   - [ ] Click **"Approve Booking"**
   - [ ] Verify status changes to "approved"
   - [ ] Verify notification sent to student

3. **Examination Officer Confirms Booking:**
   - [ ] Log in as Examination Officer
   - [ ] Navigate to **Examinations → Approved Bookings**
   - [ ] Locate approved booking
   - [ ] Click **"Confirm Booking"**
   - [ ] Verify status changes to "completed"
   - [ ] Verify notification sent to student

4. **Student Downloads Form:**
   - [ ] Log in as Student
   - [ ] Navigate to **Exams → Exam Bookings**
   - [ ] Click **"Download Form"** on approved booking
   - [ ] Verify Assessment Registration Form 1A displays correctly
   - [ ] Verify all sections populated with correct data
   - [ ] Verify form is printable

**Expected Results:**
- ✅ Complete workflow executes without errors
- ✅ Status transitions correctly (pending → approved → completed)
- ✅ Notifications sent at each stage
- ✅ HOD can approve bookings
- ✅ Examination Officer can confirm bookings
- ✅ Student can download form
- ✅ Form displays correct data

---

### Test 3.3: Clearance Workflow

**Objective:** Test complete clearance workflow from initiation to certificate issuance.

**Steps:**
1. **Student Initiates Clearance:**
   - [ ] Log in as Student
   - [ ] Navigate to **Clearance → Course Clearance**
   - [ ] Click **"Initiate Clearance"**
   - [ ] Select course from dropdown
   - [ ] Click **"Submit"**
   - [ ] Verify clearance request created with status "in_progress"

2. **Multi-Stage Approvals:**
   - [ ] Log in as Department Approver (role: dept_admin)
   - [ ] Navigate to **Clearance → Approver Dashboard**
   - [ ] Locate pending clearance approval
   - [ ] Add comments (optional)
   - [ ] Click **"Approve"**
   - [ ] Verify approval recorded
   - [ ] Repeat for Institutional Approver (role: registrar)
   - [ ] Repeat for Central Approver (role: deputy_principal)

3. **Certificate Issuance:**
   - [ ] Log in as Registrar or Deputy Principal
   - [ ] Navigate to completed clearance request
   - [ ] Click **"Issue Certificate"**
   - [ ] Verify certificate_issued flag set to true
   - [ ] Verify notification sent to student

4. **Student Downloads Form:**
   - [ ] Log in as Student
   - [ ] Navigate to **Clearance → Course Clearance**
   - [ ] Click **"Download Clearance Form"**
   - [ ] Verify Student Clearance Form displays correctly
   - [ ] Verify all sections present
   - [ ] Verify form is printable

**Expected Results:**
- ✅ Complete workflow executes without errors
- ✅ Status transitions correctly (in_progress → completed → certificate_issued)
- ✅ Multi-stage approvals work correctly
- ✅ Notifications sent at each stage
- ✅ Certificate issuance works
- ✅ Student can download form
- ✅ Form displays correct data

---

## Test Suite 4: Database Field Verification

### Test 4.1: User Profiles Table

**Objective:** Verify all required fields exist in user_profiles table.

**SQL Query:**
```sql
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'user_profiles'
ORDER BY ordinal_position;
```

**Required Fields:**
- [ ] `id` (uuid, NOT NULL)
- [ ] `email` (text)
- [ ] `full_name` (text, NOT NULL)
- [ ] `admission_no` (text)
- [ ] `role` (text, NOT NULL)
- [ ] `department_id` (uuid)
- [ ] `password_hash` (text)
- [ ] `mobile_number` (text)
- [ ] `gender` (text) - **CHECK IF EXISTS**
- [ ] `date_of_birth` (date) - **CHECK IF EXISTS**
- [ ] `national_id` (text) - **CHECK IF EXISTS**
- [ ] `is_active` (boolean)
- [ ] `created_at` (timestamp)
- [ ] `updated_at` (timestamp)

**Action Required:**
If missing fields found, add them:
```sql
-- Add gender field
ALTER TABLE user_profiles ADD COLUMN gender TEXT;

-- Add date_of_birth field
ALTER TABLE user_profiles ADD COLUMN date_of_birth DATE;

-- Add national_id field
ALTER TABLE user_profiles ADD COLUMN national_id TEXT;
```

---

### Test 4.2: Foreign Key Relationships

**Objective:** Verify all foreign key relationships work correctly.

**Test Queries:**
```sql
-- Test exam_bookings → user_profiles (student_id)
SELECT eb.id, eb.student_id, up.full_name
FROM exam_bookings eb
LEFT JOIN user_profiles up ON eb.student_id = up.id
LIMIT 5;

-- Test exam_bookings → user_profiles (approved_by)
SELECT eb.id, eb.approved_by, up.full_name
FROM exam_bookings eb
LEFT JOIN user_profiles up ON eb.approved_by = up.id
WHERE eb.approved_by IS NOT NULL
LIMIT 5;

-- Test exam_bookings → units
SELECT eb.id, eb.unit_id, u.name, u.code
FROM exam_bookings eb
LEFT JOIN units u ON eb.unit_id = u.id
LIMIT 5;

-- Test clearance_requests → user_profiles
SELECT cr.id, cr.student_id, up.full_name
FROM clearance_requests cr
LEFT JOIN user_profiles up ON cr.student_id = up.id
LIMIT 5;

-- Test clearance_requests → courses
SELECT cr.id, cr.course_id, c.name, c.code
FROM clearance_requests cr
LEFT JOIN courses c ON cr.course_id = c.id
LIMIT 5;

-- Test clearance_requests → departments
SELECT cr.id, cr.department_id, d.name
FROM clearance_requests cr
LEFT JOIN departments d ON cr.department_id = d.id
LIMIT 5;

-- Test admission_requests → user_profiles
SELECT ar.id, ar.student_id, up.full_name
FROM admission_requests ar
LEFT JOIN user_profiles up ON ar.student_id = up.id
LIMIT 5;

-- Test admission_requests → courses
SELECT ar.id, ar.course_id, c.name, c.code
FROM admission_requests ar
LEFT JOIN courses c ON ar.course_id = c.id
LIMIT 5;

-- Test admission_requests → departments
SELECT ar.id, ar.department_id, d.name
FROM admission_requests ar
LEFT JOIN departments d ON ar.department_id = d.id
LIMIT 5;
```

**Expected Results:**
- ✅ All joins return data without errors
- ✅ No NULL values in required foreign key fields
- ✅ All relationships resolve correctly

---

## Test Suite 5: Error Handling

### Test 5.1: Missing Data Handling

**Objective:** Verify system handles missing data gracefully without 500 errors.

**Test Cases:**
1. **Missing Gender/DOB in Exam Booking Form:**
   - [ ] Create exam booking for student without gender/date_of_birth
   - [ ] Download Assessment Registration Form 1A
   - [ ] Verify placeholders ("_______________") appear instead of errors

2. **Missing National ID in Clearance Form:**
   - [ ] Create clearance request for student without national_id
   - [ ] Download Student Clearance Form
   - [ ] Verify placeholder appears instead of error

3. **Missing Uploaded Documents in Checklist:**
   - [ ] Create admission request with partial documents
   - [ ] Download Departmental Checklist
   - [ ] Verify empty tick boxes appear for missing documents
   - [ ] Verify checkmarks appear for uploaded documents

**Expected Results:**
- ✅ No 500 errors on missing data
- ✅ Placeholders display correctly
- ✅ Forms remain printable

---

### Test 5.2: Permission Checks

**Objective:** Verify access control works correctly.

**Test Cases:**
1. **Student Access Control:**
   - [ ] Student can only view their own exam bookings
   - [ ] Student can only view their own clearance requests
   - [ ] Student can only view their own admission requests
   - [ ] Student cannot access other students' documents

2. **HOD Access Control:**
   - [ ] HOD can only approve bookings in their department
   - [ ] HOD can only approve admissions in their department
   - [ ] HOD cannot access other departments' data

3. **Examination Officer Access Control:**
   - [ ] Examination Officer can view all approved bookings
   - [ ] Examination Officer can confirm bookings
   - [ ] Examination Officer cannot approve bookings (HOD only)

**Expected Results:**
- ✅ 403 Forbidden errors for unauthorized access
- ✅ Users can only access their authorized data
- ✅ Role-based permissions enforced correctly

---

## Test Suite 6: Print & PDF Functionality

### Test 6.1: Print Dialog

**Objective:** Verify print button opens browser print dialog correctly.

**Test Cases:**
1. **Assessment Registration Form 1A:**
   - [ ] Click "Print / Save PDF" button
   - [ ] Verify browser print dialog opens
   - [ ] Verify form displays correctly in print preview
   - [ ] Verify print/back buttons hidden in print view

2. **Student Clearance Form:**
   - [ ] Click "Print / Save PDF" button
   - [ ] Verify browser print dialog opens
   - [ ] Verify form displays correctly in print preview
   - [ ] Verify print/back buttons hidden in print view

3. **Departmental Checklist:**
   - [ ] Click "Print / Save PDF" button
   - [ ] Verify browser print dialog opens
   - [ ] Verify form displays correctly in print preview
   - [ ] Verify print/back buttons hidden in print view

**Expected Results:**
- ✅ Print dialog opens correctly
- ✅ Forms display correctly in print preview
- ✅ UI buttons hidden in print view
- ✅ Forms fit on standard A4 paper

---

### Test 6.2: PDF Generation

**Objective:** Verify forms can be saved as PDF.

**Test Cases:**
1. **Save as PDF:**
   - [ ] Open each form
   - [ ] Click "Print / Save PDF"
   - [ ] Select "Save as PDF" in print dialog
   - [ ] Save PDF to local machine
   - [ ] Open saved PDF
   - [ ] Verify PDF displays correctly
   - [ ] Verify all data visible in PDF

**Expected Results:**
- ✅ PDF saves successfully
- ✅ PDF opens without errors
- ✅ All form data visible in PDF
- ✅ PDF formatting matches screen display

---

## Test Suite 7: TSMS Portal Information

### Test 7.1: Landing Page

**Objective:** Verify TSMS portal information displays on landing page.

**Steps:**
1. Navigate to `/` (landing page)
2. Verify hero section displays TSMS information
3. Check for portal descriptions:
   - [ ] Trainee Portal
   - [ ] Institute Dashboard
   - [ ] Employer Portal
   - [ ] Digital Portfolio
   - [ ] Media Evidence
   - [ ] GIS Map

**Expected Results:**
- ✅ TSMS information visible on landing page
- ✅ Portal descriptions clear and accurate
- ✅ Links to portals work correctly

---

### Test 7.2: Login Page

**Objective:** Verify login page displays portal information.

**Steps:**
1. Navigate to `/auth/login`
2. Verify dual login system explained
3. Check for:
   - [ ] Staff/Employer login (email + password)
   - [ ] Student login (admission number + password)
   - [ ] Portal access information

**Expected Results:**
- ✅ Dual login system clearly explained
- ✅ Portal access information visible
- ✅ Login forms work correctly

---

## Test Results Summary

### Overall Test Status

| Test Suite | Total Tests | Passed | Failed | Pending |
|------------|-------------|--------|--------|---------|
| Physical Document Templates | 3 | 0 | 0 | 3 |
| Navigation & Submenus | 18 | 0 | 0 | 18 |
| End-to-End Workflows | 3 | 0 | 0 | 3 |
| Database Field Verification | 2 | 0 | 0 | 2 |
| Error Handling | 2 | 0 | 0 | 2 |
| Print & PDF Functionality | 2 | 0 | 0 | 2 |
| TSMS Portal Information | 2 | 0 | 0 | 2 |
| **TOTAL** | **32** | **0** | **0** | **32** |

### Critical Issues Found

| Issue ID | Severity | Description | Status |
|----------|----------|-------------|--------|
| - | - | - | - |

### Recommendations

1. **Database Fields:**
   - Add missing fields to `user_profiles` table (gender, date_of_birth, national_id)
   - Update existing student records with missing data

2. **Testing Priority:**
   - Start with Physical Document Templates (Test Suite 1)
   - Then test Navigation & Submenus (Test Suite 2)
   - Finally test End-to-End Workflows (Test Suite 3)

3. **Documentation:**
   - Update user manual with new document templates
   - Create video tutorials for each workflow
   - Document common issues and solutions

---

## Conclusion

This testing guide provides comprehensive coverage of all system features, with special focus on the newly integrated physical document templates. Follow the test suites in order, document all issues found, and update the test results summary as you progress.

**Next Steps:**
1. Execute Test Suite 1 (Physical Document Templates)
2. Document any issues found
3. Fix critical issues before proceeding
4. Continue with remaining test suites
5. Update INTEGRATION_SUMMARY.md with final test results

**Testing Team:**
- System Administrator
- Department Admin (HOD)
- Examination Officer
- Student Representative
- Quality Assurance Officer

**Testing Timeline:**
- Day 1: Test Suites 1-2 (Templates & Navigation)
- Day 2: Test Suites 3-4 (Workflows & Database)
- Day 3: Test Suites 5-7 (Error Handling, Print, TSMS)
- Day 4: Bug fixes and retesting
- Day 5: Final verification and sign-off
