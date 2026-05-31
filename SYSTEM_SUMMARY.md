# TTTI Academic Management System - Complete System Summary

## System Overview

**System Name:** Thika Technical Training Institute Academic Management System (TTTI AMS)  
**Version:** 2.0  
**Status:** Production Ready  
**Last Updated:** May 31, 2026  

### System Motto
"Digitize the Journey. Verify the Competence. Celebrate the Graduate."

### Footer
"Verified Learning. Mapped Progress. Empowered Futures."

---

## Features

- **Attendance Management** - Track daily student attendance
- **Assessment & E-Portfolio** - Upload and review student assessments
- **Job Portal** - Employers post jobs, students apply
- **Employer Verifications** - Work experience verification for trainees
- **In-App Notifications** - Real-time notifications for all users
- **Audit Logging** - Complete system activity tracking

---

## Technology Stack

### Frontend
- Flask Jinja2 Templates
- HTML5
- Tailwind CSS (CDN)
- Alpine.js
- AJAX
- Leaflet.js (GIS Maps)
- Font Awesome 6.4.0 (Icons)

### Backend
- Python 3.11+
- Flask Blueprint Architecture
- REST APIs
- Service Layer Architecture

### Database
- PostgreSQL (via Supabase)
- Row-Level Security (RLS)
- UUID primary keys

### Authentication
- JWT Authentication (Staff/Employer)
- Password Hash (Students)
- RBAC (Role-Based Access Control)
- Session Management
- MFA Ready
- Password Reset System

### Storage
- Supabase Storage
- PDF, Image, Video, Audio Upload Support
- Assessment Scripts Bucket
- Assessment Evidence Bucket

### Deployment
- Docker
- Gunicorn
- Nginx
- Render (Cloud Platform)

---

## System Architecture

### File Structure
```
TTTI ACADEMIC MANAGEMENT SYSTEM/
├── app.py                          # Main Flask application entry point
├── db.py                           # Supabase client factory
├── auth_utils.py                   # Authentication helpers & RBAC decorators
├── notifications.py                # Notification system utilities
├── utils.py                        # Timezone utilities
├── requirements.txt                # Python dependencies
├── .env.example                    # Environment variables template
├── .env                            # Environment configuration
├── supabase_schema.sql            # Database schema
├── Procfile                        # Render deployment
├── render.yaml                     # Render configuration
├── runtime.txt                     # Python version
├── SYSTEM_SUMMARY.md               # This file
├── routes/                         # Blueprint modules
│   ├── __init__.py
│   ├── main.py                     # Public landing page
│   ├── auth.py                     # Authentication routes
│   ├── super_admin.py              # Super admin blueprint
│   ├── dept_admin.py               # Department admin blueprint
│   ├── trainer.py                  # Trainer blueprint
│   ├── student.py                  # Student blueprint
│   ├── employer.py                 # Employer blueprint
│   ├── examination_officer.py      # Examination officer blueprint
│   ├── industry_mentor.py          # Industry mentor blueprint
│   ├── internal_verifier.py        # Internal verifier blueprint
│   ├── clearance.py                # Clearance blueprint
│   ├── admission.py                # Admission blueprint
│   ├── admin_oversight.py          # Admin oversight blueprint
│   └── notifications.py            # Notification routes
├── templates/                      # Jinja2 templates
│   ├── main/                       # Public pages
│   ├── auth/                       # Authentication pages
│   ├── student/                    # Student portal
│   ├── trainer/                    # Trainer portal
│   ├── dept_admin/                 # Department admin portal
│   ├── super_admin/                # Super admin portal
│   ├── employer/                   # Employer portal
│   ├── examination_officer/        # Examination officer portal
│   ├── industry_mentor/            # Industry mentor portal
│   ├── internal_verifier/          # Internal verifier portal
│   ├── clearance/                  # Clearance portal
│   ├── admission/                  # Admission portal
│   ├── admin_oversight/            # Admin oversight portal
│   ├── clearance_approver/          # Clearance approver portal
│   ├── lecturer/                   # Lecturer portal
│   └── errors/                     # Error pages
├── static/                         # Static assets
│   ├── assets/                     # Images, logos
│   └── css/                        # Custom styles
└── assets/                         # Additional assets
```

---

## User Roles & Permissions

### 1. Trainee / Student
**Can:**
- Upload evidence & documents
- View attendance, results, clearance status
- Book exams
- View attachment progress
- Access personal dashboard
- Download official forms

**Cannot:**
- Approve records
- Edit marks
- View other students' data

### 2. Trainer
**Can:**
- Mark attendance
- Upload marks
- Approve/reject evidence
- Manage assigned units
- Monitor trainee progress

