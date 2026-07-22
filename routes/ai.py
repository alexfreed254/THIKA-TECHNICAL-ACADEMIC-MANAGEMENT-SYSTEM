"""
routes/ai.py — TTTI Guardian AI Assistant.

Rule-based, role-aware assistant that answers from live Supabase data.
Aligned with current portal menus and workflows (Marks Entry / formative marks,
Trainee POE review, Exam Booking HOD → Exam Office → completed, etc.).
"""

from flask import Blueprint, request, jsonify
from auth_utils import login_required, current_user
from db import get_service_client

ai_bp = Blueprint("ai", __name__)

# ── Role metadata ─────────────────────────────────────────────────────────────

ROLE_PORTALS = {
    "student": "Trainee Portal",
    "trainer": "Trainer Portal",
    "dept_admin": "Department Admin Portal",
    "super_admin": "Super Admin Portal",
    "examination_officer": "Examination Officer Portal",
    "industry_mentor": "Industry Mentor Portal",
    "internal_verifier": "Internal Verifier Portal",
    "cdacc_verifier": "CDACC Verifier Portal",
    "liaison_officer": "Liaison Officer Portal",
    "workshop_technician": "Workshop Technician Portal",
    "admin_oversight": "Admin Oversight Portal",
    "sports_hod": "Sports Department Portal",
    "environment_hod": "Environment Department Portal",
    "dean_students": "Dean of Students Portal",
    "library_hod": "Library Portal",
    "finance_officer": "Finance Portal",
    "registrar": "Registrar Portal",
    "deputy_principal": "Deputy Principal Portal",
    "quality_assurance_officer": "Quality Assurance Portal",
    "service_clearance_officer": "Service Clearance Portal",
}

ROLE_SUGGESTIONS = {
    "student": [
        {"label": "My Units", "query": "Show my enrolled units", "icon": "book-open"},
        {"label": "Attendance", "query": "What is my attendance?", "icon": "clipboard-list"},
        {"label": "Marks", "query": "Show my formative marks", "icon": "chart-line"},
        {"label": "POE Status", "query": "Show my POE status", "icon": "folder-open"},
        {"label": "Exam Booking", "query": "Can I book an exam and what is my booking status?", "icon": "file-signature"},
        {"label": "Clearance", "query": "What is my clearance status?", "icon": "clipboard-check"},
    ],
    "trainer": [
        {"label": "My Classes", "query": "Show my assigned classes and units", "icon": "chalkboard"},
        {"label": "Pending POE", "query": "How many POE assessments need my review?", "icon": "clock"},
        {"label": "Attendance", "query": "What is attendance for my trainees?", "icon": "clipboard-list"},
        {"label": "Marks Entry", "query": "How do I enter formative marks?", "icon": "edit"},
        {"label": "Dashboard", "query": "Give me a trainer overview", "icon": "tachometer-alt"},
    ],
    "dept_admin": [
        {"label": "Dept Overview", "query": "Give me a department overview", "icon": "chart-pie"},
        {"label": "Pending POE", "query": "How many pending trainee POE submissions?", "icon": "clock"},
        {"label": "Exam Bookings", "query": "How many pending exam bookings need HOD approval?", "icon": "file-signature"},
        {"label": "Attendance", "query": "What is the department attendance?", "icon": "clipboard-list"},
        {"label": "Credentials", "query": "How do I reset a forgotten password?", "icon": "key"},
    ],
    "super_admin": [
        {"label": "System Overview", "query": "Give me a full system overview", "icon": "server"},
        {"label": "Pending Items", "query": "Show all pending items system-wide", "icon": "hourglass-half"},
        {"label": "Users", "query": "How many users are registered?", "icon": "users"},
        {"label": "Exam Bookings", "query": "How many pending exam bookings institute-wide?", "icon": "file-signature"},
        {"label": "Credentials", "query": "How do I reset a user password?", "icon": "key"},
    ],
    "examination_officer": [
        {"label": "To Confirm", "query": "How many approved exam bookings await my confirmation?", "icon": "clipboard-check"},
        {"label": "Completed", "query": "How many exam bookings are completed?", "icon": "check-circle"},
        {"label": "Stats", "query": "Give me an exam booking statistics overview", "icon": "chart-bar"},
    ],
    "industry_mentor": [
        {"label": "My Trainees", "query": "Show my active industrial attachment trainees", "icon": "user-graduate"},
        {"label": "Logbooks", "query": "How many pending logbook approvals?", "icon": "book"},
    ],
    "internal_verifier": [
        {"label": "Pending", "query": "How many assessments are pending verification?", "icon": "clock"},
        {"label": "Stats", "query": "Show verification statistics", "icon": "chart-bar"},
    ],
    "liaison_officer": [
        {"label": "Placements", "query": "How many industrial attachment placements are pending?", "icon": "industry"},
        {"label": "Companies", "query": "How many industry partners are registered?", "icon": "building"},
        {"label": "Logbooks", "query": "How many logbooks need liaison review?", "icon": "book"},
    ],
    "workshop_technician": [
        {"label": "Inventory", "query": "Give me a workshop inventory summary", "icon": "boxes"},
        {"label": "Clearances", "query": "How many clearance approvals are pending for me?", "icon": "clipboard-check"},
    ],
    "cdacc_verifier": [
        {"label": "Pending", "query": "How many assessments await CDACC verification?", "icon": "certificate"},
        {"label": "Marks", "query": "Where do I view formative marks?", "icon": "chart-line"},
    ],
}

_DEFAULT_SUGGESTIONS = [
    {"label": "Overview", "query": "Give me an overview of my dashboard", "icon": "tachometer-alt"},
    {"label": "Pending Items", "query": "What items are pending my attention?", "icon": "bell"},
    {"label": "Help", "query": "What can you help me with?", "icon": "question-circle"},
]

SERVICE_ROLES = frozenset({
    "sports_hod", "environment_hod", "dean_students", "library_hod",
    "finance_officer", "registrar", "deputy_principal",
    "quality_assurance_officer", "service_clearance_officer",
})


