"""
routes/ai.py — Shared TTTI Guardian AI Assistant endpoint.
Serves all roles: student, trainer, dept_admin, super_admin,
examination_officer, industry_mentor, internal_verifier, and others.
"""

from flask import Blueprint, request, jsonify
from auth_utils import login_required, current_user
from db import get_service_client

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/api/ai-ask", methods=["POST"])
@login_required
def ai_ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("q") or "").strip().lower()
    if not question:
        return jsonify({"reply": "Please type a question so I can help you."})

    user = current_user()
    role = (user.get("role") or "").lower()
    uid  = user["id"]
    db   = get_service_client()

    # ── Route to role-specific handler ───────────────────────────────────────
    if role == "student":
        return jsonify({"reply": _student(db, uid, question)})
    elif role == "dept_admin":
        return jsonify({"reply": _dept_admin(db, uid, user, question)})
    elif role == "trainer":
        return jsonify({"reply": _trainer(db, uid, question)})
    elif role == "super_admin":
        return jsonify({"reply": _super_admin(db, question)})
    elif role == "examination_officer":
        return jsonify({"reply": _exam_officer(db, question)})
    elif role == "industry_mentor":
        return jsonify({"reply": _industry_mentor(db, uid, question)})
    elif role == "internal_verifier":
        return jsonify({"reply": _internal_verifier(db, question)})
    else:
        return jsonify({"reply": _generic(role, question)})


# ── Student ───────────────────────────────────────────────────────────────────