### 3. Department Office (HOD + Department Admin Combined)
**Can:**
- Assign units to trainers
- Manage department operations
- Verify documents
- Manage industrial attachment workflows
- Approve departmental clearance stages
- Generate departmental reports
- View analytics dashboards

### 4. Industry Supervisor / Mentor
**Can:**
- Mark trainee attendance during attachment
- Review logbooks
- Approve daily activities
- Grade trainees
- Assess competencies

### 5. Examination Officer
**Can:**
- View approved exam bookings
- Filter by admission number, class, trainee name, year, exam series
- Confirm exam bookings
- View marks (read-only)

### 6. Internal Verifier
**Can:**
- Verify competency assessments
- View industrial attachments
- Generate CDACC compliance reports

### 7. Employer
**Can:**
- Register company account
- Post job opportunities
- Review job applications
- Verify trainee work
- Submit recommendations

### 8. Super Admin
**Can:**
- Full system control
- Manage all users
- Configure system settings
- View all reports
- Manage departments, courses, units

### 9. Admin Oversight Roles
**Registrar, Deputy Principal, Quality Assurance Officer:**
- Read-only access to all departmental activities
- Cross-departmental statistics
- Admission and clearance oversight

---

## Database Schema

### Core Tables
- **user_profiles** - All users (students, staff, employers)
- **roles** - System roles
- **permissions** - Role permissions
- **departments** - Academic departments
- **programs** - Academic programs
- **courses** - Course offerings
- **classes** - Class groups with intake year/month
- **units** - Units of competency
- **unit_allocations** - Unit assignments

### Academic Tables
- **attendance** - Daily attendance records
- **assessments** - Assessment script uploads
- **assessment_uploads** - Assessment evidence
- **competency_tracking** - Competency assessments
- **marks** - Formative assessment marks
- **enrollments** - Student-class relationships

### Clearance Tables
- **clearance_requests** - Student clearance requests
- **clearance_approvals** - Multi-stage approval records
- **clearance_stages** - Approval stage definitions
- **clearance_departments** - Department/section definitions

### Admission Tables
- **admission_requests** - Student admission requests
- **admission_documents** - Uploaded admission documents

### Industrial Attachment Tables
- **industrial_attachments** - Student placements
- **companies** - Industry partner companies
- **industry_supervisors** - Industry supervisors
- **mentors** - Industry mentors
- **digital_logbook** - Daily work logs
- **location_logs** - GPS check-in/check-out records

### Job Portal Tables
- **employers** - Employer company profiles
- **job_postings** - Job opportunities
- **job_applications** - Student applications
- **employer_verifications** - Employer recommendations

### System Tables
- **system_logs** - Audit trail
- **notifications** - User notifications
- **course_applications** - Public course applications
- **system_settings** - System configuration

---

## Key System Modules

### 1. Authentication & Registration
**Features:**
- Dual login system (Staff: Email/Password, Students: Admission Number/Password)
- JWT token refresh for staff
- Password hash for students
- RBAC enforcement
- Session management
- Password reset (staff)
- Profile management

**Rules:**
- Registration ONLY if full_name matches master record AND admission_number matches master record
- Block duplicate accounts, fake admission numbers, unauthorized registration

### 2. Admission Module
**Workflow:**
1. Student initiates admission request for a course
2. Student uploads 9 required documents
3. Student submits for HOD review
4. HOD verifies each document individually
5. HOD approves/rejects with comments
6. Student downloads Departmental Admission Approval Form and Departmental Checklist

**Required Documents:**
- Passport Photos
- Admission Letter
- Medical Form
- Personal Data Form
- Declaration Form
- KCSE Result Slip
- KCSE Certificate
- KCPE Result Slip
- Birth Certificate
- National ID
- Guardian ID
- Consent Form

**Document Status:** Uploaded, Pending Verification, Verified, Rejected, Resubmit Required

### 3. My Documents Module
**Features:**
- Centralized digital document system
- Upload once, reuse everywhere
- Support: PDF, Images, Videos, Audio
- Document preview
- Verification tracking
- Version history

### 4. Student Dashboard
**Displays:**
- Attendance percentage
- Assessment status (approved/pending/rejected)
- Competency status
- Clearance status
- Exam eligibility
- Industrial attachment status (with GIS map)
- Recent logbook entries
- Recent notifications
- Recent uploads
- Calendar
- Quick actions
- Progress bars

### 5. Attendance Module
**Features:**
- Trainers mark attendance
- System calculates attendance percentage
- Generates defaulter lists
- Blocks exam booking below threshold
- Attendance affects competency status

### 6. Assessment Module
**Supports:**
- Theory assessments
- Practical assessments
- Oral assessments
- Formative assessments
- Summative assessments
- Marks: 0–100%

