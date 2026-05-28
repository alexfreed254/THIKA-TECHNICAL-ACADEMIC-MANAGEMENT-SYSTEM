# TTTI Physical Document Templates - Quick Reference Guide

## Overview

This guide provides quick reference information for the three official TTTI physical document templates that have been digitized and integrated into the Academic Management System.

**Integration Date:** May 29, 2026
**System Version:** Unified Academic Management System v2.0

---

## Document 1: Assessment Registration Form 1A

### Basic Information
- **Official Reference:** TTTI/EXAMS/CDACC/REG/1A
- **Purpose:** Regular Candidate Assessment Registration for exam booking
- **Template File:** `templates/student/exam_booking_form.html`
- **Route:** `GET /student/exam-bookings/<id>/download`
- **Access:** Students (own bookings only)

### When to Use
- Student has created an exam booking
- HOD has approved the exam booking
- Student needs to present form at examination venue

### How to Access
1. Log in as Student
2. Navigate to **Exams → Exam Bookings**
3. Locate approved exam booking
4. Click **"Download Form"** button

### Form Sections

#### Section 1: Candidate Details
- Full Name (as per ID)
- Admission Number
- Gender
- Date of Birth
- Mobile Number
- Email Address
- National ID / Birth Certificate Number
- Course Code
- Course Name
- Module / Level / TEP
- PWD Status

#### Section 2: Examination Details
- Exam Date
- Exam Session (Morning/Afternoon/Evening)
- Exam Venue
- Class / Group
- Department
- Purpose

#### Section 3: Departmental Clearance
- Department Name
- HOD Name
- HOD Signature
- Date of Approval

#### Units of Competency Table
- S/N (Serial Number)
- Unit of Competency (Name and Code)
- Unit Type (Core/Common/Basic)
- Unit Cost
- Total Cost (Ksh)

#### Required Attachments
1. Copy of National ID / Passport
2. Copy of Birth Certificate
3. KCSE Certificate (for Module I) or Previous Module Result Slip
4. Fee Statement showing exam fee payment

#### Signature Blocks
- Student Signature & Date
- HOD Signature & Stamp
- Examination Officer Signature

### Data Sources
```python
# Main data object: booking
booking = {
    "id": "uuid",
    "student_id": "uuid",
    "unit_id": "uuid",
    "exam_date": "2026-06-15",
    "exam_session": "morning",
    "exam_venue": "Main Hall",
    "purpose": "Module II Assessment",
    "status": "approved",
    "approved_by": "uuid",
    "approved_at": "2026-05-29T10:30:00Z",
    "user_profiles": {
        "full_name": "John Doe",
        "admission_no": "TTTI/2024/001",
        "gender": "Male",
        "date_of_birth": "2000-01-15",
        "mobile_number": "+254712345678",
        "email": "john.doe@student.ttti.ac.ke",
        "classes": {
            "name": "ICT 1A",
            "departments": {
                "name": "ICT"
            }
        }
    },
    "units": {
        "code": "ICT101",
        "name": "Introduction to Computing"
    },
    "approved_by_user": {
        "full_name": "Dr. Jane Smith"
    }
}
```

### Print Settings
- **Paper Size:** A4
- **Orientation:** Portrait
- **Margins:** Default (20mm)
- **Print Button:** JavaScript `window.print()`

---

## Document 2: Student Clearance Form

### Basic Information
- **Official Reference:** TTTI/ADM/CLEAR/F1
- **Purpose:** Multi-section clearance for course completion and certificate issuance
- **Template File:** `templates/clearance/clearance_form_pdf.html`
- **Route:** `GET /clearance/clearance-form/<request_id>`
- **Access:** Students (own clearances only)

### When to Use
- Student has completed all course requirements
- Clearance request status is "completed" or "certificate_issued"
- Student needs to collect certificate

### How to Access
1. Log in as Student
2. Navigate to **Clearance → Course Clearance**
3. Locate completed clearance request
4. Click **"Download Clearance Form"** button

### Form Sections

#### Student Information Bar
- Student's Name
- Admission Number
- National ID Number
- Phone Number
- Email Address
- Department
- Course

#### Subject / Trainer Clearance Section
- 15 rows for subject/trainer clearance
- Columns: S/No, Subject/Trainer, Lost Item(s), Cost, Sign
- Additional rows for Technician (One) and Technician (Two)