def _matches(kw: str, *phrases) -> bool:
    return any(p in kw for p in phrases)


def _first_name(user: dict) -> str:
    name = (user.get("full_name") or "").strip()
    return name.split()[0] if name else "there"


def _suggestions(role: str) -> list:
    if role in SERVICE_ROLES:
        return [
            {"label": "Pending Clearances", "query": "How many clearances are pending for my department?", "icon": "hourglass-half"},
            {"label": "Help", "query": "What can you help me with?", "icon": "question-circle"},
        ]
    return ROLE_SUGGESTIONS.get(role, _DEFAULT_SUGGESTIONS)


def _ai_response(reply: str, role: str) -> dict:
    return {"reply": reply, "suggestions": _suggestions(role)}


def _count(query) -> int:
    try:
        res = query.execute()
        if getattr(res, "count", None) is not None:
            return res.count or 0
        return len(res.data or [])
    except Exception:
        return 0


def _safe_data(query, default=None):
    try:
        return query.execute().data or (default if default is not None else [])
    except Exception:
        return default if default is not None else []


def _help_text(role: str) -> str:
    topics = {
        "student": (
            "My Units, Lesson Attendance, Marks & Transcripts (formative), Portfolio of Evidence, "
            "Assessments, My Documents, Exam Booking Form / My Exam Bookings, Industrial Attachment, "
            "Digital Logbook, Course Clearance, and Employment Status"
        ),
        "trainer": (
            "Dashboard, Mark Attendance / Biometric Attendance, Trainee POE Review, Marks Entry "
            "(Oral/Practical/Theory), My Portfolio, Clearance Approvals"
        ),
        "dept_admin": (
            "Department dashboard, Exam Booking Approvals (HOD), Trainee/Trainer POE, Marks Reports, "
            "Manage Credentials, Attendance Search, Industry Partners, Summative Assessments"
        ),
        "super_admin": (
            "Institute overview, users, departments, Exam Booking Approvals (oversight), "
            "Manage Credentials, Summative Assessments, documents, and imports"
        ),
        "examination_officer": (
            "Approved Exam Bookings awaiting confirmation, and completed bookings. "
            "Workflow: Trainee submits → HOD approves → you Confirm → Completed"
        ),
        "industry_mentor": "Active attachment trainees at your company, logbook approvals, and competency checks",
        "internal_verifier": "Assessment verification queue and statistics",
        "liaison_officer": "Industrial attachment placements, companies, logbook review, and attachment marks",
        "workshop_technician": "Workshop inventory and clearance approvals assigned to you",
        "cdacc_verifier": "CDACC verification of assessments, trainee POE, formative marks, and attachment records",
    }
    if role in SERVICE_ROLES:
        topic = "Pending clearances for your service department and lost-and-found items on your dashboard"
    else:
        topic = topics.get(role, "your dashboard features, pending items, and navigation")
    label = ROLE_PORTALS.get(role, "your portal")
    return (
        f"I'm **TTTI Guardian** for the **{label}**.\n\n"
        f"I can help with: {topic}.\n\n"
        f"Ask in plain language, or tap a **suggested question** below."
    )


def _universal(kw: str, role: str, user: dict):
    if _matches(kw, "thank", "thanks", "appreciate", "asante"):
        return "You're welcome! Ask anytime if you need more help."
    if _matches(kw, "hello", " hi", "hi ", "hey", "good morning", "good afternoon",
                "good evening", "howdy", "greetings"):
        return f"Hello **{_first_name(user)}**! I'm TTTI Guardian. How can I help you today?"
    if _matches(kw, "help", "what can you", "what do you", "capabilities", "features",
                "commands", "what can i ask"):
        return _help_text(role)
    if _matches(kw, "who are you", "what are you", "your name"):
        return (
            "I'm **TTTI Guardian** — the AI academic assistant for "
            "Thika Technical Training Institute.\n\n"
            "I answer from your live portal data: records, pending tasks, and how to use menus."
        )
    if _matches(kw, "password", "credential", "forgot password", "reset password", "login"):
        if role == "student":
            return (
                "Trainees sign in with **admission number**. If you forgot your password, "
                "ask your **HOD (Dept Admin → Manage Credentials)** or Super Admin to set a temporary one. "
                "You will be asked to change it after login. Profile: `/auth/profile`"
            )
        if role in ("dept_admin", "super_admin"):
            path = "/dept-admin/credentials" if role == "dept_admin" else "/super-admin/credentials"
            return (
                f"Use **Manage Credentials** ({path}) to **Set** or **Reset** a password. "
                "Share the temporary password once, then the user changes it at next login. "
                "Staff log in with email; trainees with admission number."
            )
        return (
            "Staff sign in with **email**. Ask Dept Admin or Super Admin → **Manage Credentials** "
            "to reset a forgotten password. Update your own details at `/auth/profile`."
        )
    return None


@ai_bp.route("/api/ai-meta", methods=["GET"])
@login_required
def ai_meta():
    user = current_user() or {}
    role = (user.get("role") or "").lower()
    db = get_service_client()
    return jsonify({
        "role": role,
        "name": _first_name(user),
        "portal": ROLE_PORTALS.get(role, "TTTI Portal"),
        "suggestions": _suggestions(role),
        "greeting": _build_greeting(db, user, role),
    })


