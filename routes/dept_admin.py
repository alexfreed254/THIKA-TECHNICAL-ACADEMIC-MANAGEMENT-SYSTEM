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
            name         = request.form.get("name", "").strip().upper()
            course_id    = request.form.get("course_id", "").strip()
            intake_year  = request.form.get("intake_year") or None
            intake_month = request.form.get("intake_month") or None
            level        = request.form.get("level") or None
            cycle        = request.form.get("cycle") or None
            if not name or not course_id:
                error = "Class name and course are required."
            else:
                try:
                    db.table("classes").insert({
                        "name": name, "course_id": course_id,
                        "department_id": dept_id, "intake_year": intake_year,
                        "intake_month": intake_month, "level": level, "cycle": cycle
                    }).execute()
                    write_audit_log("create_class", target=name)
                    flash("Class added successfully.", "success")
                    return redirect(url_for("dept_admin.classes"))
                except Exception as exc:
                    error = f"Error creating class: {exc}"
        elif action == "edit":
            class_id     = request.form.get("class_id", "").strip()
            name         = request.form.get("name", "").strip().upper()
            course_id    = request.form.get("course_id", "").strip()
            intake_year  = request.form.get("intake_year") or None
            intake_month = request.form.get("intake_month") or None
            level        = request.form.get("level") or None
            cycle        = request.form.get("cycle") or None
            if not class_id or not name or not course_id:
                error = "Class name and course are required."
            else:
                row = db.table("classes").select("department_id").eq("id", class_id).single().execute().data
                if not row or row.get("department_id") != dept_id:
                    abort(403)
                try:
                    db.table("classes").update({
                        "name": name, "course_id": course_id,
                        "intake_year": intake_year, "intake_month": intake_month,
                        "level": level, "cycle": cycle
                    }).eq("id", class_id).execute()
                    write_audit_log("edit_class", target=name)
                    flash("Class updated successfully.", "success")
                    return redirect(url_for("dept_admin.classes"))
                except Exception as exc:
                    error = f"Error updating class: {exc}"
        elif action == "delete":
            class_id = request.form.get("class_id")
            row = db.table("classes").select("department_id").eq("id", class_id).single().execute().data
            if not row or row.get("department_id") != dept_id:
                abort(403)
            try:
                db.table("classes").delete().eq("id", class_id).execute()
                write_audit_log("delete_class", target=str(class_id))
                flash("Class deleted.", "success")
            except Exception as exc:
                flash(f"Cannot delete class (it may have students enrolled): {exc}", "danger")
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
        action    = request.form.get("action", "create")
        if action == "create":
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
                    flash("Unit added successfully.", "success")
                    return redirect(url_for("dept_admin.units"))
                except Exception as exc:
                    error = f"Error creating unit: {exc}"
        elif action == "edit":
            unit_id   = request.form.get("unit_id", "").strip()
            code      = request.form.get("code", "").strip().upper()
            name      = request.form.get("name", "").strip()
            course_id = request.form.get("course_id", "").strip()
            if not all([unit_id, code, name, course_id]):
                error = "All fields are required."
            else:
                row = db.table("units").select("department_id").eq("id", unit_id).single().execute().data
                if not row or row.get("department_id") != dept_id:
                    abort(403)
                try:
                    db.table("units").update({
                        "code": code, "name": name, "course_id": course_id
                    }).eq("id", unit_id).execute()
                    write_audit_log("edit_unit", target=code)
                    flash("Unit updated successfully.", "success")
                    return redirect(url_for("dept_admin.units"))
                except Exception as exc:
                    error = f"Error updating unit: {exc}"
        elif action == "delete":
            unit_id = request.form.get("unit_id", "").strip()
            row = db.table("units").select("department_id").eq("id", unit_id).single().execute().data
            if not row or row.get("department_id") != dept_id:
                abort(403)
            try:
                db.table("units").delete().eq("id", unit_id).execute()
                write_audit_log("delete_unit", target=str(unit_id))
                flash("Unit deleted.", "success")
            except Exception as exc:
                flash(f"Cannot delete unit (it may have assessments or assignments linked to it): {exc}", "danger")
            return redirect(url_for("dept_admin.units"))
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
    search = request.args.get("q", "")
    return render_template("dept_admin/students.html", students=students_list, classes=classes,
                           error=error, new_creds=new_creds, search=search)


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
                # Verify trainer belongs to this department
                t_row = db.table("user_profiles").select("department_id").eq("id", trainer_id).single().execute().data
                if not t_row or t_row.get("department_id") != dept_id:
                    abort(403)
                # Verify unit belongs to this department
                u_row = db.table("units").select("department_id").eq("id", unit_id).single().execute().data
                if not u_row or u_row.get("department_id") != dept_id:
                    abort(403)
                try:
                    db.table("trainer_units").insert({"trainer_id": trainer_id, "unit_id": unit_id}).execute()
                    write_audit_log("assign_unit", target=f"trainer:{trainer_id}")
                    flash("Unit assigned successfully.", "success")
                    return redirect(url_for("dept_admin.trainer_units"))
                except Exception as exc:
                    err_str = str(exc)
                    if "duplicate" in err_str.lower() or "unique" in err_str.lower():
                        error = "This unit is already assigned to that trainer."
                    else:
                        error = f"Error assigning unit: {exc}"
        elif action == "unassign":
            assign_id = request.form.get("assign_id", "").strip()
            if assign_id:
                try:
                    db.table("trainer_units").delete().eq("id", assign_id).execute()
                    write_audit_log("unassign_unit", target=f"assignment:{assign_id}")
                    flash("Assignment removed successfully.", "success")
                except Exception as exc:
                    flash(f"Error removing assignment: {exc}", "danger")
                return redirect(url_for("dept_admin.trainer_units"))

    # Use explicit FK hint for the user_profiles join to avoid ambiguity
    try:
        assignments = (db.table("trainer_units")
            .select("id, trainer_id, unit_id, assigned_at, user_profiles!trainer_units_trainer_id_fkey(full_name, staff_no), units(name, code)")
            .execute().data or [])
        # Filter to only this department's trainers
        dept_trainer_ids = {t["id"] for t in
            db.table("user_profiles").select("id").eq("role", "trainer").eq("department_id", dept_id).execute().data or []}
        assignments = [a for a in assignments if a.get("trainer_id") in dept_trainer_ids]
    except Exception:
        # Fallback: fetch without join, manually attach profile data
        assignments = (db.table("trainer_units")
            .select("id, trainer_id, unit_id, assigned_at")
            .execute().data or [])
        dept_trainer_ids = {t["id"] for t in
            db.table("user_profiles").select("id").eq("role", "trainer").eq("department_id", dept_id).execute().data or []}
        assignments = [a for a in assignments if a.get("trainer_id") in dept_trainer_ids]
        # Attach profile and unit info manually
        profiles = {p["id"]: p for p in
            db.table("user_profiles").select("id, full_name, staff_no").in_("id", list(dept_trainer_ids)).execute().data or []}
        dept_units = {u["id"]: u for u in
            db.table("units").select("id, name, code").eq("department_id", dept_id).execute().data or []}
        for a in assignments:
            a["user_profiles"] = profiles.get(a["trainer_id"], {})
            a["units"] = dept_units.get(a["unit_id"], {})

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
        .select("*, user_profiles:user_profiles!attendance_student_id_fkey(full_name, admission_no, enrollments(classes(name))), units(name, code, department_id)")
        .order("attendance_date", desc=True).limit(200).execute().data or [])
        
    for r in records:
        student = r.get("user_profiles") or {}
        enrolls = student.get("enrollments") or []
        first_enroll = enrolls[0] if enrolls else {}
        cls = first_enroll.get("classes") or {}
        r["classes"] = cls
        
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
        .select("*, units(name, code, department_id), student:user_profiles!exam_bookings_student_id_fkey(full_name, admission_no), reviewer:user_profiles!exam_bookings_approved_by_fkey(full_name)")
        .order("created_at", desc=True))
    if status_filter and status_filter != "all":
        query = query.eq("status", status_filter)
    bookings = query.execute().data or []
    bookings = [b for b in bookings if b.get("units", {}).get("department_id") == dept_id]

    # Attach class name via student enrollment (no FK between exam_bookings and classes)
    for b in bookings:
        b["student_user"] = b.get("student") or {}
        b["approved_by_user"] = b.get("reviewer") or {}
        student_id = b.get("student_id")
        if student_id:
            enroll = (db.table("enrollments")
                .select("classes(name)")
                .eq("student_id", student_id).limit(1).execute().data or [])
            b["classes"] = enroll[0].get("classes") if enroll and enroll[0] else None

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
        .select("*, student:user_profiles!marks_student_id_fkey(full_name, admission_no), trainer:user_profiles!marks_trainer_id_fkey(full_name), units(name, code, department_id), classes(name, departments(name))")
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
        .select("*, student:user_profiles!marks_student_id_fkey(full_name, admission_no), trainer:user_profiles!marks_trainer_id_fkey(full_name), units(name, code, department_id), classes(name, departments(name))")
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