#### HOD Sign-Off Section
- Student's Cleared / Not Cleared
- HOD's Name
- HOD Signature
- Official Stamp
- Date

#### Academic Departments Table
10 departments listed:
1. AGRIC & ENVIRONMENTAL STUDIES
2. APPLIED SCIENCES
3. BUILDING AND CIVIL ENG.
4. BUSINESS STUDIES
5. ELECTRICAL & ELECTRONICS ENG.
6. HEALTH SCIENCES
7. ICT
8. LIBERAL STUDIES
9. MOTOR VEHICLE
10. HOSPITALITY

Columns: S/No, Department, Lost Items, Cost, HOD Sign

#### Other Sections Table
5 sections listed:
1. INSTITUTE LIBRARY
2. KENYA NATIONAL LIBRARY
3. STORE
4. GAMES
5. DEAN OF STUDENTS

Columns: S/No, Department, Lost Items, Cost, HOD Sign

#### Finance Office Clearance Section
- Cost of Lost Books (Ksh)
- Cost of Lost Items (Ksh)
- Total Cost Payable for Lost Items (Ksh)
- Finance Balance if Any (Ksh)
- Finance Officer Signature
- Date

### Data Sources
```python
# Main data objects: clearance_request, student
clearance_request = {
    "id": "uuid",
    "student_id": "uuid",
    "course_id": "uuid",
    "department_id": "uuid",
    "status": "completed",
    "completed_at": "2026-05-29T15:00:00Z",
    "departments": {
        "name": "ICT"
    },
    "courses": {
        "name": "Diploma in Information Technology",
        "code": "DIT"
    }
}

student = {
    "id": "uuid",
    "full_name": "John Doe",
    "admission_no": "TTTI/2024/001",
    "national_id": "12345678",
    "mobile_number": "+254712345678",
    "email": "john.doe@student.ttti.ac.ke"
}
```

### Print Settings
- **Paper Size:** A4
- **Orientation:** Portrait
- **Margins:** Narrow (10mm)
- **Print Button:** JavaScript `window.print()`

---

## Document 3: Departmental Checklist

### Basic Information
- **Official Reference:** Departmental Checklist (Intake)
- **Purpose:** 12-item admission document checklist for new student intake
- **Template File:** `templates/admission/departmental_checklist.html`
- **Route:** `GET /admission/departmental-checklist/<request_id>`
- **Access:** Students (own admissions only), HOD (department admissions)

### When to Use
- Student has submitted admission request
- HOD has approved admission request
- Student needs to verify all required documents submitted

### How to Access
1. Log in as Student
2. Navigate to **Admission → Admission Documents**
3. Locate approved admission request
4. Click **"Download Departmental Checklist"** button

### Form Sections

#### Header
- Official TTTI Logo
- Institution Name
- Document Title: "Departmental Checklist"
- Intake Label (e.g., "MAY 2026 INTAKE")

#### Checklist Table
12 required documents with tick boxes:

| # | Document | Remarks (Tick) |
|---|----------|----------------|
| 1 | Two (2) colored passport photo (Attach to form C) | ☐ |
| 2 | Admission Letter (Form A) | ☐ |
| 3 | Medical Examination form (Form B) Duly filled and stamped | ☐ |
| 4 | Personal Data Form (Form C) Duly filled | ☐ |
| 5 | Declaration form (Form D) Duly filled and signed | ☐ |
| 6 | KCSE Result slip (check minimum requirement for the course applied) | ☐ |
| 7 | KCSE Leaving certificate | ☐ |
| 8 | KCPE Result slip | ☐ |
| 9 | Birth Certificate | ☐ |
| 10 | National Identity Card | ☐ |
| 11 | Guardian copies of ID (optional to be submitted to the department for exam booking) | ☐ |
| 12 | Duly filled and signed consent form | ☐ |

**Note:** Tick boxes (☐) automatically show checkmarks (✓) for uploaded documents.

#### Signature Section
- Checked by: Departmental Registering Officer
- Name (signature line)
- Sign (signature line)
- Date (signature line)
- Departmental Stamp (stamp area)

#### Student Information Footer
- Student Name
- Admission Number
- Course (Name and Code)
- Department