def _student(db, uid, kw):
    def att():
        rows = db.table("attendance").select("status").eq("student_id", uid).execute().data or []
        total = len(rows)
        present = sum(1 for r in rows if r.get("status") == "present")
        pct = round(present / total * 100, 1) if total else 0
        return total, present, pct

    def docs():
        rows = db.table("student_personal_documents").select("document_type, status").eq("student_id", uid).execute().data or []
        return {r["document_type"]: r.get("status", "uploaded") for r in rows}

    def poe():
        rows = db.table("assessments").select("status").eq("student_id", uid).execute().data or []
        total = len(rows)
        return total, sum(1 for r in rows if r.get("status") == "approved"), \
               sum(1 for r in rows if r.get("status") == "pending"), \
               sum(1 for r in rows if r.get("status") == "rejected")

    def clearance():
        rows = db.table("clearance_requests").select("status, stage").eq("student_id", uid).order("created_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None

    def exam_bookings():
        return db.table("exam_bookings").select("status, units(name, code)").eq("student_id", uid).order("created_at", desc=True).limit(5).execute().data or []

    def marks():
        return db.table("marks").select("marks_obtained, grade, units(name, code)").eq("student_id", uid).order("created_at", desc=True).execute().data or []

    def attachment():
        rows = db.table("industrial_attachments").select("status, companies(name)").eq("student_id", uid).order("created_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None

    def logbook_count():
        return len(db.table("digital_logbook").select("id").eq("student_id", uid).execute().data or [])

    def my_units():
        rows = db.table("enrollments").select("id, units(name, code)").eq("student_id", uid).execute().data or []
        return rows

    def employment():
        rows = db.table("employment_tracking").select("employment_status, company_name, job_title").eq("student_id", uid).execute().data or []
        return rows[0] if rows else None

    # Attendance
    if any(x in kw for x in ("attend", "present", "absent", "lesson", "75")):
        total, present, pct = att()
        if total == 0:
            return "You have no attendance records yet. Your trainer marks attendance each lesson."
        tip = "" if pct >= 75 else " You must reach 75% to book exams — speak to your trainer immediately."
        return f"Your attendance: {present}/{total} lessons = {pct}% ({'Good standing' if pct >= 75 else 'Below threshold'}).{tip}"

    # POE
    if any(x in kw for x in ("poe", "portfolio", "assessment", "upload", "evidence", "submit")):
        total, approved, pending, rejected = poe()
        if total == 0:
            return "You haven't uploaded any POE yet. Go to Upload POE in the sidebar, select your unit, fill in task details, and attach evidence files."
        parts = [f"Total: {total}"]
        if approved: parts.append(f"{approved} approved")
        if pending:  parts.append(f"{pending} pending review")
        if rejected: parts.append(f"{rejected} need resubmission")
        hint = " Check the rejected ones and resubmit with corrections." if rejected else ""
        return "Your POE status — " + ", ".join(parts) + "." + hint

    # Exam booking
    if any(x in kw for x in ("exam", "book", "booking", "examination")):
        total, present, pct = att()
        d = docs()
        required = ['national_id', 'birth_certificate', 'kcse_certificate', 'passport_photo']
        missing = [r.replace("_", " ").title() for r in required if r not in d]
        issues = []
        if total == 0: issues.append("no attendance records")
        elif pct < 75: issues.append(f"attendance {pct}% (need ≥75%)")
        if missing: issues.append("missing docs: " + ", ".join(missing))
        if issues:
            return "Cannot book exams yet — " + "; ".join(issues) + ". Fix these first via the sidebar."
        bk = exam_bookings()
        if not bk:
            return "You are eligible to book an exam. Go to Exam Booking Form in the sidebar. Your HOD approves first, then the Exam Officer confirms."
        lines = [f"{(b.get('units') or {}).get('name') or 'Unit'}: {b.get('status','pending')}" for b in bk]
        return "Your exam bookings:\n" + "\n".join("• " + l for l in lines)

    # Clearance
    if any(x in kw for x in ("clear", "clearance", "library", "finance", "games", "store")):
        cl = clearance()
        if not cl:
            return "You haven't applied for clearance yet. Go to Course Clearance in the sidebar. Clearance runs in 3 stages: Stage 1 (Trainers, Technicians, Service Depts & other HODs — all simultaneously), Stage 2 (Home HOD final review), Stage 3 (Certificate with serial number & QR code)."
        return f"Clearance stage: {cl.get('stage','—')}, status: {cl.get('status','—')}. Check the Clearance page for approver updates."

    # Documents
    if any(x in kw for x in ("document", "admit", "national id", "birth", "kcse", "passport", "certif")):
        d = docs()
        required = ['national_id', 'birth_certificate', 'kcse_certificate', 'passport_photo']
        missing = [r.replace("_", " ").title() for r in required if r not in d]
        uploaded = [r.replace("_", " ").title() for r in required if r in d]
        if missing:
            return f"Uploaded: {', '.join(uploaded) or 'none'}.\nMissing: {', '.join(missing)}.\nUpload via Admission Documents in the sidebar."
        return "All 4 required documents uploaded.\n" + "\n".join(f"• {r.replace('_',' ').title()}: {d[r]}" for r in required)

    # Attachment
    if any(x in kw for x in ("attach", "industry", "company", "placement", "industrial", "intern")):
        a = attachment()
        if not a:
            return "No industrial attachment record. Go to Industrial Attachment in the sidebar to submit a request."
        co = (a.get("companies") or {}).get("name") or "your company"
        st = {"pending": "Submitted (awaiting review)", "active": "Active", "completed": "Completed", "rejected": "Rejected"}.get(a.get("status", ""), a.get("status", ""))
        return f"Industrial Attachment at {co} — {st}."

    # Logbook
    if any(x in kw for x in ("logbook", "log book", "log entry", "diary")):
        a = attachment()
        if not a:
            return "Logbook is for students on active industrial attachment. Submit an attachment request first."
        if a.get("status") != "active":
            return f"Your attachment is '{a.get('status','')}'. Logbook is available once it becomes active."
        count = logbook_count()
        return f"You have {count} logbook {'entry' if count==1 else 'entries'}. Add new ones via Digital Logbook in the sidebar."

    # Marks
    if any(x in kw for x in ("mark", "grade", "score", "result", "pass", "fail")):
        m = marks()
        if not m:
            return "No marks recorded yet. Marks are entered by your trainer after assessments."
        lines = []
        for r in m[:8]:
            u = r.get("units") or {}
            name = u.get("name") or u.get("code") or "Unit"
            score = r.get("marks_obtained", "—")
            grade = r.get("grade") or ""
            lines.append(f"{name}: {score}" + (f" ({grade})" if grade else ""))
        return "Your recent marks:\n" + "\n".join("• " + l for l in lines)

    # My Units
    if any(x in kw for x in ("unit", "units", "subject", "enrol", "my unit", "course subject")):
        try:
            units = my_units()
            if not units:
                return "You are not enrolled in any units yet. Contact your department admin to get enrolled."
            names = [(u.get("units") or {}).get("name") or (u.get("units") or {}).get("code") or "Unit" for u in units]
            return f"You are enrolled in {len(units)} unit{'s' if len(units)!=1 else ''}:\n" + "\n".join("• " + n for n in names[:12])
        except Exception:
            return "Your enrolled units are listed under My Units in the sidebar."

    # Employment Status
    if any(x in kw for x in ("employment", "employed", "job", "career", "work status", "after training", "after course")):
        try:
            emp = employment()
            if not emp:
                return "No employment record found. After completing your course, update your post-training status via Employment Status in the sidebar."
            st = emp.get("employment_status", "")
            if st == "employed":
                co = emp.get("company_name") or "a company"
                jt = emp.get("job_title") or "a position"
                return f"You are recorded as employed at {co} as {jt}. Update via Employment Status in the sidebar if this changes."
            elif st == "self_employed":
                return "Your status shows as self-employed. Update details via Employment Status in the sidebar."
            elif st == "unemployed":
                return "Your status shows as seeking employment. Update it via Employment Status in the sidebar when your situation changes."
            return f"Employment status: {st}. Update it via Employment Status in the sidebar."
        except Exception:
            return "Check and update your post-training employment status via Employment Status in the sidebar."

    # Password / profile
    if any(x in kw for x in ("password", "profile", "phone", "email")):
        return "To update your profile or change your password, go to My Profile in the sidebar or click your name in the top bar."

    # Default
    try:
        total, present, pct = att()
        total_p, approved_p, _, _ = poe()
        units = my_units()
        att_info = f"Attendance: {pct}%" if total > 0 else "No attendance yet"
        poe_info = f"POE: {total_p} uploads ({approved_p} approved)" if total_p > 0 else "No POE uploaded yet"
        unit_info = f"{len(units)} unit{'s' if len(units)!=1 else ''} enrolled" if units else "No units yet"
        return (f"I can help with: My Units, Lesson Attendance, Marks & Transcripts, Portfolio of Evidence, "
                f"Assessments, Documents, Exam Booking, Industrial Attachment, Digital Logbook, Course Clearance, and Employment Status.\n"
                f"Your snapshot — {att_info} | {poe_info} | {unit_info}.\n"
                f"What would you like to know?")
    except Exception:
        return ("I can help with: My Units, Attendance, Marks, POE uploads, Exam Booking, Course Clearance, "
                "Industrial Attachment, Digital Logbook, and Employment Status. What would you like to know?")


# ── Dept Admin ────────────────────────────────────────────────────────────────

def _dept_admin(db, uid, user, kw):
    dept_id = user.get("department_id")

    def stats():
        if not dept_id:
            return {}
        try:
            return {
                "trainers":  db.table("user_profiles").select("id", count="exact").eq("role", "trainer").eq("department_id", dept_id).execute().count or 0,
                "students":  db.table("user_profiles").select("id", count="exact").eq("role", "student").eq("department_id", dept_id).execute().count or 0,
                "classes":   db.table("classes").select("id", count="exact").eq("department_id", dept_id).execute().count or 0,
            }
        except Exception:
            return {}

    def pending_poe():
        if not dept_id:
            return 0
        try:
            rows = db.table("assessments").select("id, units!inner(department_id)").eq("units.department_id", dept_id).eq("status", "pending").execute().data or []
            return len(rows)
        except Exception:
            return 0

    def pending_exams():
        if not dept_id:
            return 0
        try:
            rows = db.table("exam_bookings").select("id, units!inner(department_id)").eq("units.department_id", dept_id).eq("status", "pending").execute().data or []
            return len(rows)
        except Exception:
            return 0

    def pending_clearances():
        if not dept_id:
            return 0
        try:
            rows = db.table("clearance_requests").select("id").eq("department_id", dept_id).eq("status", "pending").execute().data or []
            return len(rows)
        except Exception:
            return 0

    def trainee_att():
        if not dept_id:
            return None
        try:
            # Get all students in dept
            students = db.table("user_profiles").select("id").eq("role", "student").eq("department_id", dept_id).execute().data or []
            if not students:
                return None
            sids = [s["id"] for s in students]
            att_rows = db.table("attendance").select("student_id, status").in_("student_id", sids).execute().data or []
            total = len(att_rows)
            present = sum(1 for r in att_rows if r.get("status") == "present")
            pct = round(present / total * 100, 1) if total else 0
            return len(students), total, present, pct
        except Exception:
            return None

    # Overview / stats
    if any(x in kw for x in ("overview", "stat", "summary", "dashboard", "how many", "count", "total")):
        s = stats()
        if not s:
            return "Your department overview: trainers, trainees, and classes. Check the Dashboard page for detailed statistics."
        pp = pending_poe()
        pe = pending_exams()
        return (f"Department overview:\n"
                f"• Trainers: {s.get('trainers',0)}\n"
                f"• Trainees: {s.get('students',0)}\n"
                f"• Classes: {s.get('classes',0)}\n"
                f"• Pending POE reviews: {pp}\n"
                f"• Pending exam bookings: {pe}")

    # POE / assessments
    if any(x in kw for x in ("poe", "assessment", "review", "pending", "portfolio", "upload")):
        pp = pending_poe()
        if pp == 0:
            return "No pending POE assessments in your department right now. All submissions are reviewed."
        return f"There are {pp} pending POE assessment{'s' if pp!=1 else ''} waiting for your review. Go to Assessments in the sidebar."

    # Exam bookings
    if any(x in kw for x in ("exam", "booking", "book", "examination")):
        pe = pending_exams()
        if pe == 0:
            return "No pending exam bookings in your department right now."
        return f"{pe} exam booking{'s' if pe!=1 else ''} pending your approval in the department. Go to Exam Bookings in the sidebar."

    # Clearance
    if any(x in kw for x in ("clear", "clearance")):
        pc = pending_clearances()
        if pc == 0:
            return "No pending clearance requests in your department."
        return f"{pc} clearance request{'s' if pc!=1 else ''} pending in your department. Review them via Course Clearance in the sidebar."

    # Attendance
    if any(x in kw for x in ("attend", "present", "absent", "lesson")):
        result = trainee_att()
        if not result:
            return "No attendance data available for your department yet."
        n_students, total, present, pct = result
        low = "some trainees may be below the 75% threshold — check the Attendance section." if pct < 80 else "attendance looks healthy overall."
        return f"Department attendance across {n_students} trainees: {present}/{total} lessons = {pct}% overall. {low.capitalize()}"

    # Trainees
    if any(x in kw for x in ("trainee", "student", "enrol", "class")):
        s = stats()
        if not s:
            return "Trainee data is available in the Trainees section of your dashboard."
        return f"Your department has {s.get('students',0)} enrolled trainees across {s.get('classes',0)} classes. View them in the Trainees section."

    # Trainers
    if any(x in kw for x in ("trainer", "staff", "lecturer", "teacher")):
        s = stats()
        return f"Your department has {s.get('trainers',0)} trainer{'s' if s.get('trainers',0)!=1 else ''} registered. Manage them via the Trainers section."

    # Default
    pp = pending_poe()
    pe = pending_exams()
    s  = stats()
    return (f"I can help with department overviews, pending POE reviews, exam bookings, clearance requests, attendance, and trainee management.\n"
            f"Quick summary — {s.get('students',0)} trainees | {pp} pending POE | {pe} pending exam bookings.\n"
            f"What would you like to know?")


# ── Trainer ───────────────────────────────────────────────────────────────────

def _trainer(db, uid, kw):
    def my_classes():
        rows = db.table("classes").select("id, name").eq("trainer_id", uid).execute().data or []
        return rows

    def pending_poe():
        try:
            classes = my_classes()
            if not classes:
                return 0
            cids = [c["id"] for c in classes]
            rows = db.table("assessments").select("id").in_("class_id", cids).eq("status", "pending").execute().data or []
            return len(rows)
        except Exception:
            return 0

    def att_summary():
        try:
            classes = my_classes()
            if not classes:
                return None
            cids = [c["id"] for c in classes]
            # Get enrollments for trainer's classes
            enrollments = db.table("enrollments").select("student_id").in_("class_id", cids).execute().data or []
            sids = list({e["student_id"] for e in enrollments})
            if not sids:
                return None
            att_rows = db.table("attendance").select("status").in_("student_id", sids).execute().data or []
            total = len(att_rows)
            present = sum(1 for r in att_rows if r.get("status") == "present")
            pct = round(present / total * 100, 1) if total else 0
            return len(sids), total, present, pct
        except Exception:
            return None

    def pending_exams():
        try:
            classes = my_classes()
            if not classes:
                return 0
            cids = [c["id"] for c in classes]
            rows = db.table("exam_bookings").select("id").in_("class_id", cids).eq("status", "pending").execute().data or []
            return len(rows)
        except Exception:
            return 0

    # Classes
    if any(x in kw for x in ("class", "unit", "my class", "assigned", "teach")):
        classes = my_classes()
        if not classes:
            return "You have no classes assigned yet. Contact your department admin."
        names = [c.get("name", "—") for c in classes]
        return f"Your assigned classes ({len(classes)}):\n" + "\n".join("• " + n for n in names)

    # POE reviews
    if any(x in kw for x in ("poe", "assessment", "review", "pending", "portfolio", "upload")):
        pp = pending_poe()
        if pp == 0:
            return "No pending POE assessments waiting for your review right now."
        return f"{pp} POE assessment{'s' if pp!=1 else ''} pending your review. Go to Assessments in the sidebar."

    # Attendance
    if any(x in kw for x in ("attend", "present", "absent", "lesson", "mark")):
        result = att_summary()
        if not result:
            return "No attendance data for your classes yet. Use Mark Attendance in the sidebar to record lessons."
        n_students, total, present, pct = result
        return f"Attendance across your {n_students} trainees: {present}/{total} lessons = {pct}% overall."

    # Exam bookings
    if any(x in kw for x in ("exam", "book", "booking", "examination")):
        pe = pending_exams()
        if pe == 0:
            return "No exam bookings pending your review for your classes."
        return f"{pe} exam booking{'s' if pe!=1 else ''} pending review for your classes. Check Exam Bookings in the sidebar."

    # Portfolio / trainer portfolio
    if any(x in kw for x in ("portfolio", "upload document", "trainer document", "my document")):
        return "To upload your professional documents, go to My Portfolio in the sidebar. Supported formats: PDF, images, and videos up to 20MB."

    # Default
    pp = pending_poe()
    classes = my_classes()
    return (f"I can help with your classes, pending POE reviews, attendance marking, exam bookings, and your portfolio.\n"
            f"Quick summary — {len(classes)} class{'es' if len(classes)!=1 else ''} | {pp} pending POE review{'s' if pp!=1 else ''}.\n"
            f"What would you like to know?")


# ── Super Admin ───────────────────────────────────────────────────────────────

def _super_admin(db, kw):
    def system_stats():
        try:
            return {
                "students":  db.table("user_profiles").select("id", count="exact").eq("role", "student").execute().count or 0,
                "trainers":  db.table("user_profiles").select("id", count="exact").eq("role", "trainer").execute().count or 0,
                "dept_admins": db.table("user_profiles").select("id", count="exact").eq("role", "dept_admin").execute().count or 0,
                "departments": db.table("departments").select("id", count="exact").execute().count or 0,
                "classes":   db.table("classes").select("id", count="exact").execute().count or 0,
            }
        except Exception:
            return {}

    def pending_items():
        try:
            return {
                "poe":      db.table("assessments").select("id", count="exact").eq("status", "pending").execute().count or 0,
                "exams":    db.table("exam_bookings").select("id", count="exact").eq("status", "pending").execute().count or 0,
                "clearance": db.table("clearance_requests").select("id", count="exact").eq("status", "pending").execute().count or 0,
            }
        except Exception:
            return {}

    # System overview
    if any(x in kw for x in ("overview", "stat", "summary", "system", "total", "how many", "count")):
        s = system_stats()
        p = pending_items()
        if not s:
            return "System stats are available on the Super Admin dashboard. Check the main dashboard page."
        return (f"System overview:\n"
                f"• Students: {s.get('students',0)}\n"
                f"• Trainers: {s.get('trainers',0)}\n"
                f"• Dept Admins: {s.get('dept_admins',0)}\n"
                f"• Departments: {s.get('departments',0)}\n"
                f"• Classes: {s.get('classes',0)}\n"
                f"• Pending POE: {p.get('poe',0)}\n"
                f"• Pending Exams: {p.get('exams',0)}\n"
                f"• Pending Clearances: {p.get('clearance',0)}")

    # Pending items
    if any(x in kw for x in ("pending", "review", "approval", "waiting")):
        p = pending_items()
        if not p:
            return "Pending items data unavailable. Check the dashboard directly."
        total = sum(p.values())
        if total == 0:
            return "No pending items system-wide right now. All submissions are reviewed."
        return (f"Pending items system-wide:\n"
                f"• POE assessments: {p.get('poe',0)}\n"
                f"• Exam bookings: {p.get('exams',0)}\n"
                f"• Clearance requests: {p.get('clearance',0)}")

    # Users
    if any(x in kw for x in ("user", "student", "trainee", "trainer", "staff", "account", "register")):
        s = system_stats()
        return (f"System users:\n"
                f"• Students/Trainees: {s.get('students',0)}\n"
                f"• Trainers: {s.get('trainers',0)}\n"
                f"• Dept Admins: {s.get('dept_admins',0)}\n"
                f"Manage accounts via the Users section in the sidebar.")

    # Departments
    if any(x in kw for x in ("department", "dept", "faculty")):
        s = system_stats()
        return f"There are {s.get('departments',0)} departments registered. Manage them via Departments in the sidebar."

    # Logs / audit
    if any(x in kw for x in ("log", "audit", "activity", "history")):
        return "System audit logs are available in System Logs in the sidebar. You can filter by user, action, and date."

    # Import / bulk upload
    if any(x in kw for x in ("import", "bulk", "upload user", "csv", "excel")):
        return "To bulk-import users, go to Data Import in the sidebar. Upload a CSV with the required columns. Check the template for the correct format."

    # Default
    s = system_stats()
    p = pending_items()
    return (f"I can help with system stats, pending items, user management, departments, audit logs, and imports.\n"
            f"Quick summary — {s.get('students',0)} trainees | {s.get('trainers',0)} trainers | {p.get('poe',0)} pending POE.\n"
            f"What would you like to know?")


# ── Examination Officer ───────────────────────────────────────────────────────

def _exam_officer(db, kw):
    def counts():
        try:
            return {
                "pending":   db.table("exam_bookings").select("id", count="exact").eq("status", "pending").execute().count or 0,
                "approved":  db.table("exam_bookings").select("id", count="exact").eq("status", "approved").execute().count or 0,
                "confirmed": db.table("exam_bookings").select("id", count="exact").eq("status", "confirmed").execute().count or 0,
            }
        except Exception:
            return {}

    if any(x in kw for x in ("pending", "booking", "exam", "waiting", "review")):
        c = counts()
        p = c.get("pending", 0)
        if p == 0:
            return "No exam bookings pending your review right now. All bookings are processed."
        return f"{p} exam booking{'s' if p!=1 else ''} pending your confirmation. Go to Exam Bookings in the sidebar to process them."

    if any(x in kw for x in ("approved", "confirmed", "done", "complete")):
        c = counts()
        return f"Exam bookings — Approved by HOD: {c.get('approved',0)} | Confirmed by you: {c.get('confirmed',0)}."

    if any(x in kw for x in ("stat", "summary", "overview", "total")):
        c = counts()
        return (f"Exam bookings overview:\n"
                f"• Pending HOD/your review: {c.get('pending',0)}\n"
                f"• Approved (awaiting confirmation): {c.get('approved',0)}\n"
                f"• Confirmed: {c.get('confirmed',0)}")

    c = counts()
    return (f"I can help with exam booking reviews and status summaries.\n"
            f"Current — {c.get('pending',0)} pending | {c.get('confirmed',0)} confirmed.\n"
            f"What would you like to know?")


# ── Industry Mentor ───────────────────────────────────────────────────────────

def _industry_mentor(db, uid, kw):
    def my_trainees():
        try:
            rows = db.table("industrial_attachments").select("student_id, status, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no)").eq("mentor_id", uid).execute().data or []
            return rows
        except Exception:
            return []

    def logbook_pending():
        try:
            rows = db.table("digital_logbook").select("id, student_id").eq("mentor_id", uid).execute().data or []
            return len(rows)
        except Exception:
            return 0

    if any(x in kw for x in ("trainee", "student", "attach", "placement")):
        trainees = my_trainees()
        if not trainees:
            return "No trainees are currently assigned to you for industrial attachment."
        active = [t for t in trainees if t.get("status") == "active"]
        names = []
        for t in active[:8]:
            p = t.get("user_profiles") or {}
            names.append(p.get("full_name") or p.get("admission_no") or "Trainee")
        return f"{len(active)} active trainee{'s' if len(active)!=1 else ''} under your supervision:\n" + "\n".join("• " + n for n in names)

    if any(x in kw for x in ("logbook", "log", "diary", "entry")):
        count = logbook_pending()
        return f"There are {count} logbook {'entry' if count==1 else 'entries'} from your trainees. View them in the Logbook section."

    trainees = my_trainees()
    return (f"I can help with your assigned trainees and logbook entries.\n"
            f"You have {len(trainees)} trainee{'s' if len(trainees)!=1 else ''} assigned.\n"
            f"What would you like to know?")


# ── Internal Verifier ─────────────────────────────────────────────────────────

def _internal_verifier(db, kw):
    def counts():
        try:
            return {
                "pending":  db.table("assessments").select("id", count="exact").eq("status", "pending").execute().count or 0,
                "verified": db.table("assessments").select("id", count="exact").eq("status", "approved").execute().count or 0,
            }
        except Exception:
            return {}

    if any(x in kw for x in ("pending", "review", "verify", "assessment", "poe")):
        c = counts()
        p = c.get("pending", 0)
        if p == 0:
            return "No assessments pending verification right now."
        return f"{p} assessment{'s' if p!=1 else ''} pending verification. Go to Assessments in the sidebar."

    if any(x in kw for x in ("stat", "summary", "overview", "done", "complete")):
        c = counts()
        return f"Assessments — Pending: {c.get('pending',0)} | Verified/Approved: {c.get('verified',0)}."

    c = counts()
    return (f"I can help with pending assessment verifications.\n"
            f"Current — {c.get('pending',0)} pending.\n"
            f"What would you like to know?")


# ── Generic (other roles) ─────────────────────────────────────────────────────

def _generic(role, kw):
    role_label = role.replace("_", " ").title()
    if any(x in kw for x in ("help", "what can", "how", "guide")):
        return (f"Hello! As {role_label}, you can use your dashboard to view and manage items relevant to your role. "
                f"Use the sidebar to navigate to available sections. "
                f"If you need further assistance, contact your system administrator.")
    return (f"Hi! I'm TTTI Guardian. I'm here to help with your {role_label} dashboard. "
            f"You can ask me about pending items, statistics, or how to use specific features. "
            f"What would you like to know?")
