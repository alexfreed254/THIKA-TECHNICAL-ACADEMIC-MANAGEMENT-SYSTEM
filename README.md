# Thika Technical Training Institute — Academic Management System (TTTI AMS)

A full-stack web application for managing academic operations at Thika Technical Training Institute. Covers attendance, assessments, student clearance, industrial attachment, examinations, and institutional oversight across multiple departments and user roles.

---

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.14 · Flask · Gunicorn |
| Database | Supabase (PostgreSQL + Row Level Security) |
| Auth | Supabase Auth (JWT) for staff/employers · bcrypt hashed passwords for students |
| Storage | Supabase Storage (PDFs, images, evidence files) |
| Hosting | Render (Python web service, auto-deploy from GitHub) |
| Frontend | **React 18 + Vite** (SPA in `frontend/`) · Jinja2 portals still available during incremental migration · Tailwind CSS · Font Awesome |
| PDF generation | ReportLab |
| Excel export | openpyxl |
| AI assistant | Anthropic Claude API (student chat) |

---

## System Architecture

```
Browser
  │
  ├─ React + Vite SPA (`frontend/`) ── Axios ──► Flask /api/v1/*
  │
  └─ Legacy Jinja portals (unchanged) ─────────► Flask HTML routes
         │
         ▼
Render (Gunicorn → Flask app)
  │
  ├── Supabase Auth  ← login / JWT / password reset
  ├── Supabase DB    ← all application data (PostgreSQL + RLS)
  └── Supabase Storage ← uploaded files (PDFs, photos, documents)
```

All data lives in Supabase. Render hosts the Python API. The React frontend is deployed separately (static hosting) and talks to Flask over `/api/v1`. See `frontend/README.md`.

Jinja templates remain until each screen is ported — **design is preserved**, only the frontend language changes.

---

## User Roles (16 total)

| Role | URL Prefix | Description |
|---|---|---|
| `super_admin` | `/super-admin` | Full system access across all departments |
| `dept_admin` | `/dept-admin` | Department-scoped admin — classes, trainers, students, attendance |
| `trainer` | `/trainer` | Own assigned classes and units — attendance, assessments, marks, POE |
| `student` | `/student` | Own records — attendance, assessments, exams, attachment, AI assistant |
| `examination_officer` | `/examination-officer` | Approve and confirm exam bookings; read-only marks |
| `industry_mentor` | `/industry-mentor` | Company-side mentor — logbook approval, competency assessment |
| `internal_verifier` | `/internal-verifier` | CDACC competency verification, attachment compliance reports |
| `liaison_officer` | `/liaison-officer` | Industrial attachment approval and logbook oversight |
| `cdacc_verifier` | `/cdacc-verifier` | External CDACC body — verify assessments, marks, trainer POE, trainee POE |
| `workshop_technician` | `/workshop-technician` | Workshop inventory management and clearance |
| `registrar` | `/admin-oversight/registrar` | Read-only view of enrollments and clearances across all departments |
| `deputy_principal` | `/admin-oversight/deputy-principal` | Read-only academic and clearance overview |
| `quality_assurance_officer` | `/admin-oversight/quality-assurance` | Read-only reports; assessment approval rights |
| `service_dept` | `/service-dept` | Service department clearance approvals and lost-items register |
| `employer` | `/employer` (via student routes) | Post jobs, review applications, verify trainee work |
| Biometric scanner | `/biometric` | Fingerprint sensor API endpoint for classroom attendance |

Access control is enforced at two layers:
1. **Python decorators** — role check before any query runs
2. **Supabase RLS** — row-level policies on every table (department isolation at DB level)

---

## Module Breakdown

### Super Admin (`/super-admin`)
- Dashboard with system-wide statistics
- Departments, Classes, Units, Courses management (CRUD)
- User management — create/edit/delete users, assign roles and departments
- System-wide attendance viewer (all departments)
- Assessment viewer (all departments)
- Marks viewer with PDF export
- Exam bookings — approve / reject
- Clearance requests viewer (student and service)
- Industrial attachment viewer
- Digital logbook viewer
- GIS/location tracking (Excel and PDF export)
- Company registry
- Trainee documents verification
- Trainer POE viewer (all departments)
- Class lists and trainee search with PDF reports
- Assessment sheets and marks reports
- System notices — broadcast to all users or by role/department
- Audit log viewer
- Data import tool
- Biometric scanner registration