### Data Sources
```python
# Main data objects: admission_request, documents, uploaded_types
admission_request = {
    "id": "uuid",
    "student_id": "uuid",
    "course_id": "uuid",
    "department_id": "uuid",
    "status": "approved",
    "reviewed_at": "2026-05-29T12:00:00Z",
    "user_profiles": {
        "full_name": "John Doe",
        "admission_no": "TTTI/2024/001",
        "mobile_number": "+254712345678"
    },
    "courses": {
        "name": "Diploma in Information Technology",
        "code": "DIT"
    },
    "departments": {
        "name": "ICT"
    }
}

documents = [
    {"document_type": "passport_photo", ...},
    {"document_type": "kcse_certificate", ...},
    {"document_type": "birth_certificate", ...},
    {"document_type": "national_id", ...}
]

uploaded_types = {"passport_photo", "kcse_certificate", "birth_certificate", "national_id"}

# Intake label generated from reviewed_at or submitted_at
intake_label = "MAY 2026 INTAKE"
```

### Document Type Mapping
```python
# Maps checklist items to document_type in database
DOCUMENT_TYPE_MAPPING = {
    "passport_photo": "Two (2) colored passport photo",
    "kcse_certificate": "KCSE Result slip",
    "birth_certificate": "Birth Certificate",
    "national_id": "National Identity Card"
}
```

### Print Settings
- **Paper Size:** A4
- **Orientation:** Portrait
- **Margins:** Default (20mm)
- **Print Button:** JavaScript `window.print()`

---

## Common Issues & Solutions

### Issue 1: Missing Data Fields

**Problem:** Some fields show placeholders ("_______________") instead of actual data.

**Cause:** Database fields (gender, date_of_birth, national_id) may not exist or are empty.

**Solution:**
```sql
-- Add missing fields to user_profiles table
ALTER TABLE user_profiles ADD COLUMN gender TEXT;
ALTER TABLE user_profiles ADD COLUMN date_of_birth DATE;
ALTER TABLE user_profiles ADD COLUMN national_id TEXT;

-- Update existing records
UPDATE user_profiles SET gender = 'Male' WHERE id = 'student-uuid';
UPDATE user_profiles SET date_of_birth = '2000-01-15' WHERE id = 'student-uuid';
UPDATE user_profiles SET national_id = '12345678' WHERE id = 'student-uuid';
```

### Issue 2: Form Not Displaying

**Problem:** Clicking "Download Form" button shows 404 error.

**Cause:** Route not registered or booking/request not found.

**Solution:**
1. Verify route exists in blueprint
2. Check booking/request ID is valid
3. Verify user has permission to access document
4. Check application logs for errors

### Issue 3: Print Button Not Working

**Problem:** Clicking "Print / Save PDF" button does nothing.

**Cause:** JavaScript error or browser blocking print dialog.

**Solution:**
1. Check browser console for JavaScript errors
2. Verify `window.print()` is called correctly
3. Try different browser (Chrome, Firefox, Edge)
4. Check browser print settings

### Issue 4: Tick Boxes Not Showing Checkmarks

**Problem:** Departmental Checklist shows empty tick boxes for uploaded documents.

**Cause:** Document type mismatch or uploaded_types not passed correctly.

**Solution:**
1. Verify document_type in database matches template mapping
2. Check uploaded_types set is built correctly in route
3. Verify Jinja2 condition: `{% if doc_type in uploaded_types %}`

### Issue 5: Foreign Key Errors

**Problem:** Template shows "None" or empty values for related data.

**Cause:** Foreign key relationship not loaded or data missing.

**Solution:**
1. Verify `.select()` includes all required joins
2. Check foreign key fields are not NULL
3. Use `.get()` method with fallback values in template
4. Example: `{{ booking.user_profiles.get('full_name', 'N/A') }}`

---

## Developer Notes

### Template Structure

All three templates follow this structure:
```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Document Title — TTTI</title>
  <style>/* Inline CSS for print compatibility */</style>
</head>
<body>
  <a href="..." class="back-btn">Back</a>
  <button class="print-btn" onclick="window.print()">Print</button>
  
  <div class="page">
    <!-- Header with logo -->
    <!-- Form sections -->
    <!-- Footer -->
  </div>
</body>
</html>
```

### CSS Best Practices

