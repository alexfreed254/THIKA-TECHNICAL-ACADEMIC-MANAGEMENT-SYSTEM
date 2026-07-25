# Thika Technical Training Institute — Academic Management System

**System documentation (complete project reference)**  
**Institution:** Thika Technical Training Institute (TTTI)  
**Product name:** Academic Management System (TTTI AMS)  
**Document version:** 1.0  
**Last updated:** July 2026  

---

## 1. Purpose and scope

TTTI AMS is a full-stack institutional platform that digitises academic and administrative operations at Thika Technical Training Institute. It serves staff, trainees, mentors, verifiers, and service departments through role-based portals.

### What the system covers

| Domain | Capabilities |
|---|---|
| Academic delivery | Classes, units, enrollments, lesson attendance, formative & summative assessment |
| Assessment evidence | Portfolio of Evidence (POE), scripts, evidence files, trainer documents |
| Examinations | Exam bookings, approvals, confirmation, marks and transcripts |
| Clearance | Multi-stage course clearance, certificates, public verification, lost items |
| Industrial attachment | Placement, GPS check-in/out, digital logbook, mentor competency, liaison oversight |
| Operations | Notices, notifications, audit logs, biometric classroom attendance, academic trips |
| Oversight | Registrar, Deputy Principal, Quality Assurance, CDACC external verification |
| Support | Workshop inventory, service-desk clearance, AI help Q&A |

### Out of scope / incomplete areas

- **Employer job board:** Schema tables exist (`employers`, `job_postings`, `job_applications`); a dedicated employer portal blueprint is not fully wired like other roles.
- **React SPA:** Incremental migration only — Jinja portals remain the production default for most roles.
- **AI assistant:** Currently rule-based institutional Q&A (`/api/ai-ask`), not a live Anthropic Claude dependency in `requirements.txt`.

---

## 2. System identity

| Item | Detail |
|---|---|
| Repository | `THIKA-TECHNICAL-ACADEMIC-MANAGEMENT-SYSTEM` |
| Backend entry | `app.py` → Gunicorn `app:app` |
| Primary UI | Server-rendered Jinja2 templates under `templates/` |
| Secondary UI | React 18 + Vite SPA under `frontend/` (talks to `/api/v1`) |
| Database | Supabase PostgreSQL (+ RLS policies) |
| Auth (staff) | Supabase Auth (email + password → JWT) |
| Auth (trainees) | Admission number + password hash on `user_profiles` |
| File storage | Supabase Storage buckets |
| Hosting | Render (Python web service; auto-deploy from GitHub) |
| Runtime | Python **3.12.9** (`runtime.txt`) |

---

## 3. Technology stack

| Layer | Technology |
|---|---|
| Language / runtime | Python 3.12.9 |
| Web framework | Flask 3.0.3 |
| WSGI server | Gunicorn 22 |
| Auth / CSRF | Flask-WTF · Werkzeug password hashing |
| Rate limiting | Flask-Limiter |
| CORS (SPA) | flask-cors (scoped to `/api/*`) |
| Database client | supabase-py (service role + anon) |
| Timezone | pytz (Africa/Nairobi display filters) |
| PDF | ReportLab |
| Excel | openpyxl |
| Images | Pillow |
| Frontend (legacy/current portals) | Jinja2 · Tailwind CDN · Font Awesome |
| Frontend (SPA) | React 18 · Vite · React Router · TanStack Query · Axios · Tailwind 4 |
| Config | python-dotenv |

### Key Python packages (`requirements.txt`)

```
Flask, flask-cors, Flask-WTF, Flask-Limiter, gunicorn,
supabase, gotrue, python-dotenv, Werkzeug, pytz,
openpyxl, pillow, email-validator, reportlab
```

---

## 4. High-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Browsers                            │
│  Jinja portals (all roles)     React SPA (partial migrate)  │
└───────────────┬───────────────────────────┬─────────────────┘
                │ HTML routes               │ /api/v1 + cookies
                ▼                           ▼