@ai_bp.route("/api/ai-ask", methods=["POST"])
@login_required
def ai_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("q") or "").strip()
    user = current_user() or {}
    role = (user.get("role") or "").lower()

    if not question:
        return jsonify(_ai_response("Please type a question so I can help you.", role))

    kw = " " + question.lower() + " "
    uid = user.get("id")
    db = get_service_client()

    universal = _universal(kw, role, user)
    if universal:
        return jsonify(_ai_response(universal, role))

    try:
        handlers = {
            "student": lambda: _student(db, uid, kw),
            "dept_admin": lambda: _dept_admin(db, uid, user, kw),
            "trainer": lambda: _trainer(db, uid, kw),
            "super_admin": lambda: _super_admin(db, kw),
            "examination_officer": lambda: _exam_officer(db, kw),
            "industry_mentor": lambda: _industry_mentor(db, uid, kw),
            "internal_verifier": lambda: _internal_verifier(db, kw),
            "liaison_officer": lambda: _liaison(db, kw),
            "workshop_technician": lambda: _workshop(db, user, kw),
            "cdacc_verifier": lambda: _cdacc(db, kw),
        }
        if role in SERVICE_ROLES:
            reply = _service_dept(db, user, kw)
        else:
            reply = handlers.get(role, lambda: _generic(role, kw))()
    except Exception as exc:
        print(f"[ai] handler error role={role}: {exc}")
        reply = (
            "I hit a temporary data error. Try again, or open the related menu in the sidebar. "
            "If it continues, contact your administrator."
        )
    return jsonify(_ai_response(reply, role))


def _build_greeting(db, user: dict, role: str) -> str:
    name = _first_name(user)
    portal = ROLE_PORTALS.get(role, "TTTI Portal")
    snap = "Ready to assist"
    try:
        if role == "student" and user.get("id"):
            rows = _safe_data(db.table("attendance").select("status").eq("student_id", user["id"]))
            total = len(rows)
            if total:
                pct = round(sum(1 for r in rows if r.get("status") == "present") / total * 100, 1)
                snap = f"Attendance **{pct}%**"
            else:
                snap = "No attendance recorded yet"
        elif role == "trainer" and user.get("id"):
            unit_ids = _trainer_unit_ids(db, user["id"])
            pending = 0
            if unit_ids:
                pending = len(_safe_data(
                    db.table("assessments").select("id").in_("unit_id", unit_ids).eq("status", "pending")
                ))
            snap = f"**{pending}** pending POE review{'s' if pending != 1 else ''}"
        elif role == "dept_admin" and user.get("department_id"):
            students = _count(
                db.table("user_profiles").select("id", count="exact")
                .eq("role", "student").eq("department_id", user["department_id"])
            )
            snap = f"**{students}** trainees in your department"
        elif role == "super_admin":
            students = _count(db.table("user_profiles").select("id", count="exact").eq("role", "student"))
            snap = f"**{students}** trainees system-wide"
        elif role == "examination_officer":
            approved = _count(
                db.table("exam_bookings").select("id", count="exact").eq("status", "approved")
            )
            snap = f"**{approved}** booking{'s' if approved != 1 else ''} awaiting your confirmation"
        elif role in SERVICE_ROLES:
            snap = "Clearance queue ready"
    except Exception:
        snap = "Ready to assist"

    return (
        f"Hello **{name}**! I'm TTTI Guardian for the **{portal}**.\n\n"
        f"Snapshot: {snap}.\n\n"
        f"Ask me anything, or choose a suggestion below."
    )


def _trainer_unit_ids(db, uid: str) -> list:
    rows = _safe_data(db.table("class_units").select("unit_id").eq("trainer_id", uid))
    if not rows:
        rows = _safe_data(db.table("trainer_units").select("unit_id").eq("trainer_id", uid))
    return list({r["unit_id"] for r in rows if r.get("unit_id")})


def _trainer_class_rows(db, uid: str) -> list:
    rows = _safe_data(
        db.table("class_units")
        .select("class_id, unit_id, classes(id, name), units(id, code, name)")
        .eq("trainer_id", uid)
    )
    return rows


# ── Student ───────────────────────────────────────────────────────────────────

