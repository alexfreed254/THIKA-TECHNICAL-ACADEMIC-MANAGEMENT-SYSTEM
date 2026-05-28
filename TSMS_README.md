# Thika Technical Training Institute — Tracer Study Monitoring System (TSMS)

A full-stack web application built with Flask and Supabase for tracking trainee progress, skill evidence, and employer verifications.

## 🌐 Portals

| Portal | URL | Access |
|--------|-----|--------|
| **Landing** | `/` | Public |
| **Trainee Login** | `/auth/login` (select Trainee tab) | Trainees |
| **Institute Login** | `/auth/login` (select Staff/Admin tab) | Admin / Instructors |
| **Employer Login** | `/auth/login` (select Staff/Admin → Employer) | Employers |

## ✨ Features

### 🎓 Trainee Portal
- **Personal Dashboard** — Overview of academic progress, attendance, and clearance status
- **Upload Skill Evidence** — Photos, videos, PDFs with geolocation and skill tags
- **Track Academic Progress** — View marks, attendance, and unit completion
- **Manage Account** — Update profile, change password, upload passport photo
- **Exam Booking** — Submit exam booking requests with approval workflow
- **Admission Documents** — Upload required documents for admission approval
- **Course Clearance** — Multi-stage clearance process with departmental approvals
- **Digital Portfolio** — Portfolio of Evidence (PoE) with assessment uploads

### 🏫 Institute Dashboard
- **View All Trainees** — Complete student management with enrollment tracking
- **Approve Media** — Review and approve trainee assessment uploads
- **Live Activity Feed** — Real-time notifications and system activity
- **GIS Map** — Interactive map showing internship and project locations
- **Employer Verifications** — Manage employer recommendations and verifications
- **Exam Management** — Approve exam bookings, manage marks and results
- **Admission Management** — HOD review and approval of admission documents
- **Clearance Management** — Multi-layer clearance workflow (departmental, institutional, central)

### 🏢 Employer Portal
- **Register Company Account** — Self-registration with admin verification
- **Search Trainees** — Search by name, admission number, or skills
- **Submit Recommendations** — Provide feedback and recommendations (read-only for trainees)
- **Job Postings** — Post job opportunities for trainees
- **View Applications** — Manage trainee job applications

### 📂 Digital Portfolio
- **Public Shareable Portfolio** — Each trainee has a public portfolio URL
- **Verified Skills** — Skills verified by trainers and internal verifiers
- **Employer Reviews** — Recommendations from industry partners
- **Assessment Evidence** — Photos, videos, and documents organized by unit

### 📍 Media Evidence
- **Upload with Geolocation** — Automatic GPS tagging for field work
- **Skill Tags** — Tag evidence with specific competencies
- **Category Organization** — Organize by assessment type and unit
- **Approval Workflow** — Trainer review and approval process

### 🗺️ GIS Map
- **Internship Locations** — View all active industrial attachments
- **Project Locations** — Track field projects and practical work
- **Interactive Leaflet Map** — Zoom, pan, and click for details
- **Geofence Validation** — Verify trainee check-ins at company locations

## 🚀 Setup

