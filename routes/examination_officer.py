"""
routes/examination_officer.py — Examination Officer blueprint

Examination officers can:
- View approved exam bookings
- Filter by admission number, class, trainee name, year, exam series
- Confirm exam bookings
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from auth_utils import examination_officer_required, write_audit_log, current_user
from db import get_service_client
from datetime import datetime

examination_officer_bp = Blueprint("examination_officer", __name__)


@examination_officer_bp.route("/dashboard")
@examination_officer_required
def dashboard():
    """Examination officer dashboard with statistics."""
    db = get_service_client()
    
    # Get statistics
    total_approved = db.table("exam_bookings").select("id", count="exact").eq("status", "approved").execute().count or 0
    total_pending = db.table("exam_bookings").select("id", count="exact").eq("status", "pending").execute().count or 0
    total_completed = db.table("exam_bookings").select("id", count="exact").eq("status", "completed").execute().count or 0
    
    # Get recent bookings
    recent_bookings = (db.table("exam_bookings")
                      .select("*, units(name, code), student:user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, enrollments(classes(name, departments(name)))), approver:user_profiles!exam_bookings_approved_by_fkey(full_name)")
                      .eq("status", "approved")
                      .order("approved_at", desc=True)
                      .limit(10)
                      .execute().data or [])
    
    # Flatten recent bookings
    for booking in recent_bookings:
        student = booking.get("student") or {}
        enrollments = student.get("enrollments") or []
        first_enrollment = enrollments[0] if enrollments else {}
        cls = first_enrollment.get("classes") or {}
        student["classes"] = {
            "name": cls.get("name"),
            "departments": cls.get("departments") or {}
        }
        booking["user_profiles"] = student
        booking["approved_by_user"] = booking.get("approver") or {}
    
    return render_template("examination_officer/dashboard_enhanced.html",
                          total_approved=total_approved,
                          total_pending=total_pending,
                          total_completed=total_completed,
                          recent_bookings=recent_bookings)


@examination_officer_bp.route("/exam-bookings")
@examination_officer_required
def exam_bookings():
    """View approved exam bookings with filters."""
    db = get_service_client()
    
    # Get filter parameters
    admission_no = request.args.get("admission_no", "").strip()
    class_id = request.args.get("class_id", "").strip()
    trainee_name = request.args.get("trainee_name", "").strip()
    year = request.args.get("year", "").strip()
    exam_series = request.args.get("exam_series", "").strip()
    
    # Build query with inner join if class_id is filtered
    select_str = "*, units(name, code), student:user_profiles!exam_bookings_student_id_fkey!inner(full_name, admission_no, enrollments!inner(class_id, classes(name, departments(name)))), approver:user_profiles!exam_bookings_approved_by_fkey(full_name)" if class_id else \
                 "*, units(name, code), student:user_profiles!exam_bookings_student_id_fkey!inner(full_name, admission_no, enrollments(class_id, classes(name, departments(name)))), approver:user_profiles!exam_bookings_approved_by_fkey(full_name)"
    
    query = db.table("exam_bookings").select(select_str).eq("status", "approved")

    if year:
        query = query.gte("exam_date", f"{year}-01-01").lte("exam_date", f"{year}-12-31")

    bookings = query.order("exam_date", desc=True).execute().data or []

    # Filter on joined fields in Python (PostgREST dot-notation not supported)
    if admission_no:
        bookings = [b for b in bookings
                    if admission_no.lower() in
                    ((b.get("student") or {}).get("admission_no") or "").lower()]
    if trainee_name:
        bookings = [b for b in bookings
                    if trainee_name.lower() in
                    ((b.get("student") or {}).get("full_name") or "").lower()]
    if class_id:
        bookings = [b for b in bookings
                    if any(e.get("class_id") == class_id
                           for e in ((b.get("student") or {}).get("enrollments") or []))]
    if exam_series:
        es = exam_series.lower()
        bookings = [b for b in bookings
                    if es in (b.get("exam_session") or "").lower()
                    or es in str(b.get("exam_series_no") or "").lower()
                    or es in str(b.get("exam_term") or "").lower()
                    or es in (b.get("serial_number") or "").lower()]
    
    # Flatten bookings
    for booking in bookings:
        student = booking.get("student") or {}
        enrollments = student.get("enrollments") or []
        first_enrollment = enrollments[0] if enrollments else {}
        cls = first_enrollment.get("classes") or {}
        student["classes"] = {
            "name": cls.get("name"),
            "departments": cls.get("departments") or {}
        }
        booking["user_profiles"] = student
        booking["approved_by_user"] = booking.get("approver") or {}
    
    # Get all classes for filter dropdown
    classes = db.table("classes").select("*").execute().data or []
    
    return render_template("examination_officer/exam_bookings.html",
                          bookings=bookings,
                          classes=classes,
                          filters={
                              "admission_no": admission_no,
                              "class_id": class_id,
                              "trainee_name": trainee_name,
                              "year": year,
                              "exam_series": exam_series
                          })


@examination_officer_bp.route("/exam-bookings/<booking_id>/confirm", methods=["POST"])
@examination_officer_required
def confirm_booking(booking_id):
    """Confirm an approved exam booking."""
    db = get_service_client()
    user = current_user()
    
    booking = db.table("exam_bookings").select("*").eq("id", booking_id).single().execute().data
    
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("examination_officer.exam_bookings"))
    
    if booking["status"] != "approved":
        flash("Only approved bookings can be confirmed.", "warning")
        return redirect(url_for("examination_officer.exam_bookings"))
    
    try:
        db.table("exam_bookings").update({
            "status": "completed"
        }).eq("id", booking_id).execute()
        
        write_audit_log("confirm_exam_booking", target=f"booking:{booking_id}")
        
        # Notify student
        from notifications import create_notification
        create_notification(
            user_id=booking["student_id"],
            title="Exam Booking Confirmed",
            message=f"Your exam booking for {booking.get('exam_date')} has been confirmed by the Examination Officer.",
            notification_type="success",
            action_url="/student/exam-bookings"
        )
        
        flash("Exam booking confirmed successfully.", "success")
    except Exception as e:
        flash(f"Error confirming booking: {e}", "danger")
    
    return redirect(url_for("examination_officer.exam_bookings"))


@examination_officer_bp.route("/exam-bookings/<booking_id>/view")
@examination_officer_required
def view_booking(booking_id):
    """View details of an exam booking."""
    db = get_service_client()
    
    booking_data = (db.table("exam_bookings")
                   .select("*, units(name, code), student:user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, enrollments(classes(name, departments(name)))), approver:user_profiles!exam_bookings_approved_by_fkey(full_name)")
                   .eq("id", booking_id)
                   .limit(1)
                   .execute().data)
    
    if not booking_data:
        flash("Booking not found.", "danger")
        return redirect(url_for("examination_officer.exam_bookings"))
        
    booking = booking_data[0]
    
    # Flatten booking
    student = booking.get("student") or {}
    enrollments = student.get("enrollments") or []
    first_enrollment = enrollments[0] if enrollments else {}
    cls = first_enrollment.get("classes") or {}
    student["classes"] = {
        "name": cls.get("name"),
        "departments": cls.get("departments") or {}
    }
    booking["user_profiles"] = student
    booking["approved_by_user"] = booking.get("approver") or {}
    
    return render_template("examination_officer/view_booking.html", booking=booking)


# ── Marks Viewing (Read-Only) ─────────────────────────────────────────────────

@examination_officer_bp.route("/marks")
@examination_officer_required
def marks():
    """View all marks (read-only)."""
    db = get_service_client()
    
    # Get filter parameters
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    class_id = request.args.get("class_id", "").strip()
    unit_id = request.args.get("unit_id", "").strip()
    
    # Build query
    query = (db.table("marks")
             .select("*, units(name, code), user_profiles!marks_student_id_fkey(full_name, admission_no), classes(name, departments(name))")
             .eq("year", int(year)))
    
    if term:
        query = query.eq("term", term)
    if class_id:
        query = query.eq("class_id", class_id)
    if unit_id:
        query = query.eq("unit_id", unit_id)
    
    marks_list = query.order("created_at", desc=True).execute().data or []
    
    # Get classes and units for filters
    classes = db.table("classes").select("*").execute().data or []
    units = db.table("units").select("*").execute().data or []
    
    return render_template("examination_officer/marks.html",
                          marks=marks_list,
                          classes=classes,
                          units=units,
                          year=year,
                          term=term,
                          class_id=class_id,
                          unit_id=unit_id)


@examination_officer_bp.route("/marks/download-pdf")
@examination_officer_required
def download_marks_pdf():
    """Download marks as PDF (read-only)."""
    db = get_service_client()
    
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    class_id = request.args.get("class_id", "").strip()
    unit_id = request.args.get("unit_id", "").strip()
    
    # Build query
    query = (db.table("marks")
             .select("*, units(name, code), user_profiles!marks_student_id_fkey(full_name, admission_no), classes(name, departments(name))")
             .eq("year", int(year)))
    
    if term:
        query = query.eq("term", term)
    if class_id:
        query = query.eq("class_id", class_id)
    if unit_id:
        query = query.eq("unit_id", unit_id)
    
    marks_list = query.order("classes(name), units(code), user_profiles!marks_student_id_fkey(full_name)").execute().data or []
    
    return render_template("examination_officer/marks_pdf.html",
                          marks=marks_list,
                          year=year,
                          term=term,
                          class_id=class_id,
                          unit_id=unit_id)
