"""
routes/dept_admin_merged.py — Department Admin blueprint (merged system).

Combines features from both:
- Attendance management (from original)
- E-Portfolio management (from copy)
- User management for department (from copy)
- Class/Unit management (from both)

Dept Admin manages ONLY their assigned department.
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, abort, make_response)
from auth_utils import (dept_admin_required, write_audit_log,
                                current_user, dept_isolation_check)
from db import get_service_client
from datetime import datetime
import secrets
import string

dept_admin_bp = Blueprint("dept_admin", __name__)


def _dept_id():
    """Return the current dept admin's department id, or abort 403."""
    user = current_user()
    dept = user.get("department_id")
    if not dept:
        abort(403)
    return dept


def generate_temp_password(length=10):
    chars = string.ascii_letters + string.digits + '!@#$'
    return ''.join(secrets.choice(chars) for _ in range(length))


# ── Dashboard ─────────────────────────────────────────────────────────────────

@dept_admin_bp.route("/")
@dept_admin_bp.route("/dashboard")
@dept_admin_required
def dashboard():
    db = get_service_client()
    dept_id = _dept_id()

    dept = db.table("departments").select("*").eq("id", dept_id).single().execute().data or {}

    stats = {}
    recent_assessments = []
    units_list = []

    try:
        # Basic counts
        stats['classes'] = db.table("classes").select("id", count="exact").eq("department_id", dept_id).execute().count or 0
        stats['trainers'] = db.table("user_profiles").select("id", count="exact").eq("role", "trainer").eq("department_id", dept_id).execute().count or 0
        stats['students'] = db.table("user_profiles").select("id", count="exact").eq("role", "student").eq("department_id", dept_id).execute().count or 0
        stats['units'] = db.table("units").select("id", count="exact").eq("department_id", dept_id).execute().count or 0
        stats['assessments'] = db.table("assessments").select("id", count="exact").execute().count or 0

        # Recent assessments
        recent_assessments = (
            db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name), classes(name)")
            .order("uploaded_at", desc=True)
            .limit(10)
            .execute().data or []
        )

        # Units list
        units_list = db.table("units").select("id, name").eq("department_id", dept_id).order("name").execute().data or []

    except Exception as e:
        flash(f'Error loading dashboard: {e}', 'danger')

    return render_template("dept_admin/dashboard.html",
                           dept=dept,
                           stats=stats,
                           recent_assessments=recent_assessments,
                           units_list=units_list)


# ── Classes Management ─────────────────────────────────────────────────────────

@dept_admin_bp.route("/classes", methods=["GET", "POST"])
@dept_admin_required
def classes():
    db = get_service_client()
    dept_id = _dept_id()
    error = None

    if request.method == "POST":
        action = request.form.get("action", "create")
        if action == "create":
            name = request.form.get("name", "").strip().upper()
            course_id = request.form.get("course_id")
            intake_year = request.form.get("intake_year")
            intake_month = request.form.get("intake_month")
            level = request.form.get("level")
            cycle = request.form.get("cycle")

            if not name or not course_id:
                error = "Class name and course are required."
            else:
                try:
                    db.table("classes").insert({
                        "name": name,
                        "course_id": course_id,
                        "department_id": dept_id,
                        "intake_year": intake_year,
                        "intake_month": intake_month,
                        "level": level,
                        "cycle": cycle
                    }).execute()
                    write_audit_log("create_class", target=name)
                    flash("Class added.", "success")
                    return redirect(url_for("dept_admin.classes"))
                except Exception as exc:
                    error = f"Error: {exc}"
        elif action == "delete":
            class_id = request.form.get("class_id")
            # Verify class belongs to this dept before deleting
            row = db.table("classes").select("department_id").eq("id", class_id).single().execute().data
            if not row or row["department_id"] != dept_id:
                abort(403)
            db.table("classes").delete().eq("id", class_id).execute()
            write_audit_log("delete_class", target=str(class_id))
            flash("Class deleted.", "success")
            return redirect(url_for("dept_admin.classes"))

    classes_list = db.table("classes").select("*, courses(name)").eq("department_id", dept_id).order("name").execute().data or []
    courses = db.table("courses").select("*").eq("department_id", dept_id).order("name").execute().data or []

    return render_template("dept_admin/classes.html",
                          classes=classes_list,
                          courses=courses,
                          error=error)