┌─────────────────────────────────────────────────────────────┐
│              Render — Gunicorn → Flask (`app.py`)           │
│  Blueprints · CSRF · Rate limits · Session · Role guards    │
└─────────────────────────────┬───────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   Supabase Auth        Supabase DB         Supabase Storage
   (staff JWT)          (PostgreSQL+RLS)    (files / media)
```

### Design principles

1. **Role-based portals** — each role has a URL prefix and template set.
2. **Department isolation** — dept admins and trainers are scoped to their department / assigned units.
3. **Dual authentication** — staff use Supabase Auth; trainees use local password hashes (no trainee JWT).
4. **Defence in depth** — Python decorators + Supabase RLS + CSRF + upload validation + audit logs.
5. **Incremental SPA** — React replaces screens gradually; Jinja remains authoritative until parity.

---

## 5. Application structure

### 5.1 Important root modules

| File | Role |
|---|---|
| `app.py` | Flask app, session/cookie config, CSRF/limiter init, blueprint registration, error handlers, Jinja globals |
| `auth_utils.py` | Login helpers, roles, RBAC decorators, audit log, session refresh |
| `db.py` | Supabase anon / service / user-token clients |
| `extensions.py` | Shared `csrf` and `limiter` instances |
| `security_utils.py` | Session-safe profiles, upload rules, search sanitisation, safe redirects, service-desk role maps |
| `notifications.py` | Create / list / mark-read notifications; notice recall |
| `grading_utils.py` | TVET CDACC competency grading scale |
| `report_utils.py` | Shared PDF header / signature helpers |
| `stats_utils.py` | Aggregated statistics helpers |
| `exam_booking_form1a.py` | Exam booking form generation |
| `academic_result_transcript.py` | Transcript PDF helpers |
| `unit_attendance_register.py` | Attendance register PDF helpers |

### 5.2 Top-level layout

```
THIKA TECHNICAL ACADEMIC MANAGEMENT SYSTEM/
├── app.py
├── auth_utils.py, db.py, extensions.py, security_utils.py, …
├── routes/                 # Flask blueprints
├── templates/              # Jinja portals per role
├── static/                 # CSS, JS (csrf.js, secure-dom.js), assets
├── frontend/               # React + Vite SPA
├── assets/                 # Brand images
├── supabase_schema.sql     # Base schema
├── *_migration.sql         # Incremental DB migrations
├── requirements.txt
├── runtime.txt
├── Procfile / render.yaml
└── README.md / this document
```

### 5.3 Blueprint map

| Blueprint | URL prefix | Primary users |
|---|---|---|
| `main` | `/` | Public landing / redirects |
| `auth` | `/auth` | All users (login, logout, profile, password) |
| `api_v1` | `/api/v1` | React SPA |
| `super_admin` | `/super-admin` | Super Admin |
| `dept_admin` | `/dept-admin` | Department Admin |
| `trainer` | `/trainer` | Trainer |
| `student` | `/student` | Trainee |
| `examination_officer` | `/examination-officer` | Examination Officer |
| `industry_mentor` | `/industry-mentor` | Industry Mentor |
| `internal_verifier` | `/internal-verifier` | Internal Verifier |
| `clearance` | `/clearance` | Students + clearance approvers |
| `admin_oversight` | `/admin-oversight` | Registrar, DP, QA |
| `notifications` | `/notifications` | All authenticated users |
| `liaison_officer` | `/liaison-officer` | Liaison Officer |
| `cdacc_verifier` | `/cdacc-verifier` | CDACC Verifier |
| `workshop_technician` | `/workshop-technician` | Workshop Technician |
| `biometric` | `/biometric` | Trainers + hardware devices |
| `service_dept` | `/service-dept` | Library / Sports / Service clearance |
| `academic_trips` | `/academic-trips` | Trips coordinators / reviewers |
| `summative` | `/summative` | Trainers / Dept Admin / Super Admin |
| `ai` | `/api/ai-*` | Authenticated Q&A |

---

## 6. Authentication and sessions

### 6.1 Login model

| Portal tab | Identifier | Password store | Session tokens |
|---|---|---|---|
| **Staff / Admin** | Institutional **email only** | Supabase Auth | Flask session + JWT access/refresh |
| **Trainee** | **Admission number only** | `user_profiles.password_hash` (Werkzeug) | Flask session only (no JWT) |

Login UI: `/auth/login` (split hero design). Staff and trainee fields are mutually exclusive (inactive field is disabled so it is not submitted).

### 6.2 Session keys

- `sb_user` — safe profile subset (never includes `password_hash`)
- `sb_access_token` / `sb_refresh_token` — staff JWT pair
- Cookie: `HttpOnly`; `Secure` in production; `SameSite=Lax` (or `None` when `SPA_CROSS_SITE=true`)
- Lifetime: 1 day (`PERMANENT_SESSION_LIFETIME`)

### 6.3 Auth routes (`/auth`)

| Route | Method | Purpose |
|---|---|---|
| `/auth/login` | GET/POST | Dual login (rate-limited) |
| `/auth/logout` | GET | Clear session immediately; audit in background |
| `/auth/forgot-password` | GET/POST | Self-reset disabled — directs trainees to admin |
| `/auth/change-password` | GET/POST | Forced/optional password change |
| `/auth/profile` | GET/POST | Profile management |
| `/auth/student/register` | GET/POST | Optional self-registration (`ALLOW_STUDENT_SELF_REGISTER`) |

### 6.4 Post-login redirects (examples)

| Role | Landing |
|---|---|
| `super_admin` | `/super-admin/` |
| `dept_admin` | `/dept-admin/` |
| `trainer` | `/trainer/` |
| `student` | `/student/dashboard` |
| `examination_officer` | `/examination-officer/` |
| `industry_mentor` | `/industry-mentor/` |
| `internal_verifier` | `/internal-verifier/` |
| `liaison_officer` | `/liaison-officer/` |
| `cdacc_verifier` | `/cdacc-verifier/` |
| `workshop_technician` | `/workshop-technician/` |
| `library_hod` / `sports_hod` / `service_clearance_officer` | `/service-dept/` |
| `environment_hod` / `dean_students` / `finance_officer` | `/clearance/approver` |
| `registrar` | `/admin-oversight/registrar` |
| `deputy_principal` | `/admin-oversight/deputy-principal` |
| `quality_assurance_officer` | `/admin-oversight/quality-assurance` |

### 6.5 Password policy hooks

- `must_change_password` on profile blocks most routes until `/auth/change-password` succeeds (HTML + API).
- Temporary passwords set by admins should flip this flag.

---

## 7. Authorisation (RBAC)

### 7.1 Roles recognised by the application

**Staff roles (`STAFF_ROLES`):**

`super_admin`, `dept_admin`, `trainer`, `employer`, `examination_officer`, `industry_mentor`, `internal_verifier`, `sports_hod`, `environment_hod`, `dean_students`, `library_hod`, `finance_officer`, `registrar`, `deputy_principal`, `quality_assurance_officer`, `workshop_technician`, `liaison_officer`, `cdacc_verifier`, `service_clearance_officer`

**Trainee role:** `student`

**Hardware:** biometric devices authenticate with `BIOMETRIC_DEVICE_SECRET` (not a user role).

### 7.2 Enforcement layers

1. **Decorators** — `@login_required`, `@role_required(...)`, portal helpers (`student_required`, `trainer_required`, …)
2. **Query scoping** — department / class / unit ownership checks in route logic
3. **Supabase RLS** — row-level policies in schema/migrations
4. **Service desks** — `SERVICE_DEPT_ROLES` maps clearance categories to allowed roles

---

## 8. Module reference (functional detail)

### 8.1 Super Admin (`/super-admin`)

Institution-wide control plane:

- Dashboard and system statistics  
- CRUD: departments, classes, units, courses, users  
- Cross-department attendance, assessments, marks  
- Exam booking oversight  
- Clearance and attachment viewers  
- GIS / location exports  
- Companies, notices, audit logs (`system_logs`)  
- Data import tools  
- Biometric scanner registry  

### 8.2 Department Admin (`/dept-admin`)

Department-scoped academic administration:

- Classes, units, trainers, students (enrol / export)  
- Attendance matrices and PDF registers  
- Exam booking approve/reject (+ PDF/Excel)  
- Marks reports  
- Trainer POE and trainee documents  
- Industrial attachment management and companies  
- Notices to department users  
- Credentials view / password reset initiation  
- Fingerprint ID enrolment for trainees  

### 8.3 Trainer (`/trainer`)

Teaching delivery for assigned classes/units:

- Dashboard (pending attendance, quick links)  
- Live lesson attendance  
- Assessment review / formative marks entry  
- Marks import/export  
- POE uploads  
- Biometric lesson sessions  

### 8.4 Trainee / Student (`/student`)

Learner self-service:

- Dashboard (attendance %, assessments, attachment, clearance snapshot)  
- Profile and personal documents  
- Units, lesson attendance, marks / result slip  
- Assessments + evidence upload  
- Exam booking form and history  
- Portfolio of Evidence  
- Industrial attachment (request, acceptance letter, GPS check-in/out, logbook)  
- Attachment marks and mentoring tool uploads  
- Employment status / projects  
- Summative competence (read-only view of own results)  
- Course clearance entry point  
- AI help endpoint (`/student/ai-ask` → shared AI API)  

### 8.5 Examination Officer (`/examination-officer`)

- Confirm approved exam bookings  
- Read-only marks views / PDFs  

### 8.6 Clearance (`/clearance`)

Multi-stage course clearance workflow:

- Student initiates / can stop (cancel) a request  
- Approvers act by stage and department/service  
- Approve, reject, return for correction, waive  
- Certificate generation and PDF  
- Public verify by serial (`/clearance/verify`)  
- Service-desk and lost-items support  

### 8.7 Industrial attachment

End-to-end workplace learning:

| Actor | Actions |
|---|---|
| Trainee | Apply, upload acceptance letter, GPS check-in/out, logbook |
| Liaison Officer | Periods, approvals, companies, grading, exports |
| Industry Mentor | Logbook approve/reject, competency (NYC/C/P/M), GPS monitor |
| Internal Verifier | Verify competencies; compliance reports |
| Dept / Super Admin | Oversight and exports |

### 8.8 Summative assessment (`/summative`)

TVET CDACC competence entry and reporting:

| Level | Meaning (grading utils) |
|---|---|
| Mastery (M) | 80–100% |
| Proficient (P) | 65–79% |
| Competent (C) | 50–64% |
| Not Yet Competent (NYC) | 0–49% |
| CRNM | Course Requirement Not Met |

Features: competence entry grid, unit performance analysis, Excel/PDF reports, graduation list (admin).

### 8.9 Biometric attendance (`/biometric`)

- Trainer starts a classroom biometric session  
- Device POSTs scans to CSRF-exempt APIs with shared secret  
- Matches `biometric_id` / fingerprint IDs on enrolled trainees  
- Writes standard `attendance` rows  

### 8.10 Academic trips (`/academic-trips`)

- Trip records and media uploads (`trip-media` bucket)  
- Trainer/coordinator upload; dept/super review  

### 8.11 Notifications (`/notifications`)

- In-app bell on portals  
- Created on workflow events  
- Mark read / mark all  
- Sender recall supported via `sender_id` / `notice_id` columns  

### 8.12 Other portals

| Portal | Focus |
|---|---|
| CDACC Verifier | External verification of assessments, marks, trainer/trainee POE |
| Workshop Technician | Workshop inventory + clearance for workshop |
| Service Dept | Library / Sports / service clearance desks + lost items |
| Admin Oversight | Registrar, Deputy Principal, QA read/approve views |
| AI API | Role-aware rule-based Q&A over accessible stats |

### 8.13 REST API v1 (`/api/v1`) — SPA backend

Cookie-session API used by the React app:

- `GET /csrf-token`  
- `POST /auth/login` · `POST /auth/logout` · `GET /auth/me`  
- Notifications recent/count  
- Trainer: dashboard, marks-entry, assessments, attendance  
- Student: dashboard, attendance, units, marks  

CORS origins from `SPA_ORIGINS` (default localhost Vite ports).

---

## 9. Grading standard (TVET CDACC)

All formative percentage displays and summative competence should align to:

| Marks range | Grade | Code | Meaning |
|---|---|---|---|
| 80–100% | Mastery | M | High mastery, accuracy, independence, consistency |
| 65–79% | Proficient | P | Strong competence with minor improvement areas |
| 50–64% | Competent | C | Minimum required standard met |
| 0–49% | Not Yet Competent | NYC | Further training / reassessment needed |
| — | CRNM | CRNM | Course requirement not met |

Shared implementation: `grading_utils.py`.

---

## 10. Database

### 10.1 Platform

- **Engine:** PostgreSQL via Supabase  
- **Access from app:** service-role client for server operations; anon/user clients where appropriate  
- **Security:** Row Level Security (RLS) policies in schema  

### 10.2 Core tables (base schema)

**Organisation:** `departments`, `courses`, `classes`, `units`, `class_units`, `trainer_units`, `enrollments`  

**People:** `user_profiles` (central identity; roles; admission/staff numbers; password_hash for students)  

**Teaching:** `attendance`, `class_events`, `formative_assessments`, `formative_marks`, `assessments`, `evidence`, `marks`  

**Exams:** `exam_bookings`  

**Documents:** `trainer_documents`, `trainee_documents`, `student_personal_documents`  

**Attachment:** `companies`, `mentors`, `industrial_attachments`, `location_logs`, `digital_logbook`, `competency_tracking` (+ workflow tables from migrations)  

**Clearance:** `clearance_departments`, `clearance_stages`, `clearance_requests`, `clearance_approvals` (+ lost items)  

**Jobs / employment:** `employers`, `employer_verifications`, `job_postings`, `job_applications`, `employment_tracking`, `employment_projects`  

**Ops:** `system_logs`, `notifications`, `dept_notices`, `admission_requests`, `admission_documents`, `course_applications`  

### 10.3 Important migrations

| Migration file | Purpose |
|---|---|
| `new_roles_migration.sql` | Expand allowed `user_profiles.role` values |
| `clearance_migration.sql` | Clearance serial numbers |
| `clearance_stage2_migration.sql` | Parallel stages, return-for-correction |
| `clearance_cancel_migration.sql` | Trainee can cancel/stop clearance |
| `lost_items_migration.sql` | Lost items register |
| `workshop_inventory_migration.sql` | Workshop inventory |
| `biometric_migration.sql` | Biometric sessions + profile biometric id |
| `biometric_attendance_migration.sql` | Fingerprint id support |
| `biometric_scanners_migration.sql` | Scanner device registry |
| `academic_trips_migration.sql` | Academic trips + media |
| `summative_competence_migration.sql` | Summative competence table (CDACC levels) |
| `attachment_workflow_migration.sql` | Attachment periods, weekly attendance, grading, mentoring tools |
| `industrial_attachment_acceptance_letter_migration.sql` | Acceptance letter fields/status |
| `dept_notices_migration.sql` | Department notices |
| `notifications_sender_migration.sql` | Notification sender / notice recall fields |
| `trainer_documents_update_migration.sql` | Extra trainer POE document types |
| `migration_student_documents.sql` | Student personal documents |
| `fix_course_applications_fk_migration.sql` | Course applications FK fix |
| `verify_deployment.sql` | Post-deploy verification queries |

**Base schema file:** `supabase_schema.sql` (run first on a new project, then apply migrations in dependency order).

### 10.4 Storage buckets (typical)

| Bucket | Typical contents |
|---|---|
| `assessment-scripts` | Assessment scripts |
| `assessment-evidence` | Evidence files |
| `documents` | General documents / POE |
| `trip-media` | Academic trip photos/media |

Optional `PRIVATE_STORAGE=true` uses signed URLs instead of public object URLs.

---

## 11. Frontend

### 11.1 Jinja portals (production default)

- Located in `templates/{role}/` with shared patterns (sidebar, topbar, notifications, logos).  
- Brand assets via `LOGO_URL` / `GOVT_LOGO_URL` from `app.py` context processor.  
- Client helpers: `static/js/csrf.js`, `static/js/secure-dom.js`, optional SPA-like navigation script.

### 11.2 React SPA (`frontend/`)

| Item | Detail |
|---|---|
| Stack | React 18, Vite, React Router, TanStack Query, Axios, Tailwind 4 |
| API | Flask `/api/v1` with credentials (session cookies) |
| Migrated areas | Auth login; trainer dashboard/marks/assessments/attendance; student dashboard/attendance/units/marks |
| Unfinished | Placeholder screens linking back to Jinja (`VITE_LEGACY_ORIGIN`) |
| Local | Vite `:5173` proxies `/api` and `/static` to Flask `:5000` |

**Policy:** Do not remove Jinja portals until SPA feature parity for that role is complete.

---

## 12. Security model

| Control | Implementation |
|---|---|
| Secrets | `SECRET_KEY` required in production |
| Session hygiene | `session_safe_profile()` strips password hashes |
| CSRF | Flask-WTF on POSTs; tokens in forms + `csrf.js`; SPA `/api/v1/csrf-token` |
| Rate limits | Login / register / forgot-password limited per IP |
| Uploads | Extension allow-lists, size limits (`MAX_CONTENT_LENGTH` 25 MB) |
| Search | Metacharacter sanitisation for PostgREST filters |
| Redirects | Same-host only (`safe_redirect_url`) |
| Password gate | `must_change_password` blocks portals until changed |
| Biometric API | Shared secret; CSRF exempt only for device endpoints |
| Audit | `write_audit_log` → `system_logs` |
| Proxy | `ProxyFix` for Render TLS / client IP |
| Cookies | Secure + HttpOnly in production |

Forgot-password self-service for trainees is **disabled** (prevents admission-number takeover). Resets are admin-assisted.

---

## 13. Configuration and deployment

### 13.1 Required environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Flask session / CSRF signing |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_ANON_KEY` | Anon key (RLS-honouring client) |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role (server-side) |