def _student(db, uid, kw):
    def att():
        rows = _safe_data(db.table("attendance").select("status").eq("student_id", uid))
        total = len(rows)
        present = sum(1 for r in rows if r.get("status") == "present")
        pct = round(present / total * 100, 1) if total else 0
        return total, present, pct

    def docs():
        rows = _safe_data(
            db.table("student_personal_documents").select("document_type, status").eq("student_id", uid)
        )
        return {r["document_type"]: r.get("status", "uploaded") for r in rows}

    def poe():
        rows = _safe_data(db.table("assessments").select("status").eq("student_id", uid))
        total = len(rows)
        return (
            total,
            sum(1 for r in rows if r.get("status") == "approved"),
            sum(1 for r in rows if r.get("status") == "pending"),
            sum(1 for r in rows if r.get("status") == "rejected"),
        )

    def clearance():
        rows = _safe_data(
            db.table("clearance_requests").select("status, stage")
            .eq("student_id", uid).order("created_at", desc=True).limit(1)
        )
        return rows[0] if rows else None

    def exam_bookings():
        return _safe_data(
            db.table("exam_bookings")
            .select("status, serial_number, exam_session, units(name, code)")
            .eq("student_id", uid).order("created_at", desc=True).limit(8)
        )

    def formative_marks():
        fm = _safe_data(
            db.table("formative_marks")
            .select("marks_obtained, assessment_id")
            .eq("student_id", uid)
        )
        if not fm:
            return []
        a_ids = list({m["assessment_id"] for m in fm if m.get("assessment_id")})
        assessments = {
            a["id"]: a for a in _safe_data(
                db.table("formative_assessments")
                .select("id, assessment_name, assessment_type, max_marks, units(name, code)")
                .in_("id", a_ids)
            )
        }
        out = []
        for m in fm:
            fa = assessments.get(m.get("assessment_id")) or {}
            out.append({
                "marks_obtained": m.get("marks_obtained"),
                "formative_assessments": fa,
            })
        return out

    def attachment():
        rows = _safe_data(
            db.table("industrial_attachments")
            .select("status, companies(name)")
            .eq("student_id", uid).order("created_at", desc=True).limit(1)
        )
        return rows[0] if rows else None

    def logbook_count():
        return len(_safe_data(db.table("digital_logbook").select("id").eq("student_id", uid)))

    def my_units():
        enr = _safe_data(db.table("enrollments").select("class_id").eq("student_id", uid))
        if not enr:
            return []
        class_ids = list({e["class_id"] for e in enr if e.get("class_id")})
        cu = _safe_data(
            db.table("class_units").select("units(name, code)").in_("class_id", class_ids)
        )
        seen = set()
        out = []
        for r in cu:
            u = r.get("units") or {}
            key = u.get("code") or u.get("name")
            if key and key not in seen:
                seen.add(key)
                out.append(u)
        return out

    def employment():
        rows = _safe_data(
            db.table("employment_tracking")
            .select("employment_status, company_name, job_title")
            .eq("student_id", uid).limit(1)
        )
        return rows[0] if rows else None

    if _matches(kw, "attend", "present", "absent", "lesson", "75%"):
        total, present, pct = att()
        if total == 0:
            return "You have no attendance records yet. Your trainer marks each lesson under **Lesson Attendance** (`/student/attendance`)."
        tip = "" if pct >= 75 else " You need **≥75%** to book exams — speak to your trainer."
        standing = "Good standing" if pct >= 75 else "Below threshold"
        return f"Your attendance: **{present}/{total}** lessons = **{pct}%** ({standing}).{tip}"

    if _matches(kw, "poe", "portfolio", "assessment", "evidence", "upload poe"):
        total, approved, pending, rejected = poe()
        if total == 0:
            return (
                "No POE uploads yet. Go to **Portfolio of Evidence** (`/student/portfolio`) "
                "or **My Assessments** (`/student/assessments`) to upload scripts and evidence."
            )
        parts = [f"Total: **{total}**"]
        if approved:
            parts.append(f"**{approved}** approved")
        if pending:
            parts.append(f"**{pending}** pending review")
        if rejected:
            parts.append(f"**{rejected}** need resubmission")
        hint = " Fix rejected items and re-upload." if rejected else ""
        return "Your POE status — " + ", ".join(parts) + "." + hint

    if _matches(kw, "exam", "book", "booking", "examination", "form 1a"):
        total, present, pct = att()
        d = docs()
        required = ["national_id", "birth_certificate", "kcse_certificate", "passport_photo"]
        missing = [r.replace("_", " ").title() for r in required if r not in d]
        issues = []
        if total == 0:
            issues.append("no attendance records")
        elif pct < 75:
            issues.append(f"attendance {pct}% (need ≥75%)")
        if missing:
            issues.append("missing docs: " + ", ".join(missing))
        if issues:
            return (
                "Not ready to book yet — " + "; ".join(issues) + ".\n"
                "Upload docs via **My Documents** (`/student/documents`), then open "
                "**Exam Booking Form** (`/student/exam-booking-form`)."
            )
        bk = exam_bookings()
        if not bk:
            return (
                "You look eligible. Open **Exam Booking Form** (`/student/exam-booking-form`).\n"
                "Flow: submit Form 1A → print for HOD signature → HOD approves online → "
                "Examination Office confirms → status **Completed**. Track at `/student/exam-bookings`."
            )
        lines = []
        for b in bk:
            unit = (b.get("units") or {}).get("name") or (b.get("units") or {}).get("code") or "Unit"
            st = b.get("status", "pending")
            sn = b.get("serial_number") or ""
            lines.append(f"{unit}: **{st}**" + (f" ({sn})" if sn else ""))
        return "Your exam bookings:\n" + "\n".join("• " + l for l in lines) + "\n\nOpen `/student/exam-bookings` for details."

    if _matches(kw, "clear", "clearance"):
        cl = clearance()
        if not cl:
            return (
                "No clearance application yet. Start at **Course Clearance** (`/clearance/`). "
                "Stages: service/trainers approvals → Home HOD → certificate with serial & QR."
            )
        return f"Clearance stage: **{cl.get('stage', '—')}**, status: **{cl.get('status', '—')}**. Continue at `/clearance/`."

    if _matches(kw, "document", "national id", "birth", "kcse", "passport", "certif", "my document"):
        d = docs()
        required = ["national_id", "birth_certificate", "kcse_certificate", "passport_photo"]
        missing = [r.replace("_", " ").title() for r in required if r not in d]
        uploaded = [r.replace("_", " ").title() for r in required if r in d]
        if missing:
            return (
                f"Uploaded: {', '.join(uploaded) or 'none'}.\n"
                f"Missing: {', '.join(missing)}.\n"
                f"Upload via **My Documents** (`/student/documents`)."
            )
        return "All 4 required documents are on file.\n" + "\n".join(
            f"• {r.replace('_', ' ').title()}: {d[r]}" for r in required
        )

    if _matches(kw, "attach", "industry", "company", "placement", "industrial", "intern"):
        a = attachment()
        if not a:
            return "No industrial attachment yet. Apply under **Attachment Placement** (`/student/industrial-attachment`)."
        co = (a.get("companies") or {}).get("name") or "your company"
        st = {
            "pending": "Submitted (awaiting liaison/HOD review)",
            "approved": "Approved (awaiting start)",
            "active": "Active",
            "completed": "Completed",
            "rejected": "Rejected",
            "terminated": "Terminated",
        }.get(a.get("status", ""), a.get("status", ""))
        return f"Industrial Attachment at **{co}** — {st}."

    if _matches(kw, "logbook", "log book", "diary"):
        a = attachment()
        if not a:
            return "Logbook is for trainees on industrial attachment. Apply under `/student/industrial-attachment` first."
        if a.get("status") != "active":
            return f"Your attachment status is **{a.get('status', '')}**. Logbook opens when status becomes **active** (`/student/logbook`)."
        count = logbook_count()
        return f"You have **{count}** logbook entr{'y' if count == 1 else 'ies'}. Add more at `/student/logbook`."

    if _matches(kw, "mark", "grade", "score", "result", "transcript", "formative"):
        m = formative_marks()
        if not m:
            return (
                "No formative marks yet. Trainers enter them under **Marks Entry**. "
                "When available they appear in **Marks & Transcripts** (`/student/marks`)."
            )
        lines = []
        for r in m[:10]:
            fa = r.get("formative_assessments") or {}
            u = fa.get("units") or {}
            name = fa.get("assessment_name") or fa.get("assessment_type") or "Assessment"
            unit = u.get("code") or u.get("name") or ""
            score = r.get("marks_obtained", "—")
            mx = fa.get("max_marks") or 100
            lines.append(f"{unit} {name}: **{score}/{mx}**".strip())
        return "Your formative marks:\n" + "\n".join("• " + l for l in lines) + "\n\nFull list: `/student/marks`"

    if _matches(kw, "unit", "units", "subject", "enrol", "my unit", "course subject"):
        units = my_units()
        if not units:
            return "You are not enrolled in any class/units yet. Contact your department admin."
        names = [f"{u.get('code') or '—'} — {u.get('name') or 'Unit'}" for u in units]
        return f"You have **{len(units)}** unit{'s' if len(units) != 1 else ''}:\n" + "\n".join("• " + n for n in names[:15]) + "\n\n`/student/units`"

    if _matches(kw, "employment", "employed", "job", "career", "work status", "after training"):
        emp = employment()
        if not emp:
            return "No employment record yet. After training, update **Employment Status** (`/student/employment-status`)."
        st = emp.get("employment_status", "")
        if st == "employed":
            return f"Recorded as employed at **{emp.get('company_name') or 'a company'}** as **{emp.get('job_title') or 'a role'}**."
        if st == "self_employed":
            return "Status: **self-employed**. Update details at `/student/employment-status`."
        if st == "unemployed":
            return "Status: **seeking employment**. Update when this changes at `/student/employment-status`."
        return f"Employment status: **{st}**. Manage at `/student/employment-status`."

    if _matches(kw, "profile", "phone", "email", "admission"):
        return "Update your profile at `/auth/profile`. Login ID for trainees is your **admission number**."

    total, present, pct = att()
    total_p, approved_p, _, _ = poe()
    units = my_units()
    att_info = f"Attendance **{pct}%**" if total else "No attendance yet"
    poe_info = f"POE **{total_p}** ({approved_p} approved)" if total_p else "No POE yet"
    unit_info = f"**{len(units)}** units" if units else "No units yet"
    return (
        "I can help with units, attendance, formative marks, POE, exam booking, clearance, "
        "attachment, logbook, and employment.\n\n"
        f"Snapshot — {att_info} | {poe_info} | {unit_info}.\n"
        "What would you like to know?"
    )