# ── Units Management ───────────────────────────────────────────────────────────

@dept_admin_bp.route("/units", methods=["GET", "POST"])
@dept_admin_required
def units():
    db = get_service_client()
    dept_id = _dept_id()
    error = None

    if request.method == "POST" and request.form.get("add_unit"):
        code = request.form.get("code", "").strip().upper()
        name = request.form.get("name", "").strip()
        course_id = request.form.get("course_id")

        if not all([code, name, course_id]):
            error = "Code, name, and course are required."
        else:
            try:
                db.table("units").insert({
                    "code": code,
                    "name": name,
                    "department_id": dept_id,
                    "course_id": course_id
                }).execute()
                write_audit_log("create_unit", target=code)
                flash("Unit added successfully.", "success")
                return redirect(url_for("dept_admin.units"))
            except Exception as exc:
                error = f"Error: {exc}"

    units_list = db.table("units").select("*, courses(name)").eq("department_id", dept_id).order("code").execute().data or []
    courses = db.table("courses").select("*").eq("department_id", dept_id).order("name").execute().data or []

    return render_template("dept_admin/units.html",
                          units=units_list,
                          courses=courses,
                          error=error)


# ── Trainers Management ───────────────────────────────────────────────────────

@dept_admin_bp.route("/trainers", methods=["GET", "POST"])
@dept_admin_required
def trainers():
    db = get_service_client()
    dept_id = _dept_id()
    error = None

    if request.method == "POST" and request.form.get("add_trainer"):
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        staff_no = request.form.get("staff_no", "").strip()
        password = generate_temp_password()

        if not all([email, full_name]):
            error = "Email and full name are required."
        else:
            try:
                # Check if email exists
                existing = db.table("user_profiles").select("id").eq("email", email).execute()
                if existing.data:
                    error = "Email already exists."
                else:
                    from auth_utils import create_staff_auth_user
                    user_id = create_staff_auth_user(
                        email=email,
                        password=password,
                        full_name=full_name,
                        role="trainer",
                        department_id=dept_id
                    )
                    # Update staff_no
                    db.table("user_profiles").update({"staff_no": staff_no}).eq("id", user_id).execute()
                    write_audit_log("create_trainer", target=f"user:{user_id}")
                    flash(f"Trainer added. Temporary password: {password}", "success")
                    return redirect(url_for("dept_admin.trainers"))
            except Exception as exc:
                error = f"Error: {exc}"

    trainers_list = db.table("user_profiles").select("*").eq("role", "trainer").eq("department_id", dept_id).order("full_name").execute().data or []

    return render_template("dept_admin/trainers.html",
                          trainers=trainers_list,
                          error=error)


# ── Students Management ───────────────────────────────────────────────────────

@dept_admin_bp.route("/students", methods=["GET", "POST"])
@dept_admin_required
def students():
    db = get_service_client()
    dept_id = _dept_id()
    error = None

    if request.method == "POST" and request.form.get("add_student"):
        admission_no = request.form.get("admission_no", "").strip()
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        class_id = request.form.get("class_id")
        password = generate_temp_password()

        if not all([admission_no, email, full_name, class_id]):
            error = "All fields are required."
        else:
            try:
                # Check if admission number exists
                existing = db.table("user_profiles").select("id").eq("admission_no", admission_no).execute()
                if existing.data:
                    error = "Admission number already exists."
                else:
                    from auth_utils import create_student_auth_user
                    user_id = create_student_auth_user(
                        admission_no=admission_no,
                        password=password,
                        email=email,
                        full_name=full_name,
                        department_id=dept_id,
                        class_id=class_id
                    )
                    # Enroll in class
                    db.table("enrollments").insert({
                        "student_id": user_id,
                        "class_id": class_id
                    }).execute()
                    write_audit_log("create_student", target=f"user:{user_id}")
                    flash(f"Student added. Temporary password: {password}", "success")
                    return redirect(url_for("dept_admin.students"))
            except Exception as exc:
                error = f"Error: {exc}"

    students_list = db.table("user_profiles").select("*, classes(name)").eq("role", "student").eq("department_id", dept_id).order("full_name").execute().data or []
    classes = db.table("classes").select("*").eq("department_id", dept_id).order("name").execute().data or []

    return render_template("dept_admin/students.html",
                          students=students_list,
                          classes=classes,
                          error=error)