1. **Inline Styles:** All CSS is inline for print compatibility
2. **Print Media Query:** Hide buttons in print view
3. **Font:** Times New Roman for official document look
4. **Colors:** Black text on white background for printing
5. **Borders:** 1px solid black for tables and sections

### Jinja2 Best Practices

1. **Safe Access:** Always use `.get()` method with fallback
   ```jinja2
   {{ booking.user_profiles.get('gender', '_______________') }}
   ```

2. **Loop Index:** Use `loop.index` instead of `enumerate()`
   ```jinja2
   {% for item in items %}
     {{ loop.index }}. {{ item }}
   {% endfor %}
   ```

3. **Conditional Display:** Check for data before displaying
   ```jinja2
   {% if booking.exam_date %}
     {{ booking.exam_date | to_eat('%d %B %Y') }}
   {% else %}
     _______________
   {% endif %}
   ```

4. **Date Formatting:** Use custom filter for timezone conversion
   ```jinja2
   {{ booking.approved_at | to_eat('%d %b %Y %H:%M') }}
   ```

### Route Best Practices

1. **Permission Checks:** Verify user has access to document
   ```python
   if user["role"] == "student" and booking["student_id"] != user["id"]:
       abort(403)
   ```

2. **Data Loading:** Load all required relationships in one query
   ```python
   booking = (db.table("exam_bookings")
              .select("*, units(name, code), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no)")
              .eq("id", booking_id)
              .single()
              .execute().data)
   ```

3. **Error Handling:** Handle missing data gracefully
   ```python
   if not booking:
       flash("Booking not found.", "error")
       return redirect(url_for("student.exam_bookings"))
   ```

---

## Testing Checklist

### Pre-Deployment Testing

- [ ] All three templates render without errors
- [ ] All data fields populate correctly
- [ ] Missing data shows placeholders (not errors)
- [ ] Print button opens print dialog
- [ ] Forms display correctly in print preview
- [ ] PDF generation works correctly
- [ ] Back button returns to correct page
- [ ] Permission checks work correctly
- [ ] Foreign key relationships load correctly
- [ ] Date formatting displays correctly (EAT timezone)

### User Acceptance Testing

- [ ] Students can access their own documents
- [ ] HOD can access department documents
- [ ] Examination Officer can access approved bookings
- [ ] Forms match physical document layouts
- [ ] All required information is visible
- [ ] Forms are printable on A4 paper
- [ ] PDFs are readable and complete

---

## Maintenance

### Regular Updates

1. **Logo Updates:** Replace `/static/assets/THIKATTILOGO.jpg` if logo changes
2. **Department List:** Update Academic Departments table if departments change
3. **Checklist Items:** Update Departmental Checklist if requirements change
4. **Form References:** Update official reference numbers if changed by institution

### Version Control

- Document any changes to templates in git commit messages
- Keep backup copies of original physical documents
- Test all changes in development environment before deploying
- Update this guide when templates are modified

---

## Support

For issues or questions about document templates:

1. **Check this guide first**
2. **Review TESTING_GUIDE.md for detailed test procedures**
3. **Check INTEGRATION_SUMMARY.md for system overview**
4. **Review application logs for errors**
5. **Contact system administrator**

---

## Appendix: Quick Command Reference

### View Template
```bash
# View template file
cat templates/student/exam_booking_form.html
cat templates/clearance/clearance_form_pdf.html
cat templates/admission/departmental_checklist.html
```

### Test Route
```bash
# Test route in browser
http://localhost:5000/student/exam-bookings/<id>/download
http://localhost:5000/clearance/clearance-form/<request_id>
http://localhost:5000/admission/departmental-checklist/<request_id>
```

### Check Database
```sql
-- Check exam bookings
SELECT * FROM exam_bookings WHERE status = 'approved' LIMIT 5;

-- Check clearance requests
SELECT * FROM clearance_requests WHERE status = 'completed' LIMIT 5;

-- Check admission requests
SELECT * FROM admission_requests WHERE status = 'approved' LIMIT 5;
```

### View Logs
```bash
# View application logs
tail -f logs/app.log

# View Supabase logs
# Check Supabase Dashboard → Logs
```

---

**Document Version:** 1.0
**Last Updated:** May 29, 2026
**Maintained By:** TTTI IT Department