# ── Dept Admin ────────────────────────────────────────────────────────────────

def _dept_admin(db, uid, user, kw):
    dept_id = user.get("department_id")

    def stats():
        if not dept_id:
            return {}
        return {
            "trainers": _count(db.table("user_profiles").select("id", count="exact").eq("role", "trainer").eq("department_id", dept_id)),
            "students": _count(db.table("user_profiles").select("id", count="exact").eq("role", "student").eq("department_id", dept_id)),
            "classes": _count(db.table("classes").select("id", count="exact").eq("department_id", dept_id)),
        }

    def pending_poe():
        if not dept_id:
            return 0
        return len(_safe_data(
            db.table("assessments").select("id, units!inner(department_id)")
            .eq("units.department_id", dept_id).eq("status", "pending")
        ))

    def pending_exams():
        if not dept_id:
            return 0
        return len(_safe_data(
            db.table("exam_bookings").select("id, units!inner(department_id)")
            .eq("units.department_id", dept_id).eq("status", "pending")
        ))

    def pending_clearances():
        if not dept_id:
            return 0
        return len(_safe_data(
            db.table("clearance_requests").select("id")
            .eq("department_id", dept_id).eq("status", "pending")
        ))

    if _matches(kw, "overview", "stat", "summary", "dashboard", "how many", "count", "total"):
        s = stats()
        return (
            f"**Department overview:**\n"
            f"• Trainers: **{s.get('trainers', 0)}**\n"
            f"• Trainees: **{s.get('students', 0)}**\n"
            f"• Classes: **{s.get('classes', 0)}**\n"
            f"• Pending POE: **{pending_poe()}**\n"
            f"• Pending exam bookings: **{pending_exams()}**\n\n"
            f"Dashboard: `/dept-admin/dashboard`"
        )

    if _matches(kw, "poe", "assessment", "portfolio", "trainee poe"):
        pp = pending_poe()
        if pp == 0:
            return "No pending trainee POE in your department. Browse `/dept-admin/trainee-poe`."
        return f"**{pp}** pending trainee POE submission{'s' if pp != 1 else ''}. Review at `/dept-admin/trainee-poe`."

    if _matches(kw, "exam", "booking", "book", "examination", "form 1a"):
        pe = pending_exams()
        return (
            f"**{pe}** pending Form 1A booking{'s' if pe != 1 else ''} for HOD approval.\n"
            f"Open `/dept-admin/exam-bookings`. After you approve, Examination Office confirms → **Completed**.\n"
            f"Tip: use **All** to approve every unit on the same serial."
        )

    if _matches(kw, "clear", "clearance"):
        pc = pending_clearances()
        return f"**{pc}** clearance request{'s' if pc != 1 else ''} pending. Review via `/clearance/approver`."

    if _matches(kw, "attend", "present", "absent"):
        return "Search trainee attendance under **Attendance Search** (`/dept-admin/trainee-search`)."

    if _matches(kw, "credential", "password", "reset"):
        return (
            "Open **Manage Credentials** (`/dept-admin/credentials`). "
            "Search trainer (email) or trainee (admission no), then **Set** or **Reset** password."
        )

    if _matches(kw, "mark", "formative", "summative", "grade"):
        return (
            "Formative marks reports: `/dept-admin/marks`. "
            "Summative portal: `/summative/`. Trainers enter formative marks under Marks Entry."
        )

    if _matches(kw, "trainee", "student", "class"):
        s = stats()
        return f"**{s.get('students', 0)}** trainees across **{s.get('classes', 0)}** classes. Manage via sidebar Classes / Trainees menus."

    if _matches(kw, "trainer", "staff", "lecturer"):
        s = stats()
        return f"**{s.get('trainers', 0)}** trainer{'s' if s.get('trainers', 0) != 1 else ''} in your department. See Trainers / Trainer POE in the sidebar."

    s = stats()
    return (
        f"I can help with department stats, POE, exam bookings, clearance, credentials, and marks.\n"
        f"Quick — **{s.get('students', 0)}** trainees | **{pending_poe()}** POE | **{pending_exams()}** exams pending."
    )