# ── Assign Units to Trainers ─────────────────────────────────────────────────

@dept_admin_bp.route("/trainer-units", methods=["GET", "POST"])
@dept_admin_required
def trainer_units():
    db = get_service_client()
    dept_id = _dept_id()
    error = None

    if request.method == "POST" and request.form.get("assign"):
        trainer_id = request.form.get("trainer_id")
        unit_id = request.form.get("unit_id")

        if not all([trainer_id, unit_id]):
            error = "Trainer and unit are required."
        else:
            try:
                db.table("trainer_units").insert({
                    "trainer_id": trainer_id,
                    "unit_id": unit_id
                }).execute()
                write_audit_log("assign_unit", target=f"trainer:{trainer_id}")
                flash("Unit assigned successfully.", "success")
                return redirect(url_for("dept_admin.trainer_units"))
            except Exception as exc:
                error = f"Error: {exc}"

    assignments = db.table("trainer_units").select("*, user_profiles(full_name), units(name, code)").execute().data or []
    trainers = db.table("user_profiles").select("*").eq("role", "trainer").eq("department_id", dept_id).order("full_name").execute().data or []
    units = db.table("units").select("*").eq("department_id", dept_id).order("name").execute().data or []

    return render_template("dept_admin/trainer_units.html",
                          assignments=assignments,
                          trainers=trainers,
                          units=units,
                          error=error)


# ── Attendance Overview ───────────────────────────────────────────────────────

@dept_admin_bp.route("/attendance")
@dept_admin_required
def attendance():
    db = get_service_client()
    dept_id = _dept_id()

    # Get recent attendance records
    attendance_list = db.table("attendance").select("*, user_profiles(full_name, admission_no), units(name, code), classes(name)").order("attendance_date", desc=True).limit(100).execute().data or []

    return render_template("dept_admin/attendance.html",
                          attendance=attendance_list)


# ── Assessments Overview ──────────────────────────────────────────────────────

@dept_admin_bp.route("/assessments")
@dept_admin_required
def assessments():
    db = get_service_client()
    dept_id = _dept_id()

    # Get recent assessments
    assessments_list = db.table("assessments").select("*, user_profiles(full_name, admission_no), units(name, code), classes(name)").order("uploaded_at", desc=True).limit(100).execute().data or []

    return render_template("dept_admin/assessments.html",
                          assessments=assessments_list)


# ── Download Unit Report (CSV) ─────────────────────────────────────────────────

@dept_admin_bp.route("/download-unit-report/<unit_id>")
@dept_admin_required
def download_unit_report(unit_id):
    db = get_service_client()
    dept_id = _dept_id()

    try:
        # Get unit details
        unit = db.table("units").select("*").eq("id", unit_id).single().execute().data
        if not unit or unit.get("department_id") != dept_id:
            abort(403)

        # Get all assessments for this unit
        assessments = db.table("assessments").select("*, user_profiles(full_name, admission_no), classes(name)").eq("unit_id", unit_id).execute().data or []

        # Generate CSV
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow(["Admission No", "Full Name", "Class", "Assessment Type", "Assessment No", "Term", "Cycle", "Year", "Status", "Reviewed By", "Reviewed At"])
        
        for a in assessments:
            writer.writerow([
                a.get("user_profiles", {}).get("admission_no", ""),
                a.get("user_profiles", {}).get("full_name", ""),
                a.get("classes", {}).get("name", ""),
                a.get("assessment_type", ""),
                a.get("assessment_no", ""),
                a.get("term", ""),
                a.get("cycle", ""),
                a.get("year", ""),
                a.get("status", ""),
                a.get("reviewed_by", ""),
                a.get("reviewed_at", "")
            ])

        output.seek(0)
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename=unit_report_{unit['code']}.csv"
        response.headers["Content-type"] = "text/csv"
        return response

    except Exception as e:
        flash(f"Error generating report: {e}", "danger")
        return redirect(url_for("dept_admin.dashboard"))


# ── Exam Bookings Approval ─────────────────────────────────────────────────────

