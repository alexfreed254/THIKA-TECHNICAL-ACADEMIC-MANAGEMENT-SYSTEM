"""
Admin Oversight Blueprint for Registrar, Deputy Principal, and Quality Assurance Officer
Provides read-only access to all departmental activities with filtering capabilities
"""

from flask import Blueprint, render_template, request
from auth_utils import login_required, registrar_required, deputy_principal_required, quality_assurance_officer_required, current_user
from db import get_service_client
from stats_utils import count_table, exact_count, clearance_kpi

admin_oversight_bp = Blueprint('admin_oversight', __name__)


def _oversight_core_stats(db, department_filter="", *, include_trainers=False, include_certs=False):
    """Realtime exact KPI counts shared by oversight dashboards."""
    dept_kw = {"department_id": department_filter} if department_filter else {}
    stats = {
        "total_students": count_table(db, "user_profiles", role="student", **dept_kw),
        "total_courses": count_table(db, "courses", **dept_kw),
        "pending_admissions": 0,
        "pending_clearances": 0,
        "completed_clearances": 0,
    }
    if include_trainers:
        stats["total_trainers"] = count_table(db, "user_profiles", role="trainer", **dept_kw)

    cl = clearance_kpi(db, department_id=department_filter or None)
    stats["pending_clearances"] = cl["pending"]
    stats["completed_clearances"] = cl["completed"]

    try:
        q = db.table("course_applications").select("id", count="exact").eq("status", "pending")
        if department_filter:
            q = q.eq("department_id", department_filter)
        stats["pending_admissions"] = exact_count(q)
    except Exception:
        stats["pending_admissions"] = 0

    if include_certs:
        q = db.table("clearance_requests").select("id", count="exact").eq("certificate_issued", True)
        if department_filter:
            q = q.eq("department_id", department_filter)
        stats["certificates_issued"] = exact_count(q)

    return stats


def _pending_admissions_list(db, department_filter="", limit=20):
    try:
        q = (
            db.table("course_applications")
            .select("*, departments(name)")
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(limit)
        )
        if department_filter:
            q = q.eq("department_id", department_filter)
        return q.execute().data or []
    except Exception:
        return []


def _clearance_lists(db, department_filter=""):
    pending_q = (
        db.table("clearance_requests")
        .select(
            "*, departments(name), courses(name), "
            "user_profiles:user_profiles!clearance_requests_student_id_fkey(full_name, admission_no)"
        )
        .in_("status", ["pending", "in_progress", "returned"])
        .order("created_at", desc=True)
        .limit(50)
    )
    completed_q = (
        db.table("clearance_requests")
        .select(
            "*, departments(name), courses(name), "
            "user_profiles:user_profiles!clearance_requests_student_id_fkey(full_name, admission_no)"
        )
        .eq("status", "completed")
        .order("created_at", desc=True)
        .limit(50)
    )
    if department_filter:
        pending_q = pending_q.eq("department_id", department_filter)
        completed_q = completed_q.eq("department_id", department_filter)
    try:
        return pending_q.execute().data or [], completed_q.execute().data or []
    except Exception:
        # Fallback without FK alias
        pending_q = (
            db.table("clearance_requests")
            .select("*, departments(name)")
            .in_("status", ["pending", "in_progress", "returned"])
            .order("created_at", desc=True)
            .limit(50)
        )
        completed_q = (
            db.table("clearance_requests")
            .select("*, departments(name)")
            .eq("status", "completed")
            .order("created_at", desc=True)
            .limit(50)
        )
        if department_filter:
            pending_q = pending_q.eq("department_id", department_filter)
            completed_q = completed_q.eq("department_id", department_filter)
        return pending_q.execute().data or [], completed_q.execute().data or []


# ── Registrar Dashboard ─────────────────────────────────────────────────────

@admin_oversight_bp.route("/registrar")
@login_required
@registrar_required
def registrar_dashboard():
    """Registrar dashboard with read-only access to all departments."""
    db = get_service_client()
    department_filter = request.args.get('department', '')

    departments = db.table("departments").select("*").order("name").execute().data or []
    stats = _oversight_core_stats(db, department_filter)
    pending_clearances, completed_clearances = _clearance_lists(db, department_filter)
    pending_admissions = _pending_admissions_list(db, department_filter)

    return render_template("admin_oversight/registrar_dashboard.html",
                          stats=stats,
                          departments=departments,
                          department_filter=department_filter,
                          pending_clearances=pending_clearances,
                          completed_clearances=completed_clearances,
                          pending_admissions=pending_admissions)