### 13.2 Optional environment variables

| Variable | Purpose |
|---|---|
| `FLASK_ENV` | development / production |
| `SETUP_PROFILE_TOKEN` | Gate sensitive setup profile routes |
| `BIOMETRIC_DEVICE_SECRET` | Device API authentication |
| `PRIVATE_STORAGE` | Prefer signed storage URLs |
| `ALLOW_STUDENT_SELF_REGISTER` | Enable public trainee registration |
| `SPA_ORIGINS` | Comma-separated CORS origins for SPA |
| `SPA_CROSS_SITE` | Cross-site cookies (`SameSite=None`) |
| `SESSION_COOKIE_SECURE` | Force Secure cookies |
| `PORT` | Listen port (Render sets this) |

### 13.3 SPA env (`frontend/.env`)

- `VITE_API_BASE_URL` — Flask API origin  
- `VITE_LEGACY_ORIGIN` — Jinja fallback links  
- Optional socket URL if used  

### 13.4 Deploy (Render)

1. Connect GitHub repository.  
2. Build: `pip install -r requirements.txt`  
3. Start: `gunicorn app:app` (see `Procfile` / `render.yaml`)  
4. Set env vars in Render dashboard.  
5. Apply `supabase_schema.sql` + pending `*_migration.sql` on Supabase.  
6. Create storage buckets and policies.  