# ── Trainee POE ───────────────────────────────────────────────────────────────

@dept_admin_bp.route("/trainee-poe")
@dept_admin_required
def trainee_poe():
    db = get_service_client()
    dept_id = _dept_id()
    
    status_filter = request.args.get("status", "")
    class_filter  = request.args.get("class_id", "")
    unit_filter   = request.args.get("unit_id", "")
    
    query = (db.table("assessments")
        .select("*, student:user_profiles!assessments_student_id_fkey(full_name, admission_no), units!inner(name, code, department_id), classes(name), reviewer:user_profiles!assessments_reviewed_by_fkey(full_name)")
        .eq("units.department_id", dept_id))
    
    if status_filter in ("approved", "rejected"):
        query = query.eq("status", status_filter)
    else:
        query = query.in_("status", ["approved", "rejected"])
        
    if class_filter:
        query = query.eq("class_id", class_filter)
    if unit_filter:
        query = query.eq("unit_id", unit_filter)
        
    assessments = query.order("reviewed_at", desc=True).execute().data or []
    
    classes = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
    units   = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
    
    return render_template(
        "dept_admin/trainee_poe.html",
        assessments=assessments,
        classes=classes,
        units=units,
        status_filter=status_filter,
        class_filter=class_filter,
        unit_filter=unit_filter
    )


