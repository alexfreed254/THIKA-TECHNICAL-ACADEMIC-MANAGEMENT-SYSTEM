"""
routes/super_admin_merged.py — Super Admin blueprint (merged system).

Combines features from both:
- Attendance management (from original)
- E-Portfolio management (from copy)
- User management (from copy)
- Department/Class/Unit management (from both)
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, abort, jsonify)
from auth_utils import super_admin_required, write_audit_log, current_user
from db import get_service_client
from werkzeug.security import generate_password_hash

super_admin_bp = Blueprint("super_admin", __name__)


def _svc():
    return get_service_client()


def _generate_password(length: int = 10) -> str:
    """Generate a readable temporary password."""
    import secrets, string
    chars = string.ascii_letters + string.digits + "@#!"
    while True:
        pwd = ''.join(secrets.choice(chars) for _ in range(length))
        # Ensure at least one digit and one special char
        if (any(c.isdigit() for c in pwd) and
                any(c in "@#!" for c in pwd)):
            return pwd


# ── One-time setup: seed super_admin user_profiles row ───────────────────────
# Visit /super-admin/setup-profile?email=YOUR_EMAIL once to create the row.
# This route is only accessible when NOT already logged in as super_admin.

@super_admin_bp.route("/setup-profile")
def setup_profile():
    """
    One-time helper: creates a user_profiles row for an existing Supabase Auth
    super_admin user so they can log in through the app.
    Usage: /super-admin/setup-profile?email=you@example.com
    """
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Pass ?email=your@email.com"}), 400

    db = get_service_client()

    # Check if profile already exists
    existing = db.table("user_profiles").select("id, role").eq("email", email).execute().data
    if existing:
        return jsonify({
            "status": "already_exists",
            "id": existing[0]["id"],
            "role": existing[0]["role"]
        })

    # Look up the auth user by email using admin API
    try:
        users_resp = db.auth.admin.list_users()
        auth_user = next(
            (u for u in users_resp if getattr(u, "email", "") == email),
            None
        )
        if not auth_user:
            return jsonify({"error": f"No Supabase Auth user found for {email}"}), 404

        user_id = str(auth_user.id)

        # Insert user_profiles row
        db.table("user_profiles").insert({
            "id": user_id,
            "email": email,
            "full_name": email.split("@")[0].replace(".", " ").title(),
            "role": "super_admin",
            "is_active": True
        }).execute()

        return jsonify({
            "status": "created",
            "id": user_id,
            "email": email,
            "role": "super_admin",
            "message": "Profile created. You can now log in."
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


# ── Dashboard ─────────────────────────────────────────────────────────────────

@super_admin_bp.route("/")
@super_admin_bp.route("/dashboard")
@super_admin_required
def dashboard():
    db = _svc()
    stats = {}
    recent_assessments = []
    recent_logs = []
    recent_jobs = []
    recent_clearances = []
    recent_admissions = []
    dept_stats = []

    try:
        # ── Core counts ──────────────────────────────────────────────────────
        stats['departments']  = db.table("departments").select("id", count="exact").execute().count or 0
        stats['classes']      = db.table("classes").select("id", count="exact").execute().count or 0
        stats['units']        = db.table("units").select("id", count="exact").execute().count or 0
        stats['attendance']   = db.table("attendance").select("id", count="exact").execute().count or 0
        stats['assessments']  = db.table("assessments").select("id", count="exact").execute().count or 0

        # ── Role breakdown ────────────────────────────────────────────────────
        all_users = db.table("user_profiles").select("role").execute().data or []
        stats['users']       = len(all_users)
        stats['dept_admins'] = sum(1 for u in all_users if u['role'] == 'dept_admin')
        stats['trainers']    = sum(1 for u in all_users if u['role'] == 'trainer')
        stats['students']    = sum(1 for u in all_users if u['role'] == 'student')
        stats['employers']   = sum(1 for u in all_users if u['role'] == 'employer')

        # ── Assessment status breakdown ───────────────────────────────────────
        all_assess = db.table("assessments").select("status").execute().data or []
        stats['pending']  = sum(1 for a in all_assess if a['status'] == 'pending')
        stats['approved'] = sum(1 for a in all_assess if a['status'] == 'approved')
        stats['rejected'] = sum(1 for a in all_assess if a['status'] == 'rejected')

        # ── Job portal counts ─────────────────────────────────────────────────
        stats['job_postings']    = db.table("job_postings").select("id", count="exact").execute().count or 0
        stats['job_applications']= db.table("job_applications").select("id", count="exact").execute().count or 0
        stats['verifications']   = db.table("employer_verifications").select("id", count="exact").execute().count or 0

        # ── Clearance counts ──────────────────────────────────────────────────
        all_cl = db.table("clearance_requests").select("status").execute().data or []
        stats['clearances']           = len(all_cl)
        stats['clearances_pending']   = sum(1 for c in all_cl if c['status'] in ('pending','in_progress'))
        stats['clearances_completed'] = sum(1 for c in all_cl if c['status'] == 'completed')

        # ── Admission counts ──────────────────────────────────────────────────
        all_adm = db.table("admission_requests").select("status").execute().data or []
        stats['admissions']         = len(all_adm)
        stats['admissions_pending'] = sum(1 for a in all_adm if a['status'] == 'pending')
        stats['admissions_approved']= sum(1 for a in all_adm if a['status'] == 'approved')

        # ── Recent assessments ────────────────────────────────────────────────
        recent_assessments = (
            db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name), classes(name)")
            .order("uploaded_at", desc=True).limit(8).execute().data or []
        )

        # ── Recent job postings ───────────────────────────────────────────────
        recent_jobs = (
            db.table("job_postings")
            .select("*, employers(company_name)")
            .order("created_at", desc=True).limit(6).execute().data or []
        )

        # ── Recent clearances ─────────────────────────────────────────────────
        recent_clearances = (
            db.table("clearance_requests")
            .select("*, user_profiles!clearance_requests_student_id_fkey(full_name, admission_no), courses(name)")
            .order("created_at", desc=True).limit(5).execute().data or []
        )

        # ── Recent admissions ─────────────────────────────────────────────────
        recent_admissions = (
            db.table("admission_requests")
            .select("*, user_profiles!admission_requests_student_id_fkey(full_name, admission_no), courses(name)")
            .order("submitted_at", desc=True).limit(5).execute().data or []
        )

        # ── Department stats ──────────────────────────────────────────────────
        depts = db.table("departments").select("id, name").order("name").execute().data or []
        for d in depts:
            did = d["id"]
            cc = db.table("classes").select("id", count="exact").eq("department_id", did).execute().count or 0
            sc = db.table("user_profiles").select("id", count="exact").eq("department_id", did).eq("role", "student").execute().count or 0
            tc = db.table("user_profiles").select("id", count="exact").eq("department_id", did).eq("role", "trainer").execute().count or 0
            dept_stats.append({"id": did, "name": d["name"],
                               "class_count": cc, "student_count": sc, "trainer_count": tc})

        # ── Recent audit logs ─────────────────────────────────────────────────
        recent_logs = (
            db.table("system_logs")
            .select("*, user_profiles(full_name, role)")
            .order("created_at", desc=True).limit(10).execute().data or []
        )

        # ── Pending employer count (for sidebar badge) ────────────────────────
        all_emp = db.table("employers").select("is_verified").execute().data or []
        stats['pending_employers'] = sum(1 for e in all_emp if not e.get("is_verified"))

    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'danger')

    return render_template("super_admin/welcome.html",
                           stats=stats,
                           # legacy vars kept for welcome.html compat
                           depts_count=stats.get('departments', 0),
                           trainers_count=stats.get('trainers', 0),
                           classes_count=stats.get('classes', 0),
                           students_count=stats.get('students', 0),
                           units_count=stats.get('units', 0),
                           recent_assessments=recent_assessments,
                           recent_jobs=recent_jobs,
                           recent_clearances=recent_clearances,
                           recent_admissions=recent_admissions,
                           recent_logs=recent_logs,
                           dept_stats=dept_stats)


# ── Departments ───────────────────────────────────────────────────────────────

@super_admin_bp.route("/departments", methods=["GET", "POST"])
@super_admin_required
def departments():
    db = _svc()
    error = None

    if request.method == "POST" and request.form.get("add_dept"):
        name = request.form.get("name", "").strip().upper()
        code = request.form.get("code", "").strip().upper()
        if not name or not code:
            error = "Department name and code cannot be empty."
        else:
            try:
                existing = db.table("departments").select("id").eq("name", name).execute()
                if existing.data:
                    error = "Department already exists."
                else:
                    db.table("departments").insert({"name": name, "code": code}).execute()
                    write_audit_log("create_department", target=name)
                    flash("Department added successfully.", "success")
                    return redirect(url_for("super_admin.departments"))
            except Exception as exc:
                error = f"Error: {exc}"

    if request.args.get("delete"):
        try:
            dept_id = request.args["delete"]
            db.table("departments").delete().eq("id", dept_id).execute()
            write_audit_log("delete_department", target=dept_id)
            flash("Department deleted.", "success")
            return redirect(url_for("super_admin.departments"))
        except Exception as exc:
            error = f"Error deleting: {exc}"

    depts = db.table("departments").select("*").order("name").execute().data or []
    return render_template("super_admin/departments.html", departments=depts, error=error)


# ── Users Management ───────────────────────────────────────────────────────────

@super_admin_bp.route("/users", methods=["GET", "POST"])
@super_admin_required
def users():
    db = _svc()
    error = None
    role_filter = request.args.get("role", "")
    dept_filter = request.args.get("department", "")
    new_user_creds = None          # shown once after creation
    suggested_password = _generate_password()

    if request.method == "POST" and request.form.get("add_user"):
        email         = request.form.get("email", "").strip().lower()
        full_name     = request.form.get("full_name", "").strip()
        role          = request.form.get("role", "")
        department_id = request.form.get("department_id") or None
        password      = request.form.get("password", "").strip()
        admission_no  = request.form.get("admission_no", "").strip()
        staff_no      = request.form.get("staff_no", "").strip() or None
        mobile_number = request.form.get("mobile_number", "").strip() or None

        # Validate role against allowed set
        from auth_utils import ALL_ROLES
        if not all([email, full_name, role, password]):
            error = "Full name, email, role and password are all required."
        elif role not in ALL_ROLES:
            error = f"Invalid role: {role}"
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        else:
            try:
                # Duplicate email check
                existing = db.table("user_profiles").select("id").eq("email", email).execute()
                if existing.data:
                    error = "An account with this email already exists."
                else:
                    if role == "student":
                        if not admission_no:
                            error = "Admission number is required for students."
                        else:
                            dup_adm = db.table("user_profiles").select("id").eq("admission_no", admission_no).execute()
                            if dup_adm.data:
                                error = "Admission number already exists."
                            else:
                                from auth_utils import create_student_auth_user
                                user_id = create_student_auth_user(
                                    admission_no=admission_no,
                                    password=password,
                                    email=email,
                                    full_name=full_name,
                                    department_id=department_id,
                                    class_id=None,
                                    mobile_number=mobile_number
                                )
                                new_user_creds = {"full_name": full_name, "role": role,
                                                  "email": email, "password": password}
                                write_audit_log("create_user", target=f"user:{user_id}")
                                flash(f"Student account created for {full_name}.", "success")
                    else:
                        from auth_utils import create_staff_auth_user
                        user_id = create_staff_auth_user(
                            email=email,
                            password=password,
                            full_name=full_name,
                            role=role,
                            department_id=department_id,
                            staff_no=staff_no,
                            mobile_number=mobile_number
                        )
                        new_user_creds = {"full_name": full_name, "role": role,
                                          "email": email, "password": password}
                        write_audit_log("create_user", target=f"user:{user_id}")
                        flash(f"Account created for {full_name} ({role.replace('_',' ').title()}).", "success")
            except Exception as exc:
                error = f"Error creating account: {exc}"

    # Build query
    query = db.table("user_profiles").select("*, departments(name)")
    if role_filter:
        query = query.eq("role", role_filter)
    if dept_filter:
        query = query.eq("department_id", dept_filter)

    users_list   = query.order("created_at", desc=True).execute().data or []
    departments  = db.table("departments").select("*").order("name").execute().data or []

    return render_template("super_admin/users.html",
                           users=users_list,
                           departments=departments,
                           error=error,
                           role_filter=role_filter,
                           dept_filter=dept_filter,
                           new_user_creds=new_user_creds,
                           suggested_password=suggested_password)


@super_admin_bp.route("/users/<user_id>/edit", methods=["GET", "POST"])
@super_admin_required
def edit_user(user_id):
    db = _svc()
    error = None

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "")
        department_id = request.form.get("department_id")
        is_active = request.form.get("is_active") == "on"

        try:
            update_data = {
                "full_name": full_name,
                "role": role,
                "department_id": department_id if department_id else None,
                "is_active": is_active
            }
            db.table("user_profiles").update(update_data).eq("id", user_id).execute()
            write_audit_log("update_user", target=f"user:{user_id}")
            flash("User updated successfully.", "success")
            return redirect(url_for("super_admin.users"))
        except Exception as exc:
            error = f"Error: {exc}"

    user = db.table("user_profiles").select("*, departments(name)").eq("id", user_id).single().execute().data
    departments = db.table("departments").select("*").order("name").execute().data or []

    return render_template("super_admin/edit_user.html", 
                          user=user, 
                          departments=departments,
                          error=error)


@super_admin_bp.route("/users/<user_id>/delete")
@super_admin_required
def delete_user(user_id):
    db = _svc()
    try:
        db.table("user_profiles").delete().eq("id", user_id).execute()
        write_audit_log("delete_user", target=f"user:{user_id}")
        flash("User deleted successfully.", "success")
    except Exception as exc:
        flash(f"Error deleting user: {exc}", "danger")
    return redirect(url_for("super_admin.users"))


# ── Classes Management ─────────────────────────────────────────────────────────

@super_admin_bp.route("/classes", methods=["GET", "POST"])
@super_admin_required
def classes():
    db = _svc()
    error = None

    if request.args.get("delete"):
        try:
            db.table("classes").delete().eq("id", request.args["delete"]).execute()
            write_audit_log("delete_class", target=request.args["delete"])
            flash("Class deleted.", "success")
            return redirect(url_for("super_admin.classes"))
        except Exception as exc:
            error = f"Error deleting: {exc}"

    if request.method == "POST" and request.form.get("add_class"):
        name          = request.form.get("name", "").strip()
        course_id     = request.form.get("course_id") or None
        department_id = request.form.get("department_id") or None
        intake_year   = request.form.get("intake_year") or None
        intake_month  = request.form.get("intake_month") or None
        level         = request.form.get("level") or None
        cycle         = request.form.get("cycle") or None

        if not name or not department_id:
            error = "Class name and department are required."
        else:
            try:
                db.table("classes").insert({
                    "name": name,
                    "course_id": course_id,
                    "department_id": department_id,
                    "intake_year": int(intake_year) if intake_year else None,
                    "intake_month": intake_month,
                    "level": level,
                    "cycle": cycle
                }).execute()
                write_audit_log("create_class", target=name)
                flash("Class added successfully.", "success")
                return redirect(url_for("super_admin.classes"))
            except Exception as exc:
                error = f"Error: {exc}"

    classes_list = db.table("classes").select("*, departments(name), courses(name)").order("name").execute().data or []
    departments  = db.table("departments").select("*").order("name").execute().data or []
    courses      = db.table("courses").select("*").order("name").execute().data or []

    return render_template("super_admin/classes.html",
                           classes=classes_list,
                           departments=departments,
                           courses=courses,
                           error=error)


# ── Units Management ───────────────────────────────────────────────────────────

@super_admin_bp.route("/units", methods=["GET", "POST"])
@super_admin_required
def units():
    db = _svc()
    error = None

    if request.args.get("delete"):
        try:
            db.table("units").delete().eq("id", request.args["delete"]).execute()
            write_audit_log("delete_unit", target=request.args["delete"])
            flash("Unit deleted.", "success")
            return redirect(url_for("super_admin.units"))
        except Exception as exc:
            error = f"Error deleting: {exc}"

    if request.method == "POST" and request.form.get("add_unit"):
        code          = request.form.get("code", "").strip().upper()
        name          = request.form.get("name", "").strip()
        department_id = request.form.get("department_id") or None
        course_id     = request.form.get("course_id") or None

        if not code or not name or not department_id:
            error = "Code, name, and department are required."
        else:
            try:
                db.table("units").insert({
                    "code": code,
                    "name": name,
                    "department_id": department_id,
                    "course_id": course_id
                }).execute()
                write_audit_log("create_unit", target=code)
                flash("Unit added successfully.", "success")
                return redirect(url_for("super_admin.units"))
            except Exception as exc:
                error = f"Error: {exc}"

    units_list  = db.table("units").select("*, departments(name), courses(name)").order("code").execute().data or []
    departments = db.table("departments").select("*").order("name").execute().data or []
    courses     = db.table("courses").select("*").order("name").execute().data or []

    return render_template("super_admin/units.html",
                           units=units_list,
                           departments=departments,
                           courses=courses,
                           error=error)


# ── Courses Management ─────────────────────────────────────────────────────────

@super_admin_bp.route("/courses", methods=["GET", "POST"])
@super_admin_required
def courses():
    db = _svc()
    error = None

    if request.args.get("delete"):
        try:
            db.table("courses").delete().eq("id", request.args["delete"]).execute()
            write_audit_log("delete_course", target=request.args["delete"])
            flash("Course deleted.", "success")
            return redirect(url_for("super_admin.courses"))
        except Exception as exc:
            error = f"Error deleting: {exc}"

    if request.method == "POST" and request.form.get("add_course"):
        name          = request.form.get("name", "").strip()
        code          = request.form.get("code", "").strip().upper()
        department_id = request.form.get("department_id") or None

        if not name or not code or not department_id:
            error = "Name, code, and department are required."
        else:
            try:
                db.table("courses").insert({
                    "name": name,
                    "code": code,
                    "department_id": department_id
                }).execute()
                write_audit_log("create_course", target=code)
                flash("Course added successfully.", "success")
                return redirect(url_for("super_admin.courses"))
            except Exception as exc:
                error = f"Error: {exc}"

    courses_list = db.table("courses").select("*, departments(name)").order("name").execute().data or []
    departments  = db.table("departments").select("*").order("name").execute().data or []

    return render_template("super_admin/courses.html",
                           courses=courses_list,
                           departments=departments,
                           error=error)


# ── System Logs ───────────────────────────────────────────────────────────────

@super_admin_bp.route("/logs")
@super_admin_required
def logs():
    db = _svc()
    logs_list = db.table("system_logs").select("*, user_profiles(full_name, role)").order("created_at", desc=True).limit(200).execute().data or []
    return render_template("super_admin/system_logs.html", logs=logs_list)


# ── Attendance Overview ────────────────────────────────────────────────────────

@super_admin_bp.route("/attendance")
@super_admin_required
def attendance():
    db = _svc()
    dept_filter  = request.args.get("department", "")
    class_filter = request.args.get("class_id", "")

    records = db.table("attendance").select(
        "*, user_profiles:user_profiles!attendance_student_id_fkey(full_name, admission_no, enrollments(classes(name, department_id))), "
        "units(name, code)"
    ).order("attendance_date", desc=True).limit(300).execute().data or []
    
    for r in records:
        student = r.get("user_profiles") or {}
        enrolls = student.get("enrollments") or []
        first_enroll = enrolls[0] if enrolls else {}
        cls = first_enroll.get("classes") or {}
        r["classes"] = cls

    if dept_filter:
        records = [r for r in records if r.get("classes", {}).get("department_id") == dept_filter]
    if class_filter:
        records = [r for r in records if r.get("class_id") == class_filter]

    departments = db.table("departments").select("id, name").order("name").execute().data or []
    classes     = db.table("classes").select("id, name").order("name").execute().data or []

    return render_template("super_admin/attendance.html",
                           records=records, departments=departments,
                           classes=classes, dept_filter=dept_filter,
                           class_filter=class_filter)


# ── Assessments Overview ───────────────────────────────────────────────────────

@super_admin_bp.route("/assessments")
@super_admin_required
def assessments():
    db = _svc()
    status_filter = request.args.get("status", "")
    dept_filter   = request.args.get("department", "")

    query = db.table("assessments").select(
        "*, user_profiles!assessments_student_id_fkey(full_name, admission_no), "
        "units(name, code, department_id), classes(name)"
    ).order("uploaded_at", desc=True).limit(300)

    if status_filter:
        query = query.eq("status", status_filter)

    records = query.execute().data or []

    if dept_filter:
        records = [r for r in records if r.get("units", {}).get("department_id") == dept_filter]

    departments = db.table("departments").select("id, name").order("name").execute().data or []

    return render_template("super_admin/assessments.html",
                           assessments=records, departments=departments,
                           status_filter=status_filter, dept_filter=dept_filter)


# ── Marks Overview ─────────────────────────────────────────────────────────────

@super_admin_bp.route("/marks")
@super_admin_required
def marks():
    from datetime import datetime as _dt
    db = _svc()
    year        = request.args.get("year", str(_dt.now().year))
    term        = request.args.get("term", "")
    dept_filter = request.args.get("department", "")

    query = db.table("marks").select(
        "*, units(name, code, department_id), "
        "user_profiles!marks_student_id_fkey(full_name, admission_no), "
        "classes(name)"
    ).eq("year", int(year)).order("created_at", desc=True).limit(500)

    if term:
        query = query.eq("term", term)

    records = query.execute().data or []

    if dept_filter:
        records = [r for r in records if r.get("units", {}).get("department_id") == dept_filter]

    departments = db.table("departments").select("id, name").order("name").execute().data or []

    return render_template("super_admin/marks.html",
                           marks=records, departments=departments,
                           year=year, term=term, dept_filter=dept_filter)


# ── Job Postings ───────────────────────────────────────────────────────────────

@super_admin_bp.route("/job-postings")
@super_admin_required
def job_postings():
    db = _svc()
    jobs = db.table("job_postings").select(
        "*, employers(company_name, official_email)"
    ).order("created_at", desc=True).execute().data or []
    return render_template("super_admin/job_postings.html", jobs=jobs)


@super_admin_bp.route("/job-postings/<job_id>/toggle", methods=["POST"])
@super_admin_required
def toggle_job(job_id):
    db = _svc()
    row = db.table("job_postings").select("is_active").eq("id", job_id).single().execute().data
    if row:
        db.table("job_postings").update({"is_active": not row["is_active"]}).eq("id", job_id).execute()
        write_audit_log("toggle_job_posting", target=f"job:{job_id}")
        flash("Job posting updated.", "success")
    return redirect(url_for("super_admin.job_postings"))


@super_admin_bp.route("/job-postings/<job_id>/delete", methods=["POST"])
@super_admin_required
def delete_job(job_id):
    db = _svc()
    db.table("job_postings").delete().eq("id", job_id).execute()
    write_audit_log("delete_job_posting", target=f"job:{job_id}")
    flash("Job posting deleted.", "success")
    return redirect(url_for("super_admin.job_postings"))


# ── Job Applications ───────────────────────────────────────────────────────────

@super_admin_bp.route("/job-applications")
@super_admin_required
def job_applications():
    db = _svc()
    status_filter = request.args.get("status", "")
    query = db.table("job_applications").select(
        "*, job_postings(title, type, employers(company_name)), "
        "user_profiles!job_applications_student_id_fkey(full_name, admission_no)"
    ).order("applied_at", desc=True).limit(300)
    if status_filter:
        query = query.eq("status", status_filter)
    apps = query.execute().data or []
    return render_template("super_admin/job_applications.html",
                           apps=apps, status_filter=status_filter)


# ── Employer Verification Management ──────────────────────────────────────────

@super_admin_bp.route("/employers")
@super_admin_required
def employers():
    """List all employer accounts with verify/reject controls."""
    db = _svc()
    status_filter = request.args.get("status", "pending")  # pending | verified | all

    employers_list = db.table("employers").select(
        "*, user_profiles!employers_profile_id_fkey(full_name, email, is_active, created_at)"
    ).order("created_at", desc=True).execute().data or []

    if status_filter == "pending":
        employers_list = [e for e in employers_list if not e.get("is_verified")]
    elif status_filter == "verified":
        employers_list = [e for e in employers_list if e.get("is_verified")]

    pending_count = sum(1 for e in db.table("employers").select("is_verified").execute().data or [] if not e.get("is_verified"))

    return render_template("super_admin/employers.html",
                           employers=employers_list,
                           status_filter=status_filter,
                           pending_count=pending_count)


@super_admin_bp.route("/employers/<employer_id>/verify", methods=["POST"])
@super_admin_required
def verify_employer(employer_id):
    """Approve an employer account — grants login access."""
    db = _svc()
    try:
        db.table("employers").update({"is_verified": True, "is_active": True}).eq("id", employer_id).execute()
        # Also ensure user_profiles is_active = True
        emp = db.table("employers").select("profile_id").eq("id", employer_id).single().execute().data
        if emp:
            db.table("user_profiles").update({"is_active": True}).eq("id", emp["profile_id"]).execute()
        write_audit_log("verify_employer", target=f"employer:{employer_id}")
        flash("Employer verified. They can now log in.", "success")
    except Exception as exc:
        flash(f"Error: {exc}", "danger")
    return redirect(url_for("super_admin.employers"))


@super_admin_bp.route("/employers/<employer_id>/reject", methods=["POST"])
@super_admin_required
def reject_employer(employer_id):
    """Reject/deactivate an employer account."""
    db = _svc()
    reason = request.form.get("reason", "")
    try:
        db.table("employers").update({"is_verified": False, "is_active": False}).eq("id", employer_id).execute()
        emp = db.table("employers").select("profile_id").eq("id", employer_id).single().execute().data
        if emp:
            db.table("user_profiles").update({"is_active": False}).eq("id", emp["profile_id"]).execute()
        write_audit_log("reject_employer", target=f"employer:{employer_id}", detail={"reason": reason})
        flash("Employer account rejected and deactivated.", "warning")
    except Exception as exc:
        flash(f"Error: {exc}", "danger")
    return redirect(url_for("super_admin.employers"))


# ── Employer Verifications ─────────────────────────────────────────────────────

@super_admin_bp.route("/employer-verifications")
@super_admin_required
def employer_verifications():
    db = _svc()
    records = db.table("employer_verifications").select(
        "*, user_profiles!employer_verifications_trainee_id_fkey(full_name, admission_no), "
        "employers(company_name)"
    ).order("submitted_at", desc=True).execute().data or []
    return render_template("super_admin/employer_verifications.html", records=records)


# ── Clearance Requests ─────────────────────────────────────────────────────────

@super_admin_bp.route("/clearances")
@super_admin_required
def clearances():
    db = _svc()
    status_filter = request.args.get("status", "")
    query = db.table("clearance_requests").select(
        "*, user_profiles!clearance_requests_student_id_fkey(full_name, admission_no), "
        "courses(name, code), departments(name)"
    ).order("created_at", desc=True).limit(300)
    if status_filter:
        query = query.eq("status", status_filter)
    records = query.execute().data or []
    return render_template("super_admin/clearances.html",
                           clearances=records, status_filter=status_filter)


# ── Admission Requests ─────────────────────────────────────────────────────────

@super_admin_bp.route("/admissions")
@super_admin_required
def admissions():
    db = _svc()
    status_filter = request.args.get("status", "")
    dept_filter   = request.args.get("department", "")
    query = db.table("admission_requests").select(
        "*, user_profiles!admission_requests_student_id_fkey(full_name, admission_no, email), "
        "courses(name, code), departments(name)"
    ).order("submitted_at", desc=True).limit(300)
    if status_filter:
        query = query.eq("status", status_filter)
    if dept_filter:
        query = query.eq("department_id", dept_filter)
    records = query.execute().data or []
    departments = db.table("departments").select("id, name").order("name").execute().data or []
    return render_template("super_admin/admissions.html",
                           admissions=records, departments=departments,
                           status_filter=status_filter, dept_filter=dept_filter)


# ── Industry Partners (Companies) ─────────────────────────────────────────────

@super_admin_bp.route("/companies")
@super_admin_required
def companies():
    db = _svc()
    records = db.table("companies").select("*, departments(name)").order("name").execute().data or []
    departments = db.table("departments").select("id, name").order("name").execute().data or []
    return render_template("super_admin/companies.html",
                           companies=records, departments=departments)


# ── Industrial Attachments ─────────────────────────────────────────────────────

@super_admin_bp.route("/attachments")
@super_admin_required
def attachments():
    db = _svc()
    status_filter = request.args.get("status", "")
    query = db.table("industrial_attachments").select(
        "*, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no), "
        "companies(name), units(name, code)"
    ).order("created_at", desc=True).limit(300)
    if status_filter:
        query = query.eq("status", status_filter)
    records = query.execute().data or []
    return render_template("super_admin/attachments.html",
                           attachments=records, status_filter=status_filter)


@super_admin_bp.route("/logbooks")
@super_admin_required
def logbooks():
    db = _svc()
    dept_filter = request.args.get("department", "")
    query = (db.table("digital_logbook")
               .select("*, user_profiles!digital_logbook_student_id_fkey(full_name, admission_no), "
                       "units(name, code)")
               .order("log_date", desc=True)
               .limit(300))
    records = query.execute().data or []
    departments = db.table("departments").select("id, name").order("name").execute().data or []
    return render_template("super_admin/logbooks.html",
                           logbooks=records, departments=departments,
                           dept_filter=dept_filter)