Local run:

```bash
pip install -r requirements.txt
flask --app app run
# or: python app.py
```

SPA local:

```bash
cd frontend
npm install
npm run dev
```

---

## 14. Operational workflows (summary)

### Trainee journey

1. Account created by Dept Admin / Super Admin (or optional self-register).  
2. Login with admission number + password.  
3. May be forced to change temporary password.  
4. Use portal for attendance, assessments, exams, POE, attachment, clearance.  

### Teaching journey

1. Dept Admin assigns trainers to class/units.  
2. Trainer marks attendance (manual or biometric).  
3. Trainer enters formative marks / reviews assessments.  
4. Summative competence entered via `/summative`.  
5. Exam bookings flow: student → dept approval → examination officer confirmation.  

### Clearance journey

1. Eligible trainee starts clearance.  
2. Stage 1 / Stage 2 approvers act (academic + service desks).  
3. Certificate issued; public verify by serial.  
4. Trainee may cancel an in-progress request (migration-supported).  

### Attachment journey

1. Placement period opened by liaison / admin.  
2. Trainee applies + uploads acceptance letter.  
3. Mentors approve logbook and competencies.  
4. GPS check-ins recorded; liaison grades / exports.  

---

## 15. Error pages and UX notes

| Code | Template | Notes |
|---|---|---|
| 400 | `templates/errors/400.html` | Generic bad request |
| CSRF | Redirect to `/auth/login` with flash | Prefer this over raw 400 for auth forms |
| 403 | `templates/errors/403.html` | Forbidden / wrong role |
| 404 | `templates/errors/404.html` | Missing route |
| 500 | `templates/errors/500.html` | Server error (traceback logged) |

