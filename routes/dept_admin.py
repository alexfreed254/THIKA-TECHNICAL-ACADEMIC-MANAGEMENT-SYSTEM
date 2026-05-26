"""
routes/dept_admin.py — Department Admin (HOD) blueprint.
Manages everything within the HOD's assigned department only.
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, abort, make_response)
from auth_utils import (dept_admin_required, write_audit_log,
                        current_user, dept_isolation_check)
from db import get_service_client
from notifications import get_user_notifications
from datetime import datetime
import secrets, string

dept_admin_bp = Blueprint("dept_admin", __name__)


def _dept_id():
    user = current_user()
    dept = user.get("department_id")
    if not dept:
        abort(403)
    return dept


def _gen_password(length=10):
    chars = string.ascii_letters + string.digits + "!@#$"
    while True:
        pwd = "".join(secrets.choice(chars) for _ in range(length))
        if any(c.isdigit() for c in pwd) and any(c in "!@#$" for c in pwd):
            return pwd


# ── Dashboard ─────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/")
@dept_admin_bp.route("/dashboard")
@dept_admin_required
def dashboard():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    stats = {}
    unread_notifications = []
    recent_assessments = []
    recent_attendance = []
    units_list = []
    try:
        stats["classes"]     = db.table("classes").select("id", count="exact").eq("department_id", dept_id).execute().count or 0
        stats["trainers"]    = db.table("user_profiles").select("id", count="exact").eq("role", "trainer").eq("department_id", dept_id).execute().count or 0
        stats["students"]    = db.table("user_profiles").select("id", count="exact").eq("role", "student").eq("department_id", dept_id).execute().count or 0
        stats["units"]       = db.table("units").select("id", count="exact").eq("department_id", dept_id).execute().count or 0
        
        # Fetch unread notifications
        unread_notifications = get_user_notifications(current_user()["id"], unread_only=True, limit=3)

        # Assessments stats filtered by department units at DB level
        dept_assessments = db.table("assessments").select("status, units!inner(department_id)").eq("units.department_id", dept_id).execute().data or []
        stats["assessments"] = len(dept_assessments)
        stats["pending"]     = sum(1 for a in dept_assessments if a["status"] == "pending")
        stats["approved"]    = sum(1 for a in dept_assessments if a["status"] == "approved")
        stats["rejected"]    = sum(1 for a in dept_assessments if a["status"] == "rejected")

        # Recent assessments specifically for this department
        recent_assessments = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units!inner(name, department_id), classes(name)")
            .eq("units.department_id", dept_id)
            .order("uploaded_at", desc=True).limit(8).execute().data or [])

        # Recent attendance specifically for this department
        recent_attendance = (db.table("attendance")
            .select("*, user_profiles!attendance_student_id_fkey(full_name, admission_no, enrollments(classes(name))), units!inner(name, code, department_id)")
            .eq("units.department_id", dept_id)
            .order("attendance_date", desc=True).limit(10).execute().data or [])
            
        # Flatten recent_attendance class names
        for att in recent_attendance:
            student = att.get("user_profiles") or {}
            enrolls = student.get("enrollments") or []
            first_enroll = enrolls[0] if enrolls else {}
            cls = first_enroll.get("classes") or {}
            att["classes"] = cls
            
        units_list = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")
    return render_template("dept_admin/dashboard.html",
                           dept=dept, stats=stats,
                           recent_assessments=recent_assessments,
                           recent_attendance=recent_attendance,
                           units_list=units_list,
                           unread_notifications=unread_notifications)


# ── Welcome alias ─────────────────────────────────────────────────────────────

@dept_admin_bp.route("/welcome")
@dept_admin_required
def welcome():
    return redirect(url_for("dept_admin.dashboard"))


# ── Classes ───────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/classes", methods=["GET", "POST"])
@dept_admin_required
def classes():
    db = get_service_client()
    dept_id = _dept_id()
    error = None
    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name      = request.form.get("name", "").strip().upper()
            course_id = request.form.get("course_id", "").strip()
            intake_year  = request.form.get("intake_year") or None
            intake_month = request.form.get("intake_month") or None
            level = request.form.get("level") or None
            cycle = request.form.get("cycle") or None
            if not name or not course_id:
                error = "Class name and course are required."
            else:
                try:
                    db.table("classes").insert({"name": name, "course_id": course_id,
                        "department_id": dept_id, "intake_year": intake_year,
                        "intake_month": intake_month, "level": level, "cycle": cycle}).execute()
                    write_audit_log("create_class", target=name)
                    flash("Class added.", "success")
                    return redirect(url_for("dept_admin.classes"))
                except Exception as exc:
                    error = f"Error: {exc}"
        elif action == "delete":
            class_id = request.form.get("class_id")
            row = db.table("classes").select("department_id").eq("id", class_id).single().execute().data
            if not row or row["department_id"] != dept_id:
                abort(403)
            db.table("classes").delete().eq("id", class_id).execute()
            write_audit_log("delete_class", target=str(class_id))
            flash("Class deleted.", "success")
            return redirect(url_for("dept_admin.classes"))
    classes_list = db.table("classes").select("*, courses(name)").eq("department_id", dept_id).order("name").execute().data or []
    courses = db.table("courses").select("*").eq("department_id", dept_id).order("name").execute().data or []
    return render_template("dept_admin/classes.html", classes=classes_list, courses=courses, error=error)


# ── Units ─────────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/units", methods=["GET", "POST"])
@dept_admin_required
def units():
    db = get_service_client()
    dept_id = _dept_id()
    error = None
    if request.method == "POST":
        code      = request.form.get("code", "").strip().upper()
        name      = request.form.get("name", "").strip()
        course_id = request.form.get("course_id", "").strip()
        if not all([code, name, course_id]):
            error = "Code, name, and course are required."
        else:
            try:
                db.table("units").insert({"code": code, "name": name,
                    "department_id": dept_id, "course_id": course_id}).execute()
                write_audit_log("create_unit", target=code)
                flash("Unit added.", "success")
                return redirect(url_for("dept_admin.units"))
            except Exception as exc:
                error = f"Error: {exc}"
    units_list = db.table("units").select("*, courses(name)").eq("department_id", dept_id).order("code").execute().data or []
    courses    = db.table("courses").select("*").eq("department_id", dept_id).order("name").execute().data or []
    return render_template("dept_admin/units.html", units=units_list, courses=courses, error=error)


# ── Trainers ──────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/trainers", methods=["GET", "POST"])
@dept_admin_required
def trainers():
    db = get_service_client()
    dept_id = _dept_id()
    error = None
    new_creds = None
    if request.method == "POST":
        email     = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        staff_no  = request.form.get("staff_no", "").strip()
        password  = _gen_password()
        if not all([email, full_name]):
            error = "Email and full name are required."
        else:
            existing = db.table("user_profiles").select("id").eq("email", email).execute()
            if existing.data:
                error = "Email already exists."
            else:
                try:
                    from auth_utils import create_staff_auth_user
                    user_id = create_staff_auth_user(email=email, password=password,
                        full_name=full_name, role="trainer", department_id=dept_id)
                    if staff_no:
                        db.table("user_profiles").update({"staff_no": staff_no}).eq("id", user_id).execute()
                    write_audit_log("create_trainer", target=f"user:{user_id}")
                    new_creds = {"full_name": full_name, "email": email, "password": password}
                    flash(f"Trainer {full_name} added.", "success")
                except Exception as exc:
                    error = f"Error: {exc}"
    trainers_list = db.table("user_profiles").select("*, departments(name)").eq("role", "trainer").eq("department_id", dept_id).order("full_name").execute().data or []
    return render_template("dept_admin/trainers.html", trainers=trainers_list, error=error, new_creds=new_creds)


# ── Students ──────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/students", methods=["GET", "POST"])
@dept_admin_required
def students():
    db = get_service_client()
    dept_id = _dept_id()
    error = None
    new_creds = None
    if request.method == "POST":
        admission_no = request.form.get("admission_no", "").strip()
        email        = request.form.get("email", "").strip().lower()
        full_name    = request.form.get("full_name", "").strip()
        class_id     = request.form.get("class_id", "").strip()
        password     = _gen_password()
        if not all([admission_no, email, full_name, class_id]):
            error = "All fields are required."
        else:
            dup = db.table("user_profiles").select("id").eq("admission_no", admission_no).execute()
            if dup.data:
                error = "Admission number already exists."
            else:
                try:
                    from auth_utils import create_student_auth_user
                    user_id = create_student_auth_user(admission_no=admission_no, password=password,
                        email=email, full_name=full_name, department_id=dept_id, class_id=class_id)
                    db.table("enrollments").insert({"student_id": user_id, "class_id": class_id}).execute()
                    write_audit_log("create_student", target=f"user:{user_id}")
                    new_creds = {"full_name": full_name, "admission_no": admission_no,
                                 "email": email, "password": password}
                    flash(f"Student {full_name} added.", "success")
                except Exception as exc:
                    error = f"Error: {exc}"
    students_list = (db.table("enrollments")
        .select("*, user_profiles(id, full_name, admission_no, email, mobile_number, is_active), classes(name)")
        .eq("classes.department_id", dept_id)
        .execute().data or [])
    # Fallback: query user_profiles directly
    if not students_list:
        students_list = db.table("user_profiles").select("*").eq("role", "student").eq("department_id", dept_id).order("full_name").execute().data or []
    classes = db.table("classes").select("*").eq("department_id", dept_id).order("name").execute().data or []
    return render_template("dept_admin/students.html", students=students_list, classes=classes,
                           error=error, new_creds=new_creds)


# ── Assign Units to Trainers ──────────────────────────────────────────────────

@dept_admin_bp.route("/trainer-units", methods=["GET", "POST"])
@dept_admin_bp.route("/assign-units", methods=["GET", "POST"])
@dept_admin_required
def trainer_units():
    db = get_service_client()
    dept_id = _dept_id()
    error = None
    if request.method == "POST":
        action     = request.form.get("action", "assign")
        trainer_id = request.form.get("trainer_id", "").strip()
        unit_id    = request.form.get("unit_id", "").strip()
        if action == "assign":
            if not all([trainer_id, unit_id]):
                error = "Trainer and unit are required."
            else:
                try:
                    db.table("trainer_units").insert({"trainer_id": trainer_id, "unit_id": unit_id}).execute()
                    write_audit_log("assign_unit", target=f"trainer:{trainer_id}")
                    flash("Unit assigned.", "success")
                    return redirect(url_for("dept_admin.trainer_units"))
                except Exception as exc:
                    error = f"Error: {exc}"
        elif action == "unassign":
            assign_id = request.form.get("assign_id", "").strip()
            if assign_id:
                db.table("trainer_units").delete().eq("id", assign_id).execute()
                write_audit_log("unassign_unit", target=f"assignment:{assign_id}")
                flash("Assignment removed.", "success")
                return redirect(url_for("dept_admin.trainer_units"))
    assignments = (db.table("trainer_units")
        .select("id, trainer_id, unit_id, user_profiles(full_name, staff_no), units(name, code)")
        .execute().data or [])
    # Filter to this department's trainers only
    dept_trainer_ids = {t["id"] for t in
        db.table("user_profiles").select("id").eq("role", "trainer").eq("department_id", dept_id).execute().data or []}
    assignments = [a for a in assignments if a.get("trainer_id") in dept_trainer_ids]
    trainers = db.table("user_profiles").select("id, full_name, staff_no").eq("role", "trainer").eq("department_id", dept_id).order("full_name").execute().data or []
    units    = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
    return render_template("dept_admin/trainer_units.html",
                           assignments=assignments, trainers=trainers, units=units, error=error)


# ── Attendance Overview ───────────────────────────────────────────────────────

@dept_admin_bp.route("/attendance")
@dept_admin_required
def attendance():
    db = get_service_client()
    dept_id = _dept_id()
    class_filter = request.args.get("class_id", "")
    unit_filter  = request.args.get("unit_id", "")
    records = (db.table("attendance")
        .select("*, user_profiles!attendance_student_id_fkey(full_name, admission_no), units(name, code, department_id), classes(name)")
        .order("attendance_date", desc=True).limit(200).execute().data or [])
    records = [r for r in records if r.get("units", {}).get("department_id") == dept_id]

    if class_filter:
        records = [r for r in records if r.get("class_id") == class_filter]
    if unit_filter:
        records = [r for r in records if r.get("unit_id") == unit_filter]

    classes = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
    units   = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
    return render_template("dept_admin/attendance.html",
                           attendance=records, classes=classes, units=units,
                           class_filter=class_filter, unit_filter=unit_filter)


# ── Assessments Overview ──────────────────────────────────────────────────────

@dept_admin_bp.route("/assessments")
@dept_admin_required
def assessments():
    db = get_service_client()
    dept_id = _dept_id()
    status_filter = request.args.get("status", "")
    query = (db.table("assessments")
        .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name, code, department_id), classes(name)")
        .order("uploaded_at", desc=True).limit(200))
    if status_filter:
        query = query.eq("status", status_filter)
    records = query.execute().data or []
    records = [r for r in records if r.get("units", {}).get("department_id") == dept_id]
    return render_template("dept_admin/assessments.html",
                           assessments=records, status_filter=status_filter)


# ── Download Unit Report CSV ──────────────────────────────────────────────────

@dept_admin_bp.route("/download-unit-report/<unit_id>")
@dept_admin_required
def download_unit_report(unit_id):
    db = get_service_client()
    dept_id = _dept_id()
    unit = db.table("units").select("*").eq("id", unit_id).single().execute().data
    if not unit or unit.get("department_id") != dept_id:
        abort(403)
    assessments = (db.table("assessments")
        .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), classes(name)")
        .eq("unit_id", unit_id).execute().data or [])
    import csv, io
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Admission No", "Full Name", "Class", "Type", "No.", "Term", "Cycle", "Year", "Status"])
    for a in assessments:
        writer.writerow([
            a.get("user_profiles", {}).get("admission_no", ""),
            a.get("user_profiles", {}).get("full_name", ""),
            a.get("classes", {}).get("name", ""),
            a.get("assessment_type", ""), a.get("assessment_no", ""),
            a.get("term", ""), a.get("cycle", ""), a.get("year", ""), a.get("status", "")
        ])
    output.seek(0)
    resp = make_response(output.getvalue())
    resp.headers["Content-Disposition"] = f"attachment; filename=unit_{unit.get('code','report')}.csv"
    resp.headers["Content-type"] = "text/csv"
    return resp


# ── Exam Bookings ─────────────────────────────────────────────────────────────

@dept_admin_bp.route("/exam-bookings")
@dept_admin_required
def exam_bookings():
    db = get_service_client()
    dept_id = _dept_id()
    status_filter = request.args.get("status", "pending")
    query = (db.table("exam_bookings")
        .select("*, units(name, code, department_id), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no), user_profiles!exam_bookings_approved_by_fkey(full_name)")
        .order("created_at", desc=True))
    if status_filter and status_filter != "all":
        query = query.eq("status", status_filter)
    bookings = query.execute().data or []
    bookings = [b for b in bookings if b.get("units", {}).get("department_id") == dept_id]
    return render_template("dept_admin/exam_bookings.html",
                           bookings=bookings, status_filter=status_filter)


@dept_admin_bp.route("/exam-bookings/<booking_id>/approve", methods=["POST"])
@dept_admin_required
def approve_exam_booking(booking_id):
    db = get_service_client()
    dept_id = _dept_id()
    user = current_user()
    booking = db.table("exam_bookings").select("*").eq("id", booking_id).single().execute().data
    if not booking:
        abort(404)
    unit = db.table("units").select("department_id").eq("id", booking["unit_id"]).single().execute().data
    if not unit or unit["department_id"] != dept_id:
        abort(403)
    try:
        db.table("exam_bookings").update({"status": "approved", "approved_by": user["id"],
            "approved_at": datetime.now().isoformat()}).eq("id", booking_id).execute()
        write_audit_log("approve_exam_booking", target=f"booking:{booking_id}")
        from notifications import create_notification
        create_notification(user_id=booking["student_id"], title="Exam Booking Approved",
            message=f"Your exam booking for {booking.get('exam_date')} has been approved.",
            notification_type="success", action_url="/student/exam-bookings")
        flash("Exam booking approved.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("dept_admin.exam_bookings"))


@dept_admin_bp.route("/exam-bookings/<booking_id>/reject", methods=["POST"])
@dept_admin_required
def reject_exam_booking(booking_id):
    db = get_service_client()
    dept_id = _dept_id()
    user = current_user()
    booking = db.table("exam_bookings").select("*").eq("id", booking_id).single().execute().data
    if not booking:
        abort(404)
    unit = db.table("units").select("department_id").eq("id", booking["unit_id"]).single().execute().data
    if not unit or unit["department_id"] != dept_id:
        abort(403)
    reason = request.form.get("rejection_reason", "")
    try:
        db.table("exam_bookings").update({"status": "rejected", "approved_by": user["id"],
            "approved_at": datetime.now().isoformat(), "rejection_reason": reason}).eq("id", booking_id).execute()
        write_audit_log("reject_exam_booking", target=f"booking:{booking_id}")
        from notifications import create_notification
        create_notification(user_id=booking["student_id"], title="Exam Booking Rejected",
            message=f"Your exam booking for {booking.get('exam_date')} was rejected. {reason}",
            notification_type="warning", action_url="/student/exam-bookings")
        flash("Exam booking rejected.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("dept_admin.exam_bookings"))


# ── Marks ─────────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/marks")
@dept_admin_required
def marks():
    db = get_service_client()
    dept_id = _dept_id()
    year     = request.args.get("year", str(datetime.now().year))
    term     = request.args.get("term", "")
    class_id = request.args.get("class_id", "")
    unit_id  = request.args.get("unit_id", "")
    query = (db.table("marks")
        .select("*, units(name, code, department_id), user_profiles!marks_student_id_fkey(full_name, admission_no), classes(name)")
        .eq("year", int(year)))
    if term:     query = query.eq("term", term)
    if class_id: query = query.eq("class_id", class_id)
    if unit_id:  query = query.eq("unit_id", unit_id)
    marks_list = query.order("created_at", desc=True).execute().data or []
    marks_list = [m for m in marks_list if m.get("units", {}).get("department_id") == dept_id]
    classes = db.table("classes").select("id, name").eq("department_id", dept_id).execute().data or []
    units   = db.table("units").select("id, name, code").eq("department_id", dept_id).execute().data or []
    return render_template("dept_admin/marks.html", marks=marks_list, classes=classes, units=units,
                           year=year, term=term, class_id=class_id, unit_id=unit_id)


@dept_admin_bp.route("/marks/download-pdf")
@dept_admin_required
def download_marks_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    year     = request.args.get("year", str(datetime.now().year))
    term     = request.args.get("term", "")
    class_id = request.args.get("class_id", "")
    unit_id  = request.args.get("unit_id", "")
    query = (db.table("marks")
        .select("*, units(name, code, department_id), user_profiles!marks_student_id_fkey(full_name, admission_no), classes(name)")
        .eq("year", int(year)))
    if term:     query = query.eq("term", term)
    if class_id: query = query.eq("class_id", class_id)
    if unit_id:  query = query.eq("unit_id", unit_id)
    marks_list = query.execute().data or []
    marks_list = [m for m in marks_list if m.get("units", {}).get("department_id") == dept_id]
    return render_template("dept_admin/marks_pdf.html", marks=marks_list,
                           year=year, term=term, class_id=class_id, unit_id=unit_id)


# ── Trainer Documents ─────────────────────────────────────────────────────────

@dept_admin_bp.route("/trainer-documents")
@dept_admin_required
def trainer_documents():
    db = get_service_client()
    dept_id = _dept_id()
    doc_type   = request.args.get("document_type", "")
    year       = request.args.get("year", str(datetime.now().year))
    term       = request.args.get("term", "")
    trainer_id = request.args.get("trainer_id", "")
    query = (db.table("trainer_documents")
        .select("*, units(name, code, department_id), classes(name), user_profiles(full_name, staff_no, department_id)")
        .eq("academic_year", int(year)))
    if term:       query = query.eq("term", term)
    if doc_type:   query = query.eq("document_type", doc_type)
    if trainer_id: query = query.eq("trainer_id", trainer_id)
    docs = query.order("created_at", desc=True).execute().data or []
    docs = [d for d in docs if (d.get("units") and d.get("units", {}).get("department_id") == dept_id) or (d.get("user_profiles") and d.get("user_profiles", {}).get("department_id") == dept_id)]
    trainers = (db.table("user_profiles").select("id, full_name, staff_no")
        .eq("role", "trainer").eq("department_id", dept_id).order("full_name").execute().data or [])
    return render_template("dept_admin/trainer_documents.html",
                           documents=docs, trainers=trainers,
                           document_type=doc_type, year=year, term=term, trainer_id=trainer_id)


# ── Class List ────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/class-list")
@dept_admin_required
def class_list():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    class_id_filter = request.args.get("class_id", "")
    classes = db.table("classes").select("*, courses(name)").eq("department_id", dept_id).order("name").execute().data or []
    selected_class = None
    students = []
    if class_id_filter:
        selected_class = next((c for c in classes if c["id"] == class_id_filter), None)
        enrollments = (db.table("enrollments")
            .select("*, user_profiles(id, full_name, admission_no, email, mobile_number)")
            .eq("class_id", class_id_filter).execute().data or [])
        students = [e.get("user_profiles", {}) for e in enrollments if e.get("user_profiles")]
    return render_template("dept_admin/class_list.html",
                           dept=dept, classes=classes, selected_class=selected_class,
                           students=students, class_id_filter=class_id_filter)


@dept_admin_bp.route("/class-list/pdf")
@dept_admin_required
def class_list_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    class_id_filter = request.args.get("class_id", "")
    selected_class = None
    students = []
    if class_id_filter:
        selected_class = db.table("classes").select("*, courses(name)").eq("id", class_id_filter).single().execute().data
        enrollments = (db.table("enrollments")
            .select("*, user_profiles(id, full_name, admission_no, email, mobile_number)")
            .eq("class_id", class_id_filter).execute().data or [])
        students = [e.get("user_profiles", {}) for e in enrollments if e.get("user_profiles")]
    return render_template("dept_admin/class_list_pdf.html",
                           dept=dept, selected_class=selected_class, students=students)


# ── Trainee Attendance Search ─────────────────────────────────────────────────

@dept_admin_bp.route("/trainee-search")
@dept_admin_required
def trainee_search():
    db = get_service_client()
    dept_id = _dept_id()
    q = request.args.get("q", "").strip()
    trainee = None
    attendance_records = []
    summary = {}
    if q:
        rows = (db.table("user_profiles").select("*").eq("role", "student")
            .eq("department_id", dept_id).ilike("admission_no", f"%{q}%").limit(1).execute().data or [])
        if not rows:
            rows = (db.table("user_profiles").select("*").eq("role", "student")
                .eq("department_id", dept_id).ilike("full_name", f"%{q}%").limit(1).execute().data or [])
        if rows:
            trainee = rows[0]
            attendance_records = (db.table("attendance")
                .select("*, units(name, code), classes(name)")
                .eq("student_id", trainee["id"]).order("attendance_date", desc=True).execute().data or [])
            total   = len(attendance_records)
            present = sum(1 for a in attendance_records if a["status"] == "present")
            summary = {"total": total, "present": present, "absent": total - present,
                       "percentage": round(present / total * 100, 1) if total else 0}
    return render_template("dept_admin/trainee_search.html",
                           query=q, trainee=trainee, attendance=attendance_records, summary=summary)


@dept_admin_bp.route("/trainee-report-pdf")
@dept_admin_required
def trainee_report_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    student_id = request.args.get("student_id", "")
    trainee = None
    attendance_records = []
    summary = {}
    if student_id:
        trainee = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data
        if trainee:
            attendance_records = (db.table("attendance")
                .select("*, units(name, code), classes(name)")
                .eq("student_id", student_id).order("attendance_date", desc=True).execute().data or [])
            total   = len(attendance_records)
            present = sum(1 for a in attendance_records if a["status"] == "present")
            summary = {"total": total, "present": present, "absent": total - present,
                       "percentage": round(present / total * 100, 1) if total else 0}
    return render_template("dept_admin/trainee_report_pdf.html",
                           dept=dept, trainee=trainee, attendance=attendance_records, summary=summary)


# ── Assessment Sheet ──────────────────────────────────────────────────────────

@dept_admin_bp.route("/assessment-sheet")
@dept_admin_required
def assessment_sheet():
    db = get_service_client()
    dept_id = _dept_id()
    class_id_filter = request.args.get("class_id", "")
    unit_id_filter  = request.args.get("unit_id", "")
    classes = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
    units   = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
    assessments = []
    if class_id_filter and unit_id_filter:
        assessments = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name, code), classes(name)")
            .eq("class_id", class_id_filter).eq("unit_id", unit_id_filter)
            .order("uploaded_at", desc=True).execute().data or [])
    return render_template("dept_admin/assessment_sheet.html",
                           classes=classes, units=units, assessments=assessments,
                           class_id_filter=class_id_filter, unit_id_filter=unit_id_filter)


@dept_admin_bp.route("/assessment-sheet/pdf")
@dept_admin_required
def assessment_sheet_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    class_id_filter = request.args.get("class_id", "")
    unit_id_filter  = request.args.get("unit_id", "")
    selected_class = selected_unit = None
    assessments = []
    if class_id_filter and unit_id_filter:
        selected_class = db.table("classes").select("*, courses(name)").eq("id", class_id_filter).single().execute().data
        selected_unit  = db.table("units").select("*").eq("id", unit_id_filter).single().execute().data
        assessments = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name, code), classes(name)")
            .eq("class_id", class_id_filter).eq("unit_id", unit_id_filter)
            .order("uploaded_at", desc=True).execute().data or [])
    return render_template("dept_admin/assessment_sheet_pdf.html",
                           dept=dept, selected_class=selected_class,
                           selected_unit=selected_unit, assessments=assessments)


# ── Credentials ───────────────────────────────────────────────────────────────

@dept_admin_bp.route("/credentials")
@dept_admin_required
def credentials():
    db = get_service_client()
    dept_id = _dept_id()
    trainers = (db.table("user_profiles").select("id, full_name, email, staff_no, is_active")
        .eq("role", "trainer").eq("department_id", dept_id).order("full_name").execute().data or [])
    students = (db.table("user_profiles").select("id, full_name, email, admission_no, is_active")
        .eq("role", "student").eq("department_id", dept_id).order("full_name").execute().data or [])
    return render_template("dept_admin/credentials.html", trainers=trainers, students=students)


# ── Import Data ───────────────────────────────────────────────────────────────

@dept_admin_bp.route("/import", methods=["GET", "POST"])
@dept_admin_required
def import_data():
    db = get_service_client()
    dept_id = _dept_id()
    results = []
    error   = None
    classes = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
    if request.method == "POST":
        import_type = request.form.get("import_type", "students")
        class_id    = request.form.get("class_id", "")
        if "file" not in request.files or request.files["file"].filename == "":
            error = "Please select an Excel (.xlsx) file."
        else:
            file = request.files["file"]
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
                ws = wb.active
                headers = [str(c.value).strip().lower() if c.value else "" for c in next(ws.iter_rows(min_row=1, max_row=1))]
                required = ["admission_no", "full_name", "email"]
                missing  = [h for h in required if h not in headers]
                if missing:
                    error = f"Missing columns: {', '.join(missing)}"
                else:
                    adm_i   = headers.index("admission_no")
                    name_i  = headers.index("full_name")
                    email_i = headers.index("email")
                    phone_i = headers.index("mobile_number") if "mobile_number" in headers else None
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if not row or row[adm_i] is None:
                            continue
                        adm   = str(row[adm_i]).strip()
                        name  = str(row[name_i]).strip()
                        email = str(row[email_i]).strip().lower()
                        phone = str(row[phone_i]).strip() if phone_i is not None and row[phone_i] else ""
                        dup = db.table("user_profiles").select("id").eq("admission_no", adm).execute().data
                        if dup:
                            results.append({"row": adm, "status": "skipped", "msg": "Already exists"})
                            continue
                        try:
                            from auth_utils import create_student_auth_user
                            pwd = _gen_password()
                            uid = create_student_auth_user(admission_no=adm, password=pwd,
                                email=email, full_name=name, department_id=dept_id, class_id=None)
                            if class_id:
                                db.table("enrollments").insert({"student_id": uid, "class_id": class_id}).execute()
                            if phone:
                                db.table("user_profiles").update({"mobile_number": phone}).eq("id", uid).execute()
                            results.append({"row": adm, "status": "created", "msg": f"Password: {pwd}"})
                        except Exception as exc:
                            results.append({"row": adm, "status": "error", "msg": str(exc)[:80]})
                wb.close()
                if not error:
                    created = sum(1 for r in results if r["status"] == "created")
                    flash(f"Import complete. {created} students created.", "success")
            except Exception as exc:
                error = f"Error reading file: {exc}"
    return render_template("dept_admin/import.html", classes=classes, results=results, error=error)


# ── Companies ─────────────────────────────────────────────────────────────────

INDUSTRIES = ['Electrical Engineering','Mechanical Engineering','Information Technology',
    'Civil Engineering','Automotive Engineering','Hospitality','Business Management',
    'Health Sciences','Agriculture','Construction','Manufacturing','Other']


@dept_admin_bp.route("/companies")
@dept_admin_required
def companies():
    db = get_service_client()
    dept_id = _dept_id()
    industry = request.args.get("industry", "")
    query = db.table("companies").select("*").eq("department_id", dept_id)
    if industry:
        query = query.eq("industry_classification", industry)
    companies_list = query.order("name").execute().data or []
    return render_template("dept_admin/companies.html",
                           companies=companies_list, industries=INDUSTRIES, industry=industry)


@dept_admin_bp.route("/companies/add", methods=["POST"])
@dept_admin_required
def add_company():
    db = get_service_client()
    dept_id = _dept_id()
    user = current_user()
    name = request.form.get("name", "").strip()
    industry_classification = request.form.get("industry_classification", "")
    if not name or not industry_classification:
        flash("Name and industry are required.", "error")
        return redirect(url_for("dept_admin.companies"))
    try:
        lat = request.form.get("latitude")
        lng = request.form.get("longitude")
        db.table("companies").insert({
            "name": name, "industry_classification": industry_classification,
            "address": request.form.get("address") or None,
            "city": request.form.get("city") or None,
            "phone_number": request.form.get("phone_number") or None,
            "email": request.form.get("email") or None,
            "website": request.form.get("website") or None,
            "latitude": float(lat) if lat else None,
            "longitude": float(lng) if lng else None,
            "geofence_radius_meters": int(request.form.get("geofence_radius_meters") or 300),
            "available_slots": int(request.form.get("available_slots") or 0),
            "department_id": dept_id,
            "contact_person": request.form.get("contact_person") or None,
            "contact_phone": request.form.get("contact_phone") or None,
            "contact_email": request.form.get("contact_email") or None,
            "description": request.form.get("description") or None,
            "created_by": user["id"]
        }).execute()
        write_audit_log("add_company", target=name)
        flash("Company added.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("dept_admin.companies"))


@dept_admin_bp.route("/companies/<company_id>/edit", methods=["POST"])
@dept_admin_required
def edit_company(company_id):
    db = get_service_client()
    dept_id = _dept_id()
    company = db.table("companies").select("department_id").eq("id", company_id).single().execute().data
    if not company or company.get("department_id") != dept_id:
        abort(403)
    try:
        lat = request.form.get("latitude")
        lng = request.form.get("longitude")
        update = {
            "name": request.form.get("name"),
            "industry_classification": request.form.get("industry_classification"),
            "address": request.form.get("address") or None,
            "city": request.form.get("city") or None,
            "phone_number": request.form.get("phone_number") or None,
            "email": request.form.get("email") or None,
            "website": request.form.get("website") or None,
            "geofence_radius_meters": int(request.form.get("geofence_radius_meters") or 300),
            "available_slots": int(request.form.get("available_slots") or 0),
            "contact_person": request.form.get("contact_person") or None,
            "contact_phone": request.form.get("contact_phone") or None,
            "contact_email": request.form.get("contact_email") or None,
            "description": request.form.get("description") or None,
            "is_active": request.form.get("is_active") == "on"
        }
        if lat: update["latitude"] = float(lat)
        if lng: update["longitude"] = float(lng)
        db.table("companies").update(update).eq("id", company_id).execute()
        write_audit_log("edit_company", target=f"company:{company_id}")
        flash("Company updated.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("dept_admin.companies"))


@dept_admin_bp.route("/companies/<company_id>/delete", methods=["POST"])
@dept_admin_required
def delete_company(company_id):
    db = get_service_client()
    dept_id = _dept_id()
    company = db.table("companies").select("department_id").eq("id", company_id).single().execute().data
    if not company or company.get("department_id") != dept_id:
        abort(403)
    try:
        db.table("companies").delete().eq("id", company_id).execute()
        write_audit_log("delete_company", target=f"company:{company_id}")
        flash("Company deleted.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    return redirect(url_for("dept_admin.companies"))