# ── Trainer ───────────────────────────────────────────────────────────────────

def _trainer(db, uid, kw):
    unit_ids = _trainer_unit_ids(db, uid)
    cu_rows = _trainer_class_rows(db, uid)

    def class_list():
        cmap = {}
        for r in cu_rows:
            c = r.get("classes") or {}
            if c.get("id"):
                cmap[c["id"]] = c.get("name") or "Class"
        return sorted(cmap.values())

    def unit_list():
        ulist = []
        seen = set()
        for r in cu_rows:
            u = r.get("units") or {}
            key = u.get("id") or u.get("code")
            if key and key not in seen:
                seen.add(key)
                ulist.append(u)
        return ulist

    def pending_poe():
        if not unit_ids:
            return 0
        return len(_safe_data(
            db.table("assessments").select("id").in_("unit_id", unit_ids).eq("status", "pending")
        ))

    def assessment_stats():
        if not unit_ids:
            return 0, 0, 0, 0
        rows = _safe_data(db.table("assessments").select("status").in_("unit_id", unit_ids))
        total = len(rows)
        pending = sum(1 for r in rows if r.get("status") == "pending")
        approved = sum(1 for r in rows if r.get("status") == "approved")
        rejected = sum(1 for r in rows if r.get("status") == "rejected")
        return total, pending, approved, rejected

    if _matches(kw, "overview", "summary", "dashboard", "snapshot"):
        total, pending, approved, rejected = assessment_stats()
        classes = class_list()
        units = unit_list()
        return (
            f"**Trainer snapshot:**\n"
            f"• Classes: **{len(classes)}**\n"
            f"• Units: **{len(units)}**\n"
            f"• POE: **{total}** total (**{pending}** pending, **{approved}** approved, **{rejected}** rejected)\n\n"
            f"Dashboard: `/trainer/dashboard`"
        )

    if _matches(kw, "unit", "units", "assigned unit", "my unit"):
        units = unit_list()
        if not units:
            return "No units assigned yet. Ask your HOD to assign you in class–unit mapping."
        lines = [f"{u.get('code', '—')} — {u.get('name', '—')}" for u in units[:15]]
        return f"Your units (**{len(units)}**):\n" + "\n".join("• " + l for l in lines)

    if _matches(kw, "class", "my class", "assigned", "teach", "trainee"):
        classes = class_list()
        if not classes:
            return "No classes linked to you yet via **class_units**. Contact your department admin."
        return f"Your classes (**{len(classes)}**):\n" + "\n".join("• " + n for n in classes)

    if _matches(kw, "poe", "assessment", "review", "pending", "portfolio", "script"):
        pp = pending_poe()
        if pp == 0:
            return "No pending POE for your units. Browse `/trainer/assessments` anytime."
        return (
            f"**{pp}** POE file{'s' if pp != 1 else ''} awaiting review. "
            f"Open **Trainee POE Review** (`/trainer/assessments`). "
            f"Marks shown beside each file come from **Marks Entry**."
        )

    if _matches(kw, "attend", "present", "absent", "lesson", "biometric", "fingerprint"):
        if _matches(kw, "biometric", "fingerprint"):
            return "Start a biometric session from **Biometric Attendance** in the trainer sidebar."
        return "Mark lesson attendance under **Mark Attendance** (`/trainer/attendance`)."

    if _matches(kw, "mark", "grade", "score", "marks entry", "import mark", "formative", "oral", "practical", "theory"):
        return (
            "Enter formative marks in **Marks Entry** (`/trainer/marks-entry`). "
            "Select class → unit → term, add Oral / Practical / Theory assessments, then type scores "
            "(they auto-save). Those same marks appear beside trainee POE files for approval."
        )

    if _matches(kw, "exam", "booking", "examination"):
        return (
            "Exam booking approval is done by the **HOD** (Dept Admin), then confirmed by the "
            "**Examination Officer**. Trainers focus on attendance, POE review, and Marks Entry."
        )

    if _matches(kw, "clear", "clearance"):
        return "Review clearance items under **Clearance Approvals** in the trainer sidebar."

    if _matches(kw, "portfolio", "my document", "trainer document"):
        return "Upload trainer documents via **My Portfolio (POE)** in the sidebar."

    pp = pending_poe()
    classes = class_list()
    units = unit_list()
    return (
        f"I can help with classes, units, POE review, attendance, and Marks Entry.\n"
        f"Quick — **{len(classes)}** classes | **{len(units)}** units | **{pp}** pending POE."
    )


# ── Super Admin ───────────────────────────────────────────────────────────────