# ── Class List ────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/class-list")
@dept_admin_required
def class_list():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    class_id = request.args.get("class_id", "")
    classes = db.table("classes").select("*, courses(name)").eq("department_id", dept_id).order("name").execute().data or []
    cls = None
    students = []
    if class_id:
        cls = next((c for c in classes if str(c["id"]) == class_id), None)
        enrollments = (db.table("enrollments")
            .select("*, user_profiles(id, full_name, admission_no, email, mobile_number)")
            .eq("class_id", class_id).execute().data or [])
        students = [e.get("user_profiles", {}) for e in enrollments if e.get("user_profiles")]
        for s in students:
            s["admission_number"] = s.get("admission_no", "")
    return render_template("dept_admin/class_list.html",
                           dept=dept, classes=classes, cls=cls,
                           students=students, class_id=class_id)


@dept_admin_bp.route("/class-list/pdf")
@dept_admin_required
def class_list_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    class_id = request.args.get("class_id", "")
    cls = None
    students = []
    if class_id:
        cls = db.table("classes").select("*, courses(name)").eq("id", class_id).single().execute().data
        enrollments = (db.table("enrollments")
            .select("*, user_profiles(id, full_name, admission_no, email, mobile_number)")
            .eq("class_id", class_id).execute().data or [])
        students = [e.get("user_profiles", {}) for e in enrollments if e.get("user_profiles")]
        for s in students:
            s["admission_number"] = s.get("admission_no", "")
    return render_template("dept_admin/class_list_pdf.html",
                           cls=cls, dept_name=dept.get("name",""),
                           students=students, date_gen=datetime.now().strftime("%d %b %Y"))