### Department Admin (`/dept-admin`)
- Dashboard with department statistics and pending tasks
- Classes and Units management for own department
- Trainer management — add, list, assign units
- Student management — enrol, list, export
- Attendance — view matrix, filter by week/lesson/unit, download PDF register
- Assessment management — view submitted assessments
- Exam bookings — approve / reject, export PDF, export Excel
- Marks entry viewer
- Trainer POE management (upload, view, filter by type/year/term)
- Trainee POE viewer
- Trainee documents verification
- Class lists and trainee search reports
- Industrial attachment management (approval, GIS tracking, export)
- Digital logbook reviewer
- Company management (add/edit/delete)
- Job applications reviewer
- Notices — send to department users
- Credentials viewer (student login credentials)
- Fingerprint enrolment — register student biometric IDs

### Trainer (`/trainer`)
- Dashboard with own class/unit stats and today's pending attendance
- Attendance marking — live session, select class/unit/week/lesson
- Attendance history — view past sessions, correct records
- Weekly attendance export (Excel)
- Session attendance PDF
- Assessment review — view and comment on submitted student assessments
- Marks entry — create assessments, enter marks per student, save, export PDF/Excel
- Marks import via Excel template
- Portfolio of Evidence (POE) upload — categorised document types, year and term
- Portfolio viewer

### Student (`/student`)
- Dashboard with attendance summary, assessment status, notifications
- Profile management with photo upload
- Document upload (national ID, birth certificate, passport photo, etc.)
- My Files viewer
- Attendance viewer — summary and unit breakdown
- Unit detail and unit report PDF
- Assessments — view assigned, upload evidence, delete
- Exam bookings — book, view status, download approval PDF
- Marks viewer — results by term/year with result slip PDF
- Portfolio of Evidence — upload and view own POE documents
- Industrial attachment — apply, view status, check-in/check-out via GPS
- Digital logbook — add daily entries with evidence photos
- Employment status (TVET graduate employment tracking)
- Employment projects
- AI assistant (powered by Claude API)

### Examination Officer (`/examination-officer`)
- Dashboard with booking statistics
- Approved exam bookings — filter by admission number, name, class, year
- Confirm (complete) bookings
- Read-only marks viewer with PDF

### Liaison Officer (`/liaison-officer`)
- Dashboard
- Industrial attachment approval (approve/reject per student)
- Company registry
- Logbook review (approve/reject entries)
- Attachments export (Excel)