Login branding: Plus Jakarta Sans / DM Mono, split hero, staff vs trainee tabs, `noindex`.

Logout clears the Flask session **first** (avoids hangs on remote Supabase sign-out).

---

## 16. Related documents in the repository

| Document | Content |
|---|---|
| `README.md` | Quick start, roles overview, module list |
| `frontend/README.md` | SPA setup and migration notes |
| `VISUAL_IMPLEMENTATION_GUIDE.md` | UI/visual implementation notes |
| `IMPLEMENTATION_STATUS.md` / `IMPLEMENTATION_COMPLETE.md` | Feature completion trackers |
| `SESSION_COMPLETE.md` | Session work logs |
| Migration `*.sql` files | Database change scripts |

This **SYSTEM_DOCUMENTATION.md** is the consolidated reference for architecture, roles, modules, data, security, and deployment.

---

## 17. Glossary

| Term | Meaning |
|---|---|
| AMS | Academic Management System |
| TTTI | Thika Technical Training Institute |
| Trainee / Student | Learner role (`student`) |
| POE | Portfolio of Evidence |
| CDACC | Curriculum Development, Assessment and Certification Council (TVET) |
| RLS | Row Level Security (PostgreSQL/Supabase) |
| JWT | JSON Web Token (staff Supabase Auth session) |
| SPA | Single Page Application (`frontend/`) |
| NYC / CRNM | Not Yet Competent / Course Requirement Not Met |

---

## 18. Document maintenance

When the system changes, update this file for:

1. New roles or blueprint prefixes  
2. New migrations (add to §10.3)  
3. SPA screens reaching parity (update §11.2)  
4. New required env vars (update §13)  
5. Security policy changes (update §12)  

**Owners:** Development team maintaining the TTTI AMS GitHub repository and Render/Supabase deployments.