# ── Trainee Attendance Search ─────────────────────────────────────────────────

@dept_admin_bp.route("/trainee-search")
@dept_admin_required
def trainee_search():
    db = get_service_client()
    dept_id = _dept_id()
    q = request.args.get("q", "").strip()
    student_id = request.args.get("student_id", "")
    unit_id = request.args.get("unit_id", "")
    students = []
    student = None
    records = []
    units_list = []
    summary = {}

    if q:
        students = (db.table("user_profiles").select("*, classes!enrollments(name)")
            .eq("role", "student").eq("department_id", dept_id)
            .or_(f"admission_no.ilike.%{q}%,full_name.ilike.%{q}%")
            .limit(20).execute().data or [])

    if student_id:
        student = db.table("user_profiles").select("*, classes!enrollments(name)").eq("id", student_id).single().execute().data
        if student:
            units_list = (db.table("attendance").select("unit_id, units!inner(id, name, code)")
                .eq("student_id", student_id)
                .execute().data or [])
            seen = set()
            deduped = []
            for u in units_list:
                uid = u["unit_id"]
                if uid not in seen:
                    seen.add(uid)
                    deduped.append(u.get("units", u))
            units_list = deduped

    if student_id and unit_id:
        records = (db.table("attendance")
            .select("*, units(name, code), trainers:user_profiles!attendance_trainer_id_fkey(name)")
            .eq("student_id", student_id).eq("unit_id", unit_id)
            .order("attendance_date", desc=True).execute().data or [])

        total = len(records)
        present = sum(1 for a in records if a["status"] == "present")
        unit_info = db.table("units").select("name, code").eq("id", unit_id).single().execute().data or {}
        summary = {"total": total, "present": present, "absent": total - present,
                   "pct": round(present / total * 100, 1) if total else 0,
                   "unit_code": unit_info.get("code", ""),
                   "unit_name": unit_info.get("name", "")}

    return render_template("dept_admin/trainee_search.html",
                           query=q, students=students, student=student,
                           student_id=student_id, unit_id=unit_id,
                           units_list=units_list, records=records, summary=summary)


@dept_admin_bp.route("/trainee-report-pdf")
@dept_admin_required
def trainee_report_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    student_id = request.args.get("student_id", "")
    unit_id = request.args.get("unit_id", "")
    student = None
    records = []
    summary = {}
    if student_id and unit_id:
        student = db.table("user_profiles").select("*, classes!enrollments(name)").eq("id", student_id).single().execute().data
        if student:
            if not student.get("admission_number"):
                student["admission_number"] = student.get("admission_no", "")
            records = (db.table("attendance")
                .select("*, units(name, code), trainers:user_profiles!attendance_trainer_id_fkey(name)")
                .eq("student_id", student_id).eq("unit_id", unit_id)
                .order("attendance_date", desc=True).execute().data or [])
            unit_info = db.table("units").select("name, code").eq("id", unit_id).single().execute().data or {}
            total = len(records)
            present = sum(1 for a in records if a["status"] == "present")
            summary = {"total": total, "present": present, "absent": total - present,
                       "pct": round(present / total * 100, 1) if total else 0,
                       "unit_code": unit_info.get("code", ""),
                       "unit_name": unit_info.get("name", "")}
    return render_template("dept_admin/trainee_report_pdf.html",
                           dept_name=dept.get("name",""), student=student,
                           records=records, summary=summary,
                           generated=datetime.now().strftime("%d %b %Y"))