@dept_admin_bp.route("/exam-bookings")
@dept_admin_required
def exam_bookings():
    """View all exam bookings in the department."""
    db = get_service_client()
    dept_id = _dept_id()
    
    bookings = (db.table("exam_bookings")
                .select("*, units(name, code), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, classes(name)), user_profiles!exam_bookings_approved_by_fkey(full_name)")
                .eq("status", "pending")
                .order("created_at", desc=True)
                .execute().data or [])
    
    # Filter by department
    dept_bookings = [b for b in bookings if b.get("units", {}).get("department_id") == dept_id]
    
    return render_template("dept_admin/exam_bookings.html", bookings=dept_bookings)


@dept_admin_bp.route("/exam-bookings/<booking_id>/approve", methods=["POST"])
@dept_admin_required
def approve_exam_booking(booking_id):
    """Approve an exam booking."""
    db = get_service_client()
    dept_id = _dept_id()
    user = current_user()
    
    booking = db.table("exam_bookings").select("*").eq("id", booking_id).single().execute().data
    
    if not booking:
        abort(404)
    
    # Check if booking belongs to department
    unit = db.table("units").select("department_id").eq("id", booking["unit_id"]).single().execute().data
    if not unit or unit["department_id"] != dept_id:
        abort(403)
    
    try:
        db.table("exam_bookings").update({
            "status": "approved",
            "approved_by": user["id"],
            "approved_at": datetime.now().isoformat()
        }).eq("id", booking_id).execute()
        
        write_audit_log("approve_exam_booking", target=f"booking:{booking_id}")
        
        # Notify student
        from notifications import create_notification
        create_notification(
            user_id=booking["student_id"],
            title="Exam Booking Approved",
            message=f"Your exam booking for {booking.get('exam_date')} has been approved.",
            notification_type="success",
            action_url="/student/exam-bookings"
        )
        
        flash('Exam booking approved successfully.', 'success')
    except Exception as e:
        flash(f"Error approving booking: {e}", "danger")
    
    return redirect(url_for("dept_admin.exam_bookings"))


@dept_admin_bp.route("/exam-bookings/<booking_id>/reject", methods=["POST"])
@dept_admin_required
def reject_exam_booking(booking_id):
    """Reject an exam booking."""
    db = get_service_client()
    dept_id = _dept_id()
    user = current_user()
    
    booking = db.table("exam_bookings").select("*").eq("id", booking_id).single().execute().data
    
    if not booking:
        abort(404)
    
    # Check if booking belongs to department
    unit = db.table("units").select("department_id").eq("id", booking["unit_id"]).single().execute().data
    if not unit or unit["department_id"] != dept_id:
        abort(403)
    
    rejection_reason = request.form.get("rejection_reason")
    
    try:
        db.table("exam_bookings").update({
            "status": "rejected",
            "approved_by": user["id"],
            "approved_at": datetime.now().isoformat(),
            "rejection_reason": rejection_reason
        }).eq("id", booking_id).execute()
        
        write_audit_log("reject_exam_booking", target=f"booking:{booking_id}")
        
        # Notify student
        from notifications import create_notification
        create_notification(
            user_id=booking["student_id"],
            title="Exam Booking Rejected",
            message=f"Your exam booking for {booking.get('exam_date')} has been rejected. {rejection_reason or ''}",
            notification_type="warning",
            action_url="/student/exam-bookings"
        )
        
        flash('Exam booking rejected successfully.', 'success')
    except Exception as e:
        flash(f"Error rejecting booking: {e}", "danger")
    
    return redirect(url_for("dept_admin.exam_bookings"))


# ── Marks Viewing (Read-Only) ─────────────────────────────────────────────────

@dept_admin_bp.route("/marks")
@dept_admin_required
def marks():
    """View all marks in department (read-only)."""
    db = get_service_client()
    dept_id = _dept_id()
    
    # Get filter parameters
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    class_id = request.args.get("class_id", "").strip()
    unit_id = request.args.get("unit_id", "").strip()
    
    # Build query
    query = (db.table("marks")
             .select("*, units(name, code, department_id), user_profiles!marks_student_id_fkey(full_name, admission_no), user_profiles!marks_trainer_id_fkey(full_name), classes(name, departments(name))")
             .eq("year", int(year)))
    
    if term:
        query = query.eq("term", term)
    if class_id:
        query = query.eq("class_id", class_id)
    if unit_id:
        query = query.eq("unit_id", unit_id)
    
    marks_list = query.order("created_at", desc=True).execute().data or []
    
    # Filter by department
    dept_marks = [m for m in marks_list if m.get("units", {}).get("department_id") == dept_id]
    
    # Get classes and units for filters
    classes = db.table("classes").select("*").execute().data or []
    units = db.table("units").select("*").eq("department_id", dept_id).execute().data or []
    
    return render_template("dept_admin/marks.html",
                          marks=dept_marks,
                          classes=classes,
                          units=units,
                          year=year,
                          term=term,
                          class_id=class_id,
                          unit_id=unit_id)