def _super_admin(db, kw):
    def system_stats():
        return {
            "students": _count(db.table("user_profiles").select("id", count="exact").eq("role", "student")),
            "trainers": _count(db.table("user_profiles").select("id", count="exact").eq("role", "trainer")),
            "dept_admins": _count(db.table("user_profiles").select("id", count="exact").eq("role", "dept_admin")),
            "departments": _count(db.table("departments").select("id", count="exact")),
            "classes": _count(db.table("classes").select("id", count="exact")),
        }

    def pending_items():
        return {
            "poe": _count(db.table("assessments").select("id", count="exact").eq("status", "pending")),
            "exams": _count(db.table("exam_bookings").select("id", count="exact").eq("status", "pending")),
            "clearance": _count(db.table("clearance_requests").select("id", count="exact").eq("status", "pending")),
            "exams_approved": _count(db.table("exam_bookings").select("id", count="exact").eq("status", "approved")),
        }

    if _matches(kw, "overview", "stat", "summary", "system", "total", "how many", "count"):
        s = system_stats()
        p = pending_items()
        return (
            f"**System overview:**\n"
            f"• Trainees: **{s.get('students', 0)}**\n"
            f"• Trainers: **{s.get('trainers', 0)}**\n"
            f"• Dept Admins: **{s.get('dept_admins', 0)}**\n"
            f"• Departments: **{s.get('departments', 0)}**\n"
            f"• Classes: **{s.get('classes', 0)}**\n"
            f"• Pending POE: **{p.get('poe', 0)}**\n"
            f"• Pending exam bookings: **{p.get('exams', 0)}**\n"
            f"• Approved (awaiting exam office): **{p.get('exams_approved', 0)}**"
        )

    if _matches(kw, "pending", "review", "approval", "waiting"):
        p = pending_items()
        return (
            f"**Pending system-wide:**\n"
            f"• POE: **{p.get('poe', 0)}**\n"
            f"• Exam bookings (HOD): **{p.get('exams', 0)}**\n"
            f"• Exam bookings (exam office queue): **{p.get('exams_approved', 0)}**\n"
            f"• Clearances: **{p.get('clearance', 0)}**\n\n"
            f"Exam oversight: `/super-admin/exam-bookings`"
        )

    if _matches(kw, "exam", "booking"):
        p = pending_items()
        return (
            f"Exam bookings — pending HOD: **{p.get('exams', 0)}** | "
            f"approved awaiting confirmation: **{p.get('exams_approved', 0)}**.\n"
            f"Oversight UI: `/super-admin/exam-bookings` (export + PDF available)."
        )

    if _matches(kw, "user", "student", "trainee", "trainer", "staff", "account"):
        s = system_stats()
        return (
            f"Users — trainees **{s.get('students', 0)}**, trainers **{s.get('trainers', 0)}**, "
            f"dept admins **{s.get('dept_admins', 0)}**. Manage via Users / Credentials menus."
        )

    if _matches(kw, "credential", "password", "reset"):
        return "Institute-wide password resets: `/super-admin/credentials`."

    if _matches(kw, "department", "dept"):
        s = system_stats()
        return f"**{s.get('departments', 0)}** departments registered. Manage under Departments."

    if _matches(kw, "log", "audit"):
        return "Open System / Audit Logs from the Super Admin sidebar."

    if _matches(kw, "import", "bulk", "csv", "excel"):
        return "Bulk import users/data from the Data Import menu in Super Admin."

    s = system_stats()
    p = pending_items()
    return (
        f"I cover system stats, pending queues, users, credentials, and exam oversight.\n"
        f"Quick — **{s.get('students', 0)}** trainees | **{p.get('poe', 0)}** POE pending | **{p.get('exams', 0)}** exams pending."
    )


# ── Examination Officer ───────────────────────────────────────────────────────

def _exam_officer(db, kw):
    def counts():
        return {
            "pending": _count(db.table("exam_bookings").select("id", count="exact").eq("status", "pending")),
            "approved": _count(db.table("exam_bookings").select("id", count="exact").eq("status", "approved")),
            "completed": _count(db.table("exam_bookings").select("id", count="exact").eq("status", "completed")),
            "rejected": _count(db.table("exam_bookings").select("id", count="exact").eq("status", "rejected")),
        }

    c = counts()
    if _matches(kw, "confirm", "approved", "awaiting", "ready", "to confirm"):
        a = c.get("approved", 0)
        if a == 0:
            return "No HOD-approved bookings waiting. Check `/examination-officer/exam-bookings` after HODs approve."
        return (
            f"**{a}** approved booking{'s' if a != 1 else ''} await your confirmation.\n"
            f"Open `/examination-officer/exam-bookings` → **Confirm** (sets status to **Completed**)."
        )

    if _matches(kw, "complete", "completed", "done", "confirmed"):
        return f"**{c.get('completed', 0)}** exam booking{'s' if c.get('completed', 0) != 1 else ''} marked completed."

    if _matches(kw, "pending", "hod", "waiting"):
        return (
            f"**{c.get('pending', 0)}** still pending HOD approval "
            f"(you only confirm after status is **approved**)."
        )

    if _matches(kw, "stat", "summary", "overview", "total", "exam", "booking"):
        return (
            f"**Exam booking overview:**\n"
            f"• Pending HOD: **{c.get('pending', 0)}**\n"
            f"• Approved (your queue): **{c.get('approved', 0)}**\n"
            f"• Completed: **{c.get('completed', 0)}**\n"
            f"• Rejected: **{c.get('rejected', 0)}**\n\n"
            f"Workflow: Trainee → HOD approve → you Confirm → Completed."
        )

    return (
        f"I track exam booking confirmation.\n"
        f"Queue — **{c.get('approved', 0)}** to confirm | **{c.get('completed', 0)}** completed.\n"
        f"`/examination-officer/exam-bookings`"
    )


# ── Industry Mentor ───────────────────────────────────────────────────────────

def _industry_mentor(db, uid, kw):
    mentor_rows = _safe_data(db.table("mentors").select("id, company_id").eq("user_id", uid).limit(1))
    mentor = mentor_rows[0] if mentor_rows else None
    if not mentor:
        return "No mentor company profile linked to your account. Contact the liaison officer or admin."

    company_id = mentor.get("company_id")
    attachments = _safe_data(
        db.table("industrial_attachments")
        .select("id, status, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no)")
        .eq("company_id", company_id)
        .eq("status", "active")
    ) if company_id else []

    if _matches(kw, "trainee", "student", "attach", "placement", "active"):
        if not attachments:
            return "No active trainees at your company right now."
        names = []
        for t in attachments[:10]:
            p = t.get("user_profiles") or {}
            names.append(p.get("full_name") or p.get("admission_no") or "Trainee")
        return f"**{len(attachments)}** active trainee{'s' if len(attachments) != 1 else ''}:\n" + "\n".join("• " + n for n in names)

    if _matches(kw, "logbook", "log", "diary"):
        pending = _safe_data(
            db.table("digital_logbook").select("id, attachment_id").eq("mentor_approval_status", "pending")
        )
        # Filter to this company's attachments
        att_ids = {a["id"] for a in _safe_data(
            db.table("industrial_attachments").select("id").eq("company_id", company_id)
        )} if company_id else set()
        count = sum(1 for l in pending if l.get("attachment_id") in att_ids)
        return f"**{count}** logbook entr{'y' if count == 1 else 'ies'} awaiting mentor approval. Open Logbooks in your portal."

    return (
        f"I can list active attachment trainees and pending logbooks for your company.\n"
        f"Active trainees: **{len(attachments)}**."
    )