# ── Assessment Sheet ──────────────────────────────────────────────────────────

@dept_admin_bp.route("/assessment-sheet")
@dept_admin_required
def assessment_sheet():
    db = get_service_client()
    dept_id = _dept_id()
    class_id = request.args.get("class_id", "")
    unit_id  = request.args.get("unit_id", "")
    year     = request.args.get("year", "")
    term     = request.args.get("term", "")
    min_pct  = int(request.args.get("min_pct", 80))

    classes = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
    units   = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
    cls = None
    unit = None
    eligible = []
    term_label = f"Term {term}" if term else "All Terms"

    if class_id and unit_id:
        cls = db.table("classes").select("id, name").eq("id", class_id).single().execute().data
        unit = db.table("units").select("id, name, code").eq("id", unit_id).single().execute().data
        enrollments = (db.table("enrollments")
            .select("student_id, user_profiles!inner(id, full_name, admission_no)")
            .eq("class_id", class_id).execute().data or [])
        for e in enrollments:
            student = e.get("user_profiles") or {}
            sid = student.get("id")
            if not sid:
                continue
            att_query = db.table("attendance").select("status").eq("student_id", sid).eq("unit_id", unit_id)
            if year:
                att_query = att_query.eq("year", int(year))
            if term:
                att_query = att_query.eq("term", term)
            att_records = att_query.execute().data or []
            total = len(att_records)
            if total == 0:
                continue
            present = sum(1 for a in att_records if a["status"] == "present")
            pct = round(present / total * 100, 1)
            if pct >= min_pct:
                eligible.append({
                    "admission_number": student.get("admission_no", ""),
                    "full_name": student.get("full_name", ""),
                    "present": present,
                    "total": total,
                    "pct": pct
                })
        eligible.sort(key=lambda x: x["full_name"])

    return render_template("dept_admin/assessment_sheet.html",
                           classes=classes, units=units,
                           class_id=class_id, unit_id=unit_id,
                           year=year, term=term, min_pct=min_pct,
                           cls=cls, unit=unit, term_label=term_label,
                           eligible=eligible)


@dept_admin_bp.route("/assessment-sheet/pdf")
@dept_admin_required
def assessment_sheet_pdf():
    db = get_service_client()
    dept_id = _dept_id()
    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}
    class_id = request.args.get("class_id", "")
    unit_id  = request.args.get("unit_id", "")
    year     = request.args.get("year", "")
    term     = request.args.get("term", "")
    min_pct  = int(request.args.get("min_pct", 80))

    cls = None
    unit = None
    eligible = []
    term_label = f"Term {term}" if term else "All Terms"

    if class_id and unit_id:
        cls = db.table("classes").select("id, name").eq("id", class_id).single().execute().data
        unit = db.table("units").select("id, name, code").eq("id", unit_id).single().execute().data
        enrollments = (db.table("enrollments")
            .select("student_id, user_profiles!inner(id, full_name, admission_no)")
            .eq("class_id", class_id).execute().data or [])
        for e in enrollments:
            student = e.get("user_profiles") or {}
            sid = student.get("id")
            if not sid:
                continue
            att_query = db.table("attendance").select("status").eq("student_id", sid).eq("unit_id", unit_id)
            if year:
                att_query = att_query.eq("year", int(year))
            if term:
                att_query = att_query.eq("term", term)
            att_records = att_query.execute().data or []
            total = len(att_records)
            if total == 0:
                continue
            present = sum(1 for a in att_records if a["status"] == "present")
            pct = round(present / total * 100, 1)
            if pct >= min_pct:
                eligible.append({
                    "admission_number": student.get("admission_no", ""),
                    "full_name": student.get("full_name", ""),
                    "present": present,
                    "total": total,
                    "pct": pct
                })
        eligible.sort(key=lambda x: x["full_name"])

    return render_template("dept_admin/assessment_sheet_pdf.html",
                           cls=cls, unit=unit, dept_name=dept.get("name",""),
                           term_label=term_label, year=year, min_pct=min_pct,
                           eligible=eligible, date_gen=datetime.now().strftime("%d %b %Y"))