@dept_admin_bp.route("/marks/download-pdf")
@dept_admin_required
def download_marks_pdf():
    """Download marks as PDF (read-only)."""
    db = get_service_client()
    dept_id = _dept_id()
    
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    class_id = request.args.get("class_id", "").strip()
    unit_id = request.args.get("unit_id", "").strip()
    
    # Build query
    query = (db.table("marks")
             .select("*, units(name, code, department_id), user_profiles!marks_student_id_fkey(full_name, admission_no), user_profiles!marks_trainer_id_fkey(full_name), classes(name, departments(name))")
             .eq("year", int(year)))
    
    if term:
        query = query.eq("term", term)
    if class_id:
        query = query.eq("class_id", class_id)
    if unit_id:
        query = query.eq("unit_id", unit_id)
    
    marks_list = query.order("classes(name), units(code), user_profiles!marks_student_id_fkey(full_name)").execute().data or []
    
    # Filter by department
    dept_marks = [m for m in marks_list if m.get("units", {}).get("department_id") == dept_id]
    
    return render_template("dept_admin/marks_pdf.html",
                          marks=dept_marks,
                          year=year,
                          term=term,
                          class_id=class_id,
                          unit_id=unit_id)


# ── Trainer Documents Viewing (Read-Only) ───────────────────────────────────────

@dept_admin_bp.route("/trainer-documents")
@dept_admin_required
def trainer_documents():
    """View trainer documents in department (read-only)."""
    db = get_service_client()
    dept_id = _dept_id()
    
    # Get filter parameters
    document_type = request.args.get("document_type", "").strip()
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    trainer_id = request.args.get("trainer_id", "").strip()
    
    # Build query
    query = (db.table("trainer_documents")
             .select("*, units(name, code, department_id), classes(name), user_profiles(full_name, admission_no)")
             .eq("academic_year", int(year)))
    
    if term:
        query = query.eq("term", term)
    if document_type:
        query = query.eq("document_type", document_type)
    if trainer_id:
        query = query.eq("trainer_id", trainer_id)
    
    documents_list = query.order("created_at", desc=True).execute().data or []
    
    # Filter by department
    dept_documents = [d for d in documents_list if d.get("units", {}).get("department_id") == dept_id]
    
    # Get trainers in department
    trainers = (db.table("user_profiles")
               .select("*")
               .eq("role", "trainer")
               .execute().data or [])
    
    return render_template("dept_admin/trainer_documents.html",
                          documents=dept_documents,
                          trainers=trainers,
                          document_type=document_type,
                          year=year,
                          term=term,
                          trainer_id=trainer_id)


# ── Company Management (Dual Training) ─────────────────────────────────────────

@dept_admin_bp.route("/companies")
@dept_admin_required
def companies():
    """Manage industry partner companies."""
    db = get_service_client()
    dept_id = _dept_id()
    
    # Get filter parameters
    industry = request.args.get("industry", "").strip()
    
    # Build query
    query = (db.table("companies")
             .select("*")
             .eq("department_id", dept_id))
    
    if industry:
        query = query.eq("industry_classification", industry)
    
    companies_list = query.order("name").execute().data or []
    
    # Get industry classifications for filter
    industries = [
        'Electrical Engineering',
        'Mechanical Engineering',
        'Information Technology',
        'Civil Engineering',
        'Automotive Engineering',
        'Hospitality',
        'Business Management',
        'Health Sciences',
        'Agriculture',
        'Construction',
        'Manufacturing',
        'Other'
    ]
    
    return render_template("dept_admin/companies.html",
                          companies=companies_list,
                          industries=industries,
                          industry=industry)


