"""
Admin Oversight Blueprint for Registrar, Deputy Principal, and Quality Assurance Officer
Provides read-only access to all departmental activities with filtering capabilities
"""

from flask import Blueprint, render_template, request
from auth_utils import login_required, registrar_required, deputy_principal_required, quality_assurance_officer_required, current_user
from db import get_service_client

admin_oversight_bp = Blueprint('admin_oversight', __name__, url_prefix='/admin-oversight')


# ── Registrar Dashboard ─────────────────────────────────────────────────────

@admin_oversight_bp.route("/registrar")
@login_required
@registrar_required
def registrar_dashboard():
    """Registrar dashboard with read-only access to all departments."""
    db = get_service_client()
    
    # Get filter parameters
    department_filter = request.args.get('department', '')
    
    # Get all departments
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Get statistics across all departments
    stats = {
        'total_students': 0,
        'total_courses': 0,
        'pending_admissions': 0,
        'pending_clearances': 0,
        'completed_clearances': 0
    }
    
    # Build query for students
    students_query = db.table("user_profiles").select("*").eq("role", "student")
    if department_filter:
        students_query = students_query.eq("department_id", department_filter)
    students = students_query.execute().data or []
    stats['total_students'] = len(students)
    
    # Build query for courses
    courses_query = db.table("courses").select("*")
    if department_filter:
        courses_query = courses_query.eq("department_id", department_filter)
    courses = courses_query.execute().data or []
    stats['total_courses'] = len(courses)
    
    # Build query for pending admissions
    admissions_query = (db.table("admission_requests")
                       .select("*, departments(name)")
                       .eq("status", "pending"))
    if department_filter:
        admissions_query = admissions_query.eq("department_id", department_filter)
    pending_admissions = admissions_query.execute().data or []
    stats['pending_admissions'] = len(pending_admissions)
    
    # Build query for pending clearances
    clearances_query = (db.table("clearance_requests")
                       .select("*, departments(name)")
                       .in_("status", ["pending", "in_progress"]))
    if department_filter:
        clearances_query = clearances_query.eq("department_id", department_filter)
    pending_clearances = clearances_query.execute().data or []
    stats['pending_clearances'] = len(pending_clearances)
    
    # Build query for completed clearances
    completed_clearances_query = (db.table("clearance_requests")
                                  .select("*, departments(name)")
                                  .eq("status", "completed"))
    if department_filter:
        completed_clearances_query = completed_clearances_query.eq("department_id", department_filter)
    completed_clearances = completed_clearances_query.execute().data or []
    stats['completed_clearances'] = len(completed_clearances)
    
    return render_template("admin_oversight/registrar_dashboard.html",
                          stats=stats,
                          departments=departments,
                          department_filter=department_filter,
                          pending_admissions=pending_admissions,
                          pending_clearances=pending_clearances,
                          completed_clearances=completed_clearances)