### Industry Mentor (`/industry-mentor`)
- Dashboard — active trainees, pending logbooks, pending competencies (scoped to mentor's company)
- Logbook review — approve/reject with comments, evidence preview
- Competency assessment — set NYC/C/P/M status with assessor comments
- Trainee list for mentor's company
- Location monitoring — GPS check-in logs for company's trainees

### Internal Verifier (`/internal-verifier`)
- Dashboard with pending competency verifications
- Competency verification — verify or reject industry mentor assessments
- Attachment viewer with competency and logbook detail
- CDACC compliance reports by year and department

### CDACC Verifier (`/cdacc-verifier`)
- Dashboard
- External assessment verification — approve or reject assessments
- Trainer documents viewer (all departments, read-only)
- Marks viewer (read-only)
- Trainee POE viewer

### Workshop Technician (`/workshop-technician`)
- Dashboard
- Workshop inventory management (tools, equipment)
- Clearance approvals for own department

### Admin Oversight (`/admin-oversight`)
- **Registrar** — enrollment and clearance overview across all departments
- **Deputy Principal** — academic activities, clearance summary, certificates
- **Quality Assurance Officer** — department performance reports, assessment approval

### Service Department (`/service-dept`)
- Service clearance approvals (library, finance, etc.)
- Lost items register (add/remove items)

### Clearance (`/clearance`)
- Student clearance initiation
- Multi-stage clearance workflow (trainer → workshop → service dept → dept admin → principal)
- Clearance approver portal — approve, reject, return for correction, waive
- Issue clearance certificate
- Manage trainer assignments per clearance
- Clearance certificate PDF generation
- Public certificate verification by serial number

### Biometric Attendance (`/biometric`)
- Trainer starts a lesson session (class, unit, room, lesson time, week, term, year)
- Live student list with biometric status
- Hardware sensor posts scan data to `/biometric/api/scan`
- Fingerprint enrolment API `/biometric/api/enroll` (called from dept admin)
- Attendance saved to the same `attendance` table as manual marking

### Notifications (`/notifications`)
- Bell dropdown in all portal base templates
- Mark individual or all notifications read
- Notifications created server-side by route actions (exam approval, logbook approval, clearance updates, etc.)

### AI Assistant
- Student-facing chat endpoint `/api/ai-ask`
- Powered by Anthropic Claude API
- Answers questions about the student's own records

---

## Database Tables (key tables)

| Table | Purpose |
|---|---|
| `user_profiles` | All users — id, full_name, role, department_id, admission_no, staff_no |
| `departments` | Departments |
| `courses` | Courses (belong to departments) |
| `classes` | Classes (belong to courses/departments) |
| `units` | Units/subjects (belong to departments) |
| `class_units` | Many-to-many: class ↔ unit, with trainer assignment |
| `enrollments` | Student ↔ class enrolment |
| `attendance` | Daily attendance records (student, class, unit, week, lesson, date) |
| `assessments` | Student assessment uploads (script files, evidence, status) |
| `evidence` | Evidence files linked to assessments |
| `marks` | Mark records (student, unit, class, term, year, score) |
| `exam_bookings` | Student exam booking requests and approvals |
| `trainer_documents` | Trainer POE uploads (categorised by document type) |
| `student_documents` | Student identity and personal documents |
| `clearance_requests` | Student clearance requests |
| `clearance_approvals` | Per-stage approval records for each clearance request |
| `industrial_attachments` | Student attachment placements at companies |
| `companies` | Employer/attachment companies |
| `mentors` | Industry mentor ↔ company links |
| `digital_logbook` | Daily student logbook entries during attachment |
| `competency_tracking` | Workplace competency assessments (NYC/C/P/M) |
| `location_logs` | GPS check-in/out records for attachment students |
| `system_logs` | Audit trail of all significant actions |
| `notifications` | In-app notification records per user |
| `notices` | System broadcast notices |
| `workshop_inventory` | Workshop tools and equipment |
| `lost_items` | Service department lost items register |

---

## URL Reference

| Path | Portal |
|---|---|
| `/` | Landing page |
| `/auth/login` | Login (all roles) |
| `/auth/logout` | Logout |
| `/auth/forgot-password` | Password reset |
| `/super-admin/` | Super Admin dashboard |
| `/dept-admin/` | Dept Admin dashboard |
| `/trainer/` | Trainer dashboard |
| `/student/` | Student dashboard |
| `/student/register` | Student self-registration |
| `/examination-officer/dashboard` | Examination Officer |
| `/industry-mentor/dashboard` | Industry Mentor |
| `/internal-verifier/dashboard` | Internal Verifier |
| `/liaison-officer/` | Liaison Officer |
| `/cdacc-verifier/` | CDACC Verifier |
| `/workshop-technician/dashboard` | Workshop Technician |
| `/admin-oversight/registrar` | Registrar |
| `/admin-oversight/deputy-principal` | Deputy Principal |
| `/admin-oversight/quality-assurance` | Quality Assurance Officer |
| `/service-dept/` | Service Department |
| `/clearance/` | Student clearance |
| `/clearance/verify` | Public certificate verification |
| `/biometric/` | Biometric attendance (trainer UI) |
| `/employer/job-board` | Public job board |

---

## Security

- Passwords are **never stored** in the app database — Supabase Auth handles them with bcrypt
- The `service_role` key is only used server-side and never exposed to the browser
- RLS policies enforce department isolation at the database level
- Python decorators enforce role checks before any query runs
- Audit logs written to `system_logs` for every significant action
- Session cookies: `HttpOnly`, `Secure`, `SameSite=None`
- JWT tokens refreshed automatically before expiry
- File uploads stored in Supabase Storage with bucket-level access policies

---

## Setup

### 1. Supabase

1. Create a project at [supabase.com](https://supabase.com)
2. SQL Editor → run `supabase_schema.sql`
3. Project Settings → API → copy: Project URL, `anon` key, `service_role` key
4. Storage → create public buckets: `assessment-scripts`, `assessment-evidence`, `documents`

### 2. Create Super Admin

```sql
-- In Supabase SQL Editor after creating the user in Auth → Users
INSERT INTO user_profiles (id, full_name, role, is_active)
VALUES ('PASTE-UUID-HERE', 'Super Admin', 'super_admin', TRUE)
ON CONFLICT (id) DO UPDATE SET role = 'super_admin', is_active = TRUE;
```

### 3. Local Development

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env — add SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY, SECRET_KEY
flask run
```

### 4. Deploy to Render

1. Push repo to GitHub
2. Render Dashboard → New Web Service → connect repo
3. Render auto-detects `render.yaml`
4. Set environment variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SECRET_KEY`