# ── Internal Verifier ─────────────────────────────────────────────────────────

def _internal_verifier(db, kw):
    pending = _count(db.table("assessments").select("id", count="exact").eq("status", "pending"))
    approved = _count(db.table("assessments").select("id", count="exact").eq("status", "approved"))
    if _matches(kw, "pending", "review", "verify", "assessment", "poe"):
        if pending == 0:
            return "No assessments pending verification right now."
        return f"**{pending}** assessment{'s' if pending != 1 else ''} pending. Use Assessments in the Internal Verifier sidebar."
    if _matches(kw, "stat", "summary", "overview"):
        return f"Assessments — Pending: **{pending}** | Approved: **{approved}**."
    return f"Verification queue — **{pending}** pending. Ask about pending items or stats."


# ── Liaison Officer ───────────────────────────────────────────────────────────

def _liaison(db, kw):
    pending = _count(db.table("industrial_attachments").select("id", count="exact").eq("status", "pending"))
    active = _count(db.table("industrial_attachments").select("id", count="exact").eq("status", "active"))
    companies = _count(db.table("companies").select("id", count="exact"))
    if _matches(kw, "placement", "attach", "pending", "application"):
        return (
            f"**{pending}** placement{'s' if pending != 1 else ''} pending review; "
            f"**{active}** active. Open `/liaison-officer/attachments`."
        )
    if _matches(kw, "compan", "partner", "industry"):
        return f"**{companies}** industry partners registered. Manage at `/liaison-officer/companies`."
    if _matches(kw, "logbook", "log"):
        return "Review trainee logbooks under **Logbooks** (`/liaison-officer/logbooks`)."
    if _matches(kw, "mark", "grade", "attachment mark"):
        return "Attachment marks: `/liaison-officer/attachment-marks`."
    return (
        f"Liaison overview — pending placements **{pending}**, active **{active}**, companies **{companies}**.\n"
        f"Dashboard: `/liaison-officer/dashboard`"
    )


# ── Workshop Technician ───────────────────────────────────────────────────────

def _workshop(db, user, kw):
    dept_id = user.get("department_id")
    uid = user.get("id")
    inv = _safe_data(db.table("workshop_inventory").select("id, quantity, condition").eq("department_id", dept_id)) if dept_id else []
    low = sum(1 for i in inv if (i.get("quantity") or 0) < 3)
    damaged = sum(1 for i in inv if i.get("condition") in ("poor", "damaged"))
    pending = _count(
        db.table("clearance_approvals").select("id", count="exact")
        .eq("approver_id", uid).eq("status", "pending")
    ) if uid else 0

    if _matches(kw, "inventor", "stock", "item", "tool", "equipment"):
        return (
            f"Workshop inventory — **{len(inv)}** items, **{low}** low stock, **{damaged}** damaged/poor.\n"
            f"Manage at `/workshop-technician/inventory`."
        )
    if _matches(kw, "clear", "clearance"):
        return f"**{pending}** clearance approval{'s' if pending != 1 else ''} assigned to you. Open `/workshop-technician/clearances`."
    return (
        f"Workshop snapshot — **{len(inv)}** inventory items | **{pending}** clearances pending.\n"
        f"`/workshop-technician/dashboard`"
    )


# ── CDACC Verifier ────────────────────────────────────────────────────────────

def _cdacc(db, kw):
    pending = _count(db.table("assessments").select("id", count="exact").eq("status", "pending"))
    if _matches(kw, "pending", "verify", "assessment", "poe"):
        return (
            f"**{pending}** assessment{'s' if pending != 1 else ''} in pending status. "
            f"Use CDACC Assessments / Trainee POE menus (`/cdacc-verifier/`)."
        )
    if _matches(kw, "mark", "formative", "grade"):
        return "View formative marks under **Marks** in the CDACC verifier sidebar (`/cdacc-verifier/marks`)."
    if _matches(kw, "attach", "logbook", "mentor"):
        return "Attachment marks, mentoring tools, and logbooks are available from the CDACC verifier sidebar."
    return (
        f"CDACC Guardian can summarise verification queues and where to find marks/POE.\n"
        f"Pending assessments (system): **{pending}**."
    )


# ── Service departments ───────────────────────────────────────────────────────

def _service_dept(db, user, kw):
    uid = user.get("id")
    role = (user.get("role") or "").replace("_", " ").title()
    pending = _count(
        db.table("clearance_approvals").select("id", count="exact")
        .eq("approver_id", uid).eq("status", "pending")
    ) if uid else 0
    if _matches(kw, "clear", "clearance", "pending"):
        return (
            f"**{pending}** clearance item{'s' if pending != 1 else ''} pending for your role ({role}).\n"
            f"Open `/clearance/service-dept` or `/service-dept/`."
        )
    if _matches(kw, "lost", "found", "item"):
        return "Manage lost & found items from your service department dashboard (`/service-dept/`)."
    return (
        f"As **{role}**, focus on clearance approvals and your dashboard tools.\n"
        f"Pending clearances: **{pending}**. Portal: `/service-dept/`"
    )


# ── Generic ───────────────────────────────────────────────────────────────────

def _generic(role, kw):
    role_label = ROLE_PORTALS.get(role, role.replace("_", " ").title())
    return (
        f"I'm TTTI Guardian for the **{role_label}**.\n"
        f"Use the sidebar menus for your tasks, or ask about pending items and how to navigate.\n"
        f"Type **help** for a guided list."
    )