@admin_oversight_bp.route("/registrar/clearances")
@login_required
@registrar_required
def registrar_clearances():
    """Registrar view of all clearance requests."""
    db = get_service_client()
    
    department_filter = request.args.get('department', '')
    status_filter = request.args.get('status', '')
    
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Build query
    query = (db.table("clearance_requests")
            .select("*, courses(name, code), departments(name), user_profiles(full_name, admission_no)"))
    
    if department_filter:
        query = query.eq("department_id", department_filter)
    
    if status_filter:
        query = query.eq("status", status_filter)
    
    clearances = query.order("initiated_at", desc=True).execute().data or []
    
    return render_template("admin_oversight/registrar_clearances.html",
                          clearances=clearances,
                          departments=departments,
                          department_filter=department_filter,
                          status_filter=status_filter)


# ── Deputy Principal Dashboard ─────────────────────────────────────────────

@admin_oversight_bp.route("/deputy-principal")
@login_required
@deputy_principal_required
def deputy_principal_dashboard():
    """Deputy Principal dashboard with read-only access to all departments."""
    db = get_service_client()
    department_filter = request.args.get('department', '')

    departments = db.table("departments").select("*").order("name").execute().data or []
    stats = _oversight_core_stats(
        db, department_filter, include_trainers=True, include_certs=True
    )
    pending_clearances, completed_clearances = _clearance_lists(db, department_filter)

    return render_template("admin_oversight/deputy_principal_dashboard.html",
                          stats=stats,
                          departments=departments,
                          department_filter=department_filter,
                          pending_clearances=pending_clearances,
                          completed_clearances=completed_clearances)


@admin_oversight_bp.route("/deputy-principal/academic")
@login_required
@deputy_principal_required
def deputy_principal_academic():
    """Deputy Principal view of academic activities."""
    db = get_service_client()
    
    department_filter = request.args.get('department', '')
    
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Get enrollments by department
    enrollments_query = (db.table("enrollments")
                        .select("*, classes(name, department_id, courses(name, code), departments(name)), user_profiles:student_id(full_name, admission_no)"))

    enrollments = enrollments_query.execute().data or []

    # Flatten enrollments for template compatibility; filter by department in Python
    for e in enrollments:
        cls = e.get("classes") or {}
        e["courses"] = cls.get("courses") or {}
        e["departments"] = cls.get("departments") or {}
        e["user_profiles"] = e.get("user_profiles") or {}

    if department_filter:
        enrollments = [e for e in enrollments
                       if (e.get("classes") or {}).get("department_id") == department_filter]

    # Get assessments by department
    assessments_query = (db.table("assessments")
                        .select("*, classes(department_id), units(name), user_profiles:user_profiles!assessments_student_id_fkey(full_name, admission_no)"))

    assessments = assessments_query.execute().data or []

    if department_filter:
        assessments = [a for a in assessments
                       if (a.get("classes") or {}).get("department_id") == department_filter]
    
    return render_template("admin_oversight/deputy_principal_academic.html",
                          enrollments=enrollments,
                          assessments=assessments,
                          departments=departments,
                          department_filter=department_filter)


@admin_oversight_bp.route("/deputy-principal/clearances")
@login_required
@deputy_principal_required
def deputy_principal_clearances():
    """Deputy Principal view of all clearance requests."""
    db = get_service_client()
    
    department_filter = request.args.get('department', '')
    status_filter = request.args.get('status', '')
    
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Build query
    query = (db.table("clearance_requests")
            .select("*, courses(name, code), departments(name), user_profiles(full_name, admission_no)"))
    
    if department_filter:
        query = query.eq("department_id", department_filter)
    
    if status_filter:
        query = query.eq("status", status_filter)
    
    clearances = query.order("initiated_at", desc=True).execute().data or []
    
    return render_template("admin_oversight/deputy_principal_clearances.html",
                          clearances=clearances,
                          departments=departments,
                          department_filter=department_filter,
                          status_filter=status_filter)