### Prerequisites
- Python 3.11+
- [Supabase](https://supabase.com) project

### Local Development

```bash
# Clone and install
git clone <repo-url>
cd <repo>
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt

# Configure
cp .env.example .env
# Fill in SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

# Run
python app.py
```

### Database Setup

1. Run `supabase_schema.sql` in Supabase SQL Editor
2. Run `supabase_rls_fix.sql` to add public read policies and seed departments/courses
3. Run `supabase_employers.sql` to add the employers table
4. Run `python setup_db.py` to seed data and create admin user (if available)

### Create Institute Admin

1. Supabase Dashboard → Authentication → Users → Add User
2. Copy the UUID
3. Run in SQL Editor:

```sql
INSERT INTO user_profiles (id, role, full_name, email, is_active)
VALUES ('YOUR-UUID', 'super_admin', 'Administrator', 'admin@ttti.ac.ke', true)
ON CONFLICT (id) DO UPDATE SET role = 'super_admin', is_active = true;
```

## 🌍 Deployment (Render)

1. Push to GitHub
2. Connect repo on [render.com](https://render.com)
3. Set environment variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SECRET_KEY`

## 🔐 Environment Variables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Flask session secret key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |
| `INSTITUTION_NAME` | Institution display name (optional) |
| `FLASK_ENV` | `development` or `production` |

## 📋 Key Workflows

### Student Admission Workflow
1. Student initiates admission request for a course
2. Student uploads 8 required documents (ID, birth cert, KCSE, etc.)
3. Student submits for HOD review
4. HOD verifies each document individually
5. HOD approves/rejects with comments
6. Student downloads **Departmental Admission Approval Form** and **Departmental Checklist**

### Exam Booking Workflow
1. Student creates exam booking (unit, date, session, purpose)
2. HOD reviews and approves/rejects
3. Examination Officer views approved bookings with filters
4. Examination Officer confirms booking
5. Student downloads **Assessment Registration Form 1A** (TTTI/EXAMS/CDACC/REG/1A)

### Student Clearance Workflow
1. Student initiates clearance for course completion
2. System creates approval stages (departmental, institutional, central)
3. Each approver (HOD, Library, Finance, Sports, Dean, etc.) approves/rejects
4. All stages must be approved for completion
5. Certificate issued when clearance complete
6. Student downloads **Student Clearance Form** (TTTI/ADM/CLEAR/F1)

### Assessment Upload Workflow
1. Student uploads PDF assessment scripts to Supabase Storage
2. Student adds photo/video/audio evidence for each assessment
3. Trainer reviews and approves/rejects
4. Approved assessments appear in Portfolio of Evidence (PoE)
5. HOD can view all trainee PoE for department

## 📄 Official Forms

The system generates official TTTI forms matching physical documents:

1. **Assessment Registration Form 1A** (`TTTI/EXAMS/CDACC/REG/1A`)
   - Regular Candidate Assessment Registration
   - Includes candidate details, exam details, departmental clearance
   - Units of competency table with cost breakdown

2. **Student Clearance Form** (`TTTI/ADM/CLEAR/F1`)
   - Subject/Trainer clearance section
   - Academic departments clearance (10 departments)
   - Other sections (Library, Store, Games, Dean)
   - Finance office clearance with cost breakdown

3. **Departmental Checklist** (Admission Intake)
   - 12-item document checklist
   - Passport photos, admission letter, medical form, personal data
   - KCSE/KCPE certificates, birth certificate, national ID
   - Departmental registering officer signature section

## 🎯 User Roles

| Role | Access Level | Key Features |
|------|--------------|--------------|
| **Super Admin** | System-wide | Full system management, all departments |
| **Dept Admin (HOD)** | Department | Manage classes, trainers, students, approve admissions/exams |
| **Trainer** | Assigned units | Mark attendance, upload marks, review assessments |
| **Student** | Personal | View progress, upload evidence, book exams, apply for clearance |
| **Employer** | Company | Search trainees, post jobs, submit recommendations |
| **Examination Officer** | Institute | View approved bookings, confirm exams, view marks |
| **Registrar** | Institute | Manage admissions, view clearances |
| **Deputy Principal** | Institute | Academic oversight, clearance approvals |
| **Quality Assurance** | Institute | Review approvals, generate reports |
| **Clearance Approvers** | Department | Sports HOD, Library HOD, Finance, Dean, Environment |

## 🛠️ Technology Stack

- **Backend**: Flask (Python)
- **Database**: Supabase (PostgreSQL)
- **Authentication**: Supabase Auth (JWT for staff, password hash for students)
- **Storage**: Supabase Storage (assessment scripts, evidence files)
- **Frontend**: Jinja2 templates, vanilla JavaScript
- **Styling**: Custom CSS with responsive design
- **Icons**: Font Awesome 6.4.0
- **Maps**: Leaflet.js (for GIS tracking)

## 📱 Responsive Design

All portals are fully responsive and work on:
- Desktop (1920px+)
- Laptop (1366px - 1920px)
- Tablet (768px - 1366px)
- Mobile (320px - 768px)

## 🔒 Security Features

- **Role-Based Access Control (RBAC)** — Python decorators enforce permissions
- **Row-Level Security (RLS)** — Supabase RLS policies protect data
- **Department Isolation** — HODs only see their department data
- **JWT Tokens** — Secure session management for staff
- **Password Hashing** — bcrypt for student passwords
- **Audit Logging** — All actions logged to `system_logs` table
- **File Upload Validation** — Type and size restrictions
- **SQL Injection Protection** — Parameterized queries via Supabase client

## 📊 Database Tables

### Core Tables
- `user_profiles` — All users (students, staff, employers)
- `departments` — Academic departments
- `courses` — Course offerings
- `classes` — Class groups with intake year/month
- `units` — Units of competency
- `enrollments` — Student-class relationships

### Academic Tables
- `attendance` — Daily attendance records
- `assessments` — Assessment script uploads
- `evidence` — Photo/video/audio evidence
- `marks` — Formative assessment marks
- `exam_bookings` — Exam booking requests

### Clearance Tables
- `clearance_requests` — Student clearance requests
- `clearance_approvals` — Multi-stage approval records
- `clearance_stages` — Approval stage definitions
- `clearance_departments` — Department/section definitions

### Admission Tables
- `admission_requests` — Student admission requests
- `admission_documents` — Uploaded admission documents

### Job Portal Tables
- `employers` — Employer company profiles
- `job_postings` — Job opportunities
- `job_applications` — Student applications
- `employer_verifications` — Employer recommendations

### Dual Training Tables
- `companies` — Industry partner companies
- `industrial_attachments` — Student placements
- `location_logs` — GPS check-in/check-out records
- `digital_logbook` — Daily work logs

### System Tables
- `system_logs` — Audit trail
- `notifications` — User notifications
- `course_applications` — Public course applications

## 🎓 Support

For technical support or questions:
- Email: support@ttti.ac.ke
- Phone: +254 700 000 000
- Visit: Thika Technical Training Institute, P.O. Box 474-01000, Thika

---

**Version**: 2.0  
**Last Updated**: {{ now().strftime('%B %Y') }}  
**Developed by**: TTTI ICT Department