@admin_oversight_bp.route("/registrar/admissions")
@login_required
@registrar_required
def registrar_admissions():
    """Registrar view of all admission requests."""
    db = get_service_client()
    
    department_filter = request.args.get('department', '')
    status_filter = request.args.get('status', '')
    
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Build query
    query = (db.table("admission_requests")
            .select("*, courses(name, code), departments(name), user_profiles(full_name, admission_no, email)"))
    
    if department_filter:
        query = query.eq("department_id", department_filter)
    
    if status_filter:
        query = query.eq("status", status_filter)
    
    admissions = query.order("submitted_at", desc=True).execute().data or []
    
    return render_template("admin_oversight/registrar_admissions.html",
                          admissions=admissions,
                          departments=departments,
                          department_filter=department_filter,
                          status_filter=status_filter)


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
    
    # Get filter parameters
    department_filter = request.args.get('department', '')
    
    # Get all departments
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Get statistics across all departments
    stats = {
        'total_students': 0,
        'total_courses': 0,
        'total_trainers': 0,
        'pending_clearances': 0,
        'completed_clearances': 0,
        'certificates_issued': 0
    }
    
    # Build query for students
    students_query = db.table("user_profiles").select("*").eq("role", "student")
    if department_filter:
        students_query = students_query.eq("department_id", department_filter)
    students = students_query.execute().data or []
    stats['total_students'] = len(students)
    
    # Build query for courses
    courses_query = db.table("courses").select("*")
    if department_filter:
        courses_query = courses_query.eq("department_id", department_filter)
    courses = courses_query.execute().data or []
    stats['total_courses'] = len(courses)
    
    # Build query for trainers
    trainers_query = db.table("user_profiles").select("*").eq("role", "trainer")
    if department_filter:
        trainers_query = trainers_query.eq("department_id", department_filter)
    trainers = trainers_query.execute().data or []
    stats['total_trainers'] = len(trainers)
    
    # Build query for pending clearances
    clearances_query = (db.table("clearance_requests")
                       .select("*, departments(name)")
                       .in_("status", ["pending", "in_progress"]))
    if department_filter:
        clearances_query = clearances_query.eq("department_id", department_filter)
    pending_clearances = clearances_query.execute().data or []
    stats['pending_clearances'] = len(pending_clearances)
    
    # Build query for completed clearances
    completed_clearances_query = (db.table("clearance_requests")
                                  .select("*, departments(name)")
                                  .eq("status", "completed"))
    if department_filter:
        completed_clearances_query = completed_clearances_query.eq("department_id", department_filter)
    completed_clearances = completed_clearances_query.execute().data or []
    stats['completed_clearances'] = len(completed_clearances)
    
    # Count certificates issued
    certificates_query = (db.table("clearance_requests")
                         .select("*")
                         .eq("certificate_issued", True))
    if department_filter:
        certificates_query = certificates_query.eq("department_id", department_filter)
    certificates = certificates_query.execute().data or []
    stats['certificates_issued'] = len(certificates)
    
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
                        .select("*, courses(name, code), departments(name), user_profiles(full_name, admission_no)"))
    
    if department_filter:
        enrollments_query = enrollments_query.eq("department_id", department_filter)
    
    enrollments = enrollments_query.execute().data or []
    
    # Get assessments by department
    assessments_query = (db.table("assessments")
                        .select("*, units(name), user_profiles(full_name, admission_no)"))
    
    if department_filter:
        assessments_query = assessments_query.eq("department_id", department_filter)
    
    assessments = assessments_query.execute().data or []
    
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
    
    # Get filter parameters
    department_filter = request.args.get('department', '')
    
    # Get all departments
    departments = (db.table("departments")
                  .select("*")
                  .execute().data or [])
    
    # Get statistics across all departments
    stats = {
        'total_students': 0,
        'total_courses': 0,
        'total_trainers': 0,
        'pending_admissions': 0,
        'pending_clearances': 0,
        'completed_clearances': 0,
        'certificates_issued': 0,
        'total_assessments': 0,
        'approved_assessments': 0
    }
    
    # Build query for students
    students_query = db.table("user_profiles").select("*").eq("role", "student")
    if department_filter:
        students_query = students_query.eq("department_id", department_filter)
    students = students_query.execute().data or []
    stats['total_students'] = len(students)
    
    # Build query for courses
    courses_query = db.table("courses").select("*")
    if department_filter:
        courses_query = courses_query.eq("department_id", department_filter)
    courses = courses_query.execute().data or []
    stats['total_courses'] = len(courses)
    
    # Build query for trainers
    trainers_query = db.table("user_profiles").select("*").eq("role", "trainer")
    if department_filter:
        trainers_query = trainers_query.eq("department_id", department_filter)
    trainers = trainers_query.execute().data or []
    stats['total_trainers'] = len(trainers)
    
    # Build query for pending admissions
    admissions_query = (db.table("admission_requests")
                       .select("*, departments(name)")
                       .eq("status", "pending"))
    if department_filter:
        admissions_query = admissions_query.eq("department_id", department_filter)
    pending_admissions = admissions_query.execute().data or []
    stats['pending_admissions'] = len(pending_admissions)
    
    # Build query for pending clearances
    clearances_query = (db.table("clearance_requests")
                       .select("*, departments(name)")
                       .in_("status", ["pending", "in_progress"]))
    if department_filter:
        clearances_query = clearances_query.eq("department_id", department_filter)
    pending_clearances = clearances_query.execute().data or []
    stats['pending_clearances'] = len(pending_clearances)
    
    # Build query for completed clearances
    completed_clearances_query = (db.table("clearance_requests")
                                  .select("*, departments(name)")
                                  .eq("status", "completed"))
    if department_filter:
        completed_clearances_query = completed_clearances_query.eq("department_id", department_filter)
    completed_clearances = completed_clearances_query.execute().data or []
    stats['completed_clearances'] = len(completed_clearances)
    
    # Count certificates issued
    certificates_query = (db.table("clearance_requests")
                         .select("*")
                         .eq("certificate_issued", True))
    if department_filter:
        certificates_query = certificates_query.eq("department_id", department_filter)
    certificates = certificates_query.execute().data or []
    stats['certificates_issued'] = len(certificates)
    
    # Build query for assessments
    assessments_query = db.table("assessments").select("*")
    if department_filter:
        assessments_query = assessments_query.eq("department_id", department_filter)
    assessments = assessments_query.execute().data or []
    stats['total_assessments'] = len(assessments)
    stats['approved_assessments'] = sum(1 for a in assessments if a['status'] == 'approved')
    
    return render_template("admin_oversight/quality_assurance_dashboard.html",
                          stats=stats,
                          departments=departments,
                          department_filter=department_filter,
                          pending_admissions=pending_admissions,
                          pending_clearances=pending_clearances,
                          completed_clearances=completed_clearances)


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