@dept_admin_bp.route("/companies/add", methods=["POST"])
@dept_admin_required
def add_company():
    """Add a new company."""
    db = get_service_client()
    dept_id = _dept_id()
    user = current_user()
    
    name = request.form.get("name")
    industry_classification = request.form.get("industry_classification")
    address = request.form.get("address")
    city = request.form.get("city")
    phone_number = request.form.get("phone_number")
    email = request.form.get("email")
    website = request.form.get("website")
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    geofence_radius_meters = request.form.get("geofence_radius_meters", 300)
    available_slots = request.form.get("available_slots", 0)
    contact_person = request.form.get("contact_person")
    contact_phone = request.form.get("contact_phone")
    contact_email = request.form.get("contact_email")
    description = request.form.get("description")
    
    if not all([name, industry_classification]):
        flash("Name and industry classification are required.", "error")
        return redirect(url_for("dept_admin.companies"))
    
    try:
        db.table("companies").insert({
            "name": name,
            "industry_classification": industry_classification,
            "address": address,
            "city": city,
            "phone_number": phone_number,
            "email": email,
            "website": website,
            "latitude": float(latitude) if latitude else None,
            "longitude": float(longitude) if longitude else None,
            "geofence_radius_meters": int(geofence_radius_meters),
            "available_slots": int(available_slots),
            "department_id": dept_id,
            "contact_person": contact_person,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "description": description,
            "created_by": user["id"]
        }).execute()
        
        write_audit_log("add_company", target=f"company:{name}")
        flash("Company added successfully.", "success")
    except Exception as e:
        flash(f"Error adding company: {e}", "error")
    
    return redirect(url_for("dept_admin.companies"))


@dept_admin_bp.route("/companies/<company_id>/edit", methods=["POST"])
@dept_admin_required
def edit_company(company_id):
    """Edit a company."""
    db = get_service_client()
    dept_id = _dept_id()
    
    # Verify company belongs to department
    company = (db.table("companies")
              .select("*")
              .eq("id", company_id)
              .single()
              .execute().data)
    
    if not company or company.get("department_id") != dept_id:
        abort(403)
    
    name = request.form.get("name")
    industry_classification = request.form.get("industry_classification")
    address = request.form.get("address")
    city = request.form.get("city")
    phone_number = request.form.get("phone_number")
    email = request.form.get("email")
    website = request.form.get("website")
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    geofence_radius_meters = request.form.get("geofence_radius_meters")
    available_slots = request.form.get("available_slots")
    contact_person = request.form.get("contact_person")
    contact_phone = request.form.get("contact_phone")
    contact_email = request.form.get("contact_email")
    description = request.form.get("description")
    is_active = request.form.get("is_active") == "on"
    
    try:
        update_data = {
            "name": name,
            "industry_classification": industry_classification,
            "address": address,
            "city": city,
            "phone_number": phone_number,
            "email": email,
            "website": website,
            "geofence_radius_meters": int(geofence_radius_meters),
            "available_slots": int(available_slots),
            "contact_person": contact_person,
            "contact_phone": contact_phone,
            "contact_email": contact_email,
            "description": description,
            "is_active": is_active
        }
        
        if latitude:
            update_data["latitude"] = float(latitude)
        if longitude:
            update_data["longitude"] = float(longitude)
        
        db.table("companies").update(update_data).eq("id", company_id).execute()
        
        write_audit_log("edit_company", target=f"company:{company_id}")
        flash("Company updated successfully.", "success")
    except Exception as e:
        flash(f"Error updating company: {e}", "error")
    
    return redirect(url_for("dept_admin.companies"))


@dept_admin_bp.route("/companies/<company_id>/delete", methods=["POST"])
@dept_admin_required
def delete_company(company_id):
    """Delete a company."""
    db = get_service_client()
    dept_id = _dept_id()
    
    # Verify company belongs to department
    company = (db.table("companies")
              .select("*")
              .eq("id", company_id)
              .single()
              .execute().data)
    
    if not company or company.get("department_id") != dept_id:
        abort(403)
    
    try:
        db.table("companies").delete().eq("id", company_id).execute()
        
        write_audit_log("delete_company", target=f"company:{company_id}")
        flash("Company deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting company: {e}", "error")
    
    return redirect(url_for("dept_admin.companies"))