### 7. Portfolio of Evidence (PoE)
**Each evidence includes:**
- Date
- Task title
- Description
- Skills used
- Equipment used
- Hours worked
- Trainer feedback
- Supporting files (Photos, Videos, Audio, PDFs, Documents)

**Workflow:**
Upload → Review → Approve/Reject → Competency Update

### 8. Competency Tracking
**Statuses:**
- Not Started
- In Progress
- Competent
- Not Yet Competent

**Outputs:**
- Competency reports
- Progress analytics
- Student readiness indicators

### 9. Industrial Attachment Module
**Features:**
- Company registration
- Supervisor assignment
- Student placement tracking
- Daily logbooks
- Evidence submission
- Attendance tracking
- Performance grading
- GIS location mapping
- Company location visualization

### 10. GIS Features
**Displays:**
- Attachment locations
- Companies
- Student locations
- Cluster markers
- Filters
- Map search
- Open in Maps integration

### 11. Digital Logbook
**Workflow:**
Task Creation → Evidence Upload → Supervisor Review → Approval → Progress Update

**Includes:**
- Daily activity tracking
- Supervisor comments
- Skill validation

### 12. Clearance Module
**Final Clearance Workflow:**
1. Trainer Clearance
2. Department Office Clearance (HOD/Admin Combined)
3. Library Clearance
4. Store Clearance
5. Games Clearance
6. Finance Clearance (MUST BE BEFORE FINAL APPROVAL)
7. Deputy Principal / Principal Final Approval (FINAL STEP)
8. Certificate Unlock

**Features:**
- Digital signatures
- Approval timestamps
- Digital stamps
- Remarks section
- Lost item tracking
- Fee validation lock

### 13. Lost Items Module
**Tracks:**
- Item name
- Department
- Cost
- Payment status

**Calculates:**
- Total loss per student
- Outstanding balances

### 14. Finance Integration
**External finance system via API only:**
- Fee verification
- Balance checking
- Clearance validation

### 15. Results Module
**Students:** View only  
**Trainers:** Upload marks

**Outputs:**
- Transcripts
- Competency reports
- PDF result sheets

### 16. Notifications
**Supports:**
- Email
- SMS-ready
- In-app notifications

**Triggers:**
- Approvals
- Rejections
- Attendance warnings
- Exam booking alerts
- Clearance updates
- Attachment updates

### 17. Audit Logging
**Tracks:**
- User
- Action
- Timestamp
- Old vs new values
- IP address

### 18. Reporting Module
**Generates:**
- Attendance reports
- Assessment reports
- Competency reports
- Department reports
- Attachment reports
- Graduation reports

**Export Formats:**
- PDF
- Excel
- CSV

**Required Downloads:**
1. Industrial Attachment Report (All students in attachment with company details, location, supervisor details, duration, status)
2. Department Attachment Register (Full list of trainees in attachment with placement history, performance summaries)

### 19. PDF Generation
**Generates:**
- Admission forms
- Clearance forms
- Reports
- Transcripts

**Requirements:**
- Multi-page PDFs
- QR verification
- Digital signatures
- Embedded documents
- Institution logo
- **Unique Serial Numbers:** TTTI/{YEAR}/{MODULE}/{SEQUENCE}

**Serial Number Format:**
- TTTI/2026/ADMISSION/00001
- TTTI/2026/CLEARANCE/00045
- TTTI/2026/ATTACHMENT/00102
- TTTI/2026/REPORT/00078
- TTTI/2026/RESULTS/00033

**Module Codes:**
- ADMISSION → Admission documents
- CLEARANCE → Clearance forms
- ATTACHMENT → Industrial attachment reports
- REPORT → Academic/department reports
- RESULTS → Student transcripts/results
- DOCUMENT → General uploaded documents

---

## Official Document Templates

### 1. Assessment Registration Form 1A
**Reference:** TTTI/EXAMS/CDACC/REG/1A  
**Purpose:** Regular Candidate Assessment Registration for exam booking  
**Template:** `templates/student/exam_booking_form.html`  
**Route:** `GET /student/exam-bookings/<id>/download`

**Sections:**
- Candidate Details (name, admission no, gender, DOB, contact info)
- Examination Details (date, session, venue, class, department)
- Departmental Clearance (HOD approval)
- Units of Competency table
- Required Attachments list
- Signature blocks (Student, HOD, Examination Officer)

### 2. Student Clearance Form
**Reference:** TTTI/ADM/CLEAR/F1  
**Purpose:** Multi-section clearance for course completion and certificate issuance  
**Template:** `templates/clearance/clearance_form_pdf.html`  
**Route:** `GET /clearance/clearance-form/<request_id>`

**Sections:**
- Student information bar
- Subject/Trainer Clearance (15 rows)
- HOD sign-off section
- Academic Departments table (10 departments)
- Other Sections table (5 sections)
- Finance Office Clearance