# ── Quality Assurance Officer Dashboard ─────────────────────────────────────

@admin_oversight_bp.route("/quality-assurance")
@login_required
@quality_assurance_officer_required
def quality_assurance_dashboard():
    """Quality Assurance Officer dashboard with read-only access and approval rights."""
    db = get_service_client()
    department_filter = request.args.get('department', '')

    departments = db.table("departments").select("*").order("name").execute().data or []
    stats = _oversight_core_stats(
        db, department_filter, include_trainers=True, include_certs=True
    )

    # Assessments via units.department_id (no assessments.department_id column)
    try:
        if department_filter:
            stats["total_assessments"] = exact_count(
                db.table("assessments")
                .select("id, units!inner(department_id)", count="exact")
                .eq("units.department_id", department_filter)
            )
            stats["approved_assessments"] = exact_count(
                db.table("assessments")
                .select("id, units!inner(department_id)", count="exact")
                .eq("units.department_id", department_filter)
                .eq("status", "approved")
            )
        else:
            stats["total_assessments"] = count_table(db, "assessments")
            stats["approved_assessments"] = count_table(db, "assessments", status="approved")
    except Exception:
        stats["total_assessments"] = 0
        stats["approved_assessments"] = 0

    pending_clearances, completed_clearances = _clearance_lists(db, department_filter)
    pending_admissions = _pending_admissions_list(db, department_filter)

    return render_template("admin_oversight/quality_assurance_dashboard.html",
                          stats=stats,
                          departments=departments,
                          department_filter=department_filter,
                          pending_clearances=pending_clearances,
                          completed_clearances=completed_clearances,
                          pending_admissions=pending_admissions)


@admin_oversight_bp.route("/quality-assurance/reports")
@login_required
@quality_assurance_officer_required
def quality_assurance_reports():
    """Quality Assurance Officer view of reports and analysis."""
    db = get_service_client()
    
    department_filter = request.args.get('department', '')
    report_type = request.args.get('report_type', '')
    
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Get department performance data
    department_performance = []
    for dept in departments:
        if department_filter and dept['id'] != department_filter:
            continue
        
        # Get students in department
        dept_students = (db.table("user_profiles")
                        .select("*")
                        .eq("role", "student")
                        .eq("department_id", dept['id'])
                        .execute().data or [])
        
        # Get courses in department
        dept_courses = (db.table("courses")
                      .select("*")
                      .eq("department_id", dept['id'])
                      .execute().data or [])
        
        # Get completed clearances
        dept_clearances = (db.table("clearance_requests")
                          .select("*")
                          .eq("department_id", dept['id'])
                          .eq("status", "completed")
                          .execute().data or [])
        
        # Get assessments
        dept_assessments = (db.table("assessments")
                           .select("*")
                           .eq("department_id", dept['id'])
                           .execute().data or [])
        
        department_performance.append({
            'department': dept['name'],
            'students': len(dept_students),
            'courses': len(dept_courses),
            'completed_clearances': len(dept_clearances),
            'total_assessments': len(dept_assessments),
            'approved_assessments': sum(1 for a in dept_assessments if a['status'] == 'approved')
        })
    
    return render_template("admin_oversight/quality_assurance_reports.html",
                          department_performance=department_performance,
                          departments=departments,
                          department_filter=department_filter,
                          report_type=report_type)


@admin_oversight_bp.route("/quality-assurance/approvals")
@login_required
@quality_assurance_officer_required
def quality_assurance_approvals():
    """Quality Assurance Officer view for approval/rejection of assessments and other items."""
    db = get_service_client()
    
    department_filter = request.args.get('department', '')
    
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Get pending assessments for review
    assessments_query = (db.table("assessments")
                        .select("*, units(name, code), user_profiles(full_name, admission_no), departments(name)"))
    
    if department_filter:
        assessments_query = assessments_query.eq("department_id", department_filter)
    
    pending_assessments = assessments_query.eq("status", "pending").execute().data or []
    
    return render_template("admin_oversight/quality_assurance_approvals.html",
                          pending_assessments=pending_assessments,
                          departments=departments,
                          department_filter=department_filter)
