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


# ── Dashboard ─────────────────────────────────────────────────────────────────

@super_admin_bp.route("/")
@super_admin_bp.route("/dashboard")
@super_admin_required
def dashboard():
    db = _svc()
    stats = {}
    recent_assessments = []
    recent_logs = []
    dept_stats = []

    try:
        # Basic counts
        stats['departments'] = db.table("departments").select("id", count="exact").execute().count or 0
        stats['users'] = db.table("user_profiles").select("id", count="exact").execute().count or 0
        stats['classes'] = db.table("classes").select("id", count="exact").execute().count or 0
        stats['units'] = db.table("units").select("id", count="exact").execute().count or 0
        stats['assessments'] = db.table("assessments").select("id", count="exact").execute().count or 0
        stats['attendance'] = db.table("attendance").select("id", count="exact").execute().count or 0

        # Role breakdown
        all_users = db.table("user_profiles").select("role").execute().data or []
        stats['dept_admins'] = sum(1 for u in all_users if u['role'] == 'dept_admin')
        stats['trainers'] = sum(1 for u in all_users if u['role'] == 'trainer')
        stats['students'] = sum(1 for u in all_users if u['role'] == 'student')

        # Assessment status breakdown
        all_assess = db.table("assessments").select("status").execute().data or []
        stats['pending'] = sum(1 for a in all_assess if a['status'] == 'pending')
        stats['approved'] = sum(1 for a in all_assess if a['status'] == 'approved')
        stats['rejected'] = sum(1 for a in all_assess if a['status'] == 'rejected')

        # Recent assessments
        recent_assessments = (
            db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name), classes(name)")
            .order("uploaded_at", desc=True)
            .limit(10)
            .execute().data or []
        )

        # Department stats — include trainer and student counts per dept
        depts = db.table("departments").select("id, name").order("name").execute().data or []
        for d in depts:
            did = d["id"]
            cc = db.table("classes").select("id", count="exact").eq("department_id", did).execute().count or 0
            sc = db.table("user_profiles").select("id", count="exact").eq("department_id", did).eq("role", "student").execute().count or 0
            tc = db.table("user_profiles").select("id", count="exact").eq("department_id", did).eq("role", "trainer").execute().count or 0
            dept_stats.append({
                "id": did, "name": d["name"],
                "class_count": cc, "user_count": sc + tc,
                "student_count": sc, "trainer_count": tc
            })

        # Recent logs
        recent_logs = (
            db.table("system_logs")
            .select("*, user_profiles(full_name, role)")
            .order("created_at", desc=True)
            .limit(20)
            .execute().data or []
        )
    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'danger')

    return render_template("super_admin/welcome.html",
                           stats=stats,
                           depts_count=stats.get('departments', 0),
                           trainers_count=stats.get('trainers', 0),
                           classes_count=stats.get('classes', 0),
                           students_count=stats.get('students', 0),
                           units_count=stats.get('units', 0),
                           recent_assessments=recent_assessments,
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

    if request.method == "POST" and request.form.get("add_user"):
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        role = request.form.get("role", "")
        department_id = request.form.get("department_id")
        password = request.form.get("password", "")
        admission_no = request.form.get("admission_no", "").strip()

        if not all([email, full_name, role, password]):
            error = "All required fields must be filled."
        else:
            try:
                # Check if email exists
                existing = db.table("user_profiles").select("id").eq("email", email).execute()
                if existing.data:
                    error = "Email already exists."
                elif role == "student" and admission_no:
                    # Check admission number
                    existing = db.table("user_profiles").select("id").eq("admission_no", admission_no).execute()
                    if existing.data:
                        error = "Admission number already exists."
                else:
                    if role in ["super_admin", "dept_admin", "trainer"]:
                        # Create staff user with Supabase Auth
                        from auth_utils import create_staff_auth_user
                        user_id = create_staff_auth_user(
                            email=email,
                            password=password,
                            full_name=full_name,
                            role=role,
                            department_id=department_id if department_id else None
                        )
                    else:
                        # Create student user
                        from auth_utils import create_student_auth_user
                        user_id = create_student_auth_user(
                            admission_no=admission_no or email[:5],
                            password=password,
                            email=email,
                            full_name=full_name,
                            department_id=department_id if department_id else None,
                            class_id=None
                        )
                    
                    write_audit_log("create_user", target=f"user:{user_id}")
                    flash("User created successfully.", "success")
                    return redirect(url_for("super_admin.users"))
            except Exception as exc:
                error = f"Error: {exc}"

    # Build query
    query = db.table("user_profiles").select("*, departments(name)")
    if role_filter:
        query = query.eq("role", role_filter)
    if dept_filter:
        query = query.eq("department_id", dept_filter)
    
    users_list = query.order("created_at", desc=True).execute().data or []
    departments = db.table("departments").select("*").order("name").execute().data or []

    return render_template("super_admin/users.html", 
                          users=users_list, 
                          departments=departments,
                          error=error,
                          role_filter=role_filter,
                          dept_filter=dept_filter)


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

    if request.method == "POST" and request.form.get("add_class"):
        name = request.form.get("name", "").strip()
        course_id = request.form.get("course_id")
        department_id = request.form.get("department_id")
        intake_year = request.form.get("intake_year")
        intake_month = request.form.get("intake_month")
        level = request.form.get("level")
        cycle = request.form.get("cycle")

        if not all([name, course_id, department_id]):
            error = "Name, course, and department are required."
        else:
            try:
                db.table("classes").insert({
                    "name": name,
                    "course_id": course_id,
                    "department_id": department_id,
                    "intake_year": intake_year,
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
    departments = db.table("departments").select("*").order("name").execute().data or []
    courses = db.table("courses").select("*").order("name").execute().data or []

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

    if request.method == "POST" and request.form.get("add_unit"):
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        department_id = request.form.get("department_id")
        course_id = request.form.get("course_id")

        if not all([code, name, department_id]):
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

    units_list = db.table("units").select("*, departments(name), courses(name)").order("code").execute().data or []
    departments = db.table("departments").select("*").order("name").execute().data or []
    courses = db.table("courses").select("*").order("name").execute().data or []

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

    if request.method == "POST" and request.form.get("add_course"):
        name = request.form.get("name", "").strip()
        code = request.form.get("code", "").strip().upper()
        department_id = request.form.get("department_id")

        if not all([name, code, department_id]):
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
    departments = db.table("departments").select("*").order("name").execute().data or []

    return render_template("super_admin/courses.html",
                          courses=courses_list,
                          departments=departments,
                          error=error)


# ── System Logs ───────────────────────────────────────────────────────────────

@super_admin_bp.route("/logs")
@super_admin_required
def logs():
    db = _svc()
    logs_list = db.table("system_logs").select("*, user_profiles(full_name, role)").order("created_at", desc=True).limit(100).execute().data or []
    return render_template("super_admin/system_logs.html", logs=logs_list)