# ── Credentials ───────────────────────────────────────────────────────────────

@dept_admin_bp.route("/credentials", methods=["GET", "POST"])
@dept_admin_required
def credentials():
    db = get_service_client()
    dept_id = _dept_id()
    msg = None
    tab = request.args.get("tab", "trainers")
    search_t = request.args.get("search_t", "")
    search_s = request.args.get("search_s", "")
    filter_class = request.args.get("filter_class", "")

    if request.method == "POST":
        action = request.form.get("action")
        if action == "update_trainer":
            tid = request.form.get("trainer_id")
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "").strip()
            if username:
                db.table("auth_users").update({"username": username}).eq("user_id", tid).execute()
            if password:
                from auth_utils import hash_password
                db.table("auth_users").update({"password_hash": hash_password(password)}).eq("user_id", tid).execute()
            msg = f"Trainer credentials updated."
        elif action == "update_student":
            sid = request.form.get("student_id")
            password = request.form.get("password", "").strip()
            if password:
                from auth_utils import hash_password
                db.table("auth_users").update({"password_hash": hash_password(password)}).eq("user_id", sid).execute()
            msg = "Student password updated."
        elif action == "reset_student":
            sid = request.form.get("student_id")
            from auth_utils import hash_password
            db.table("auth_users").update({"password_hash": hash_password("123456")}).eq("user_id", sid).execute()
            msg = "Student password reset to 123456."
        return redirect(url_for("dept_admin.credentials", tab=tab, search_t=search_t,
                                search_s=search_s, filter_class=filter_class))

    tq = db.table("user_profiles").select("id, full_name, email, staff_no, is_active, departments(name)")
    tq = tq.eq("role", "trainer").eq("department_id", dept_id)
    if search_t:
        tq = tq.or_(f"full_name.ilike.%{search_t}%,staff_no.ilike.%{search_t}%")
    trainers_list = tq.order("full_name").execute().data or []

    sq = db.table("user_profiles").select("id, full_name, admission_no, email, is_active, classes!enrollments(name)")
    sq = sq.eq("role", "student").eq("department_id", dept_id)
    if search_s:
        sq = sq.or_(f"full_name.ilike.%{search_s}%,admission_no.ilike.%{search_s}%")
    if filter_class:
        sq = sq.eq("enrollments.class_id", filter_class)
    students_list = sq.order("full_name").execute().data or []
    for s in students_list:
        if not s.get("admission_number"):
            s["admission_number"] = s.get("admission_no", "")

    classes_list = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
    return render_template("dept_admin/credentials.html",
                           tab=tab, search_t=search_t, search_s=search_s,
                           filter_class=filter_class, msg=msg,
                           trainers_list=trainers_list, students_list=students_list,
                           classes_list=classes_list)


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
    result_summary = None
    if results:
        result_summary = {
            "success": sum(1 for r in results if r["status"] == "created"),
            "errors": [r["msg"] for r in results if r["status"] == "error"]
        }
    return render_template("dept_admin/import.html", classes=classes, results=results, result=result_summary, error=error)


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


@dept_admin_bp.route("/companies/<company_id>")
@dept_admin_required
def get_company(company_id):
    db = get_service_client()
    dept_id = _dept_id()
    company = db.table("companies").select("*").eq("id", company_id).single().execute().data
    if not company or company.get("department_id") != dept_id:
        return {"error": "Not found"}, 404
    return {k: company.get(k) for k in ("id","name","industry_classification","address","city",
        "phone_number","email","website","latitude","longitude","geofence_radius_meters",
        "available_slots","contact_person","contact_phone","contact_email","description","is_active")}


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