### 3. Departmental Checklist
**Purpose:** 12-item admission document checklist for new student intake  
**Template:** `templates/admission/departmental_checklist.html`  
**Route:** `GET /admission/departmental-checklist/<request_id>`

**Checklist Items:**
1. Two colored passport photos
2. Admission Letter
3. Medical Examination form
4. Personal Data Form
5. Declaration form
6. KCSE Result slip
7. KCSE Leaving certificate
8. KCPE Result slip
9. Birth Certificate
10. National Identity Card
11. Guardian copies of ID
12. Consent form

---

## API Structure

### Authentication
- `/api/auth/login` - User login
- `/api/auth/logout` - User logout
- `/api/auth/refresh` - JWT token refresh
- `/api/auth/forgot-password` - Password reset

### Students
- `/api/students/profile` - Student profile
- `/api/students/attendance` - Attendance records
- `/api/students/assessments` - Assessment uploads
- `/api/students/evidence` - Evidence uploads
- `/api/students/attachments` - Industrial attachment
- `/api/students/clearance` - Clearance status
- `/api/students/documents` - Document management

### Trainers
- `/api/trainers/dashboard` - Trainer dashboard
- `/api/trainers/attendance` - Mark attendance
- `/api/trainers/assessments` - Review assessments
- `/api/trainers/units` - Assigned units

### Department Admin
- `/api/dept-admin/dashboard` - Department dashboard
- `/api/dept-admin/students` - Student management
- `/api/dept-admin/trainers` - Trainer management
- `/api/dept-admin/units` - Unit management
- `/api/dept-admin/admissions` - Admission approvals
- `/api/dept-admin/exams` - Exam approvals

### Super Admin
- `/api/admin/dashboard` - System dashboard
- `/api/admin/users` - User management
- `/api/admin/departments` - Department management
- `/api/admin/courses` - Course management
- `/api/admin/settings` - System settings
- `/api/admin/reports` - System reports

### Other Roles
- `/api/employer/*` - Employer portal
- `/api/examination-officer/*` - Examination officer
- `/api/industry-mentor/*` - Industry mentor
- `/api/internal-verifier/*` - Internal verifier
- `/api/clearance/*` - Clearance workflows
- `/api/admission/*` - Admission workflows
- `/api/reports/*` - Reporting

---

## Security Features

- CSRF Protection
- Rate Limiting
- Password Hashing (bcrypt)
- Secure File Uploads
- Input Validation
- SQL Injection Prevention (via Supabase client)
- RBAC Enforcement (Python decorators)
- Row-Level Security (RLS) in PostgreSQL
- Department Isolation
- Audit Logging
- JWT Token Management
- Session Security

---

## Responsive Design

All portals are fully responsive and work on:
- Desktop (1920px+)
- Laptop (1366px - 1920px)
- Tablet (768px - 1366px)
- Mobile (320px - 768px)

---

## Setup Instructions

### Prerequisites
- Python 3.11+
- Supabase project
- Git

### Local Development

```bash
# Clone repository
git clone <repo-url>
cd <repo>

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Run application
python app.py
```

### Database Setup

1. Run `supabase_schema.sql` in Supabase SQL Editor
2. Create storage buckets in Supabase Storage (set to PUBLIC):
   - `assessment-scripts`
   - `assessment-evidence`
3. Create super admin user via Supabase Auth
4. Add user_profiles row for super admin

### Create Super Admin

```sql
INSERT INTO user_profiles (id, email, full_name, role, is_active)
VALUES (
    'YOUR-UUID-FROM-SUPABASE-AUTH',
    'admin@yourdomain.com',
    'Super Administrator',
    'super_admin',
    TRUE
);
```

### Deployment (Render)

1. Push to GitHub
2. Connect repo on render.com
3. Set environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `SECRET_KEY`

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session secret key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `INSTITUTION_NAME` | Institution display name (optional) |
| `FLASK_ENV` | `development` or `production` |

---

## Support & Contact

For technical support or questions:
- Email: support@ttti.ac.ke
- Phone: +254 700 000 000
- Visit: Thika Technical Training Institute, P.O. Box 474-01000, Thika

---

## Version History

**Version 2.0** (May 31, 2026)
- Consolidated all documentation into single SYSTEM_SUMMARY.md
- Removed redundant markdown files
- System is production-ready with all modules integrated

**Version 1.0** (May 29, 2026)
- Initial unified system release
- Physical document templates integrated
- All 11 dashboards enhanced with modern Tailwind CSS
- Industrial attachment module with GIS tracking
- Complete clearance workflow
- Admission document management

---

**Developed by:** TTTI ICT Department  
**Maintained by:** TTTI IT Department  
**License:** Institutional Use Only
