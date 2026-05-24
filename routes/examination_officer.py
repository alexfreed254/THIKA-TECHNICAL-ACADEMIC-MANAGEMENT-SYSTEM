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
                      .select("*, units(name, code), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, classes(name))")
                      .eq("status", "approved")
                      .order("approved_at", desc=True)
                      .limit(10)
                      .execute().data or [])
    
    return render_template("examination_officer/dashboard.html",
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
    
    # Build query
    query = db.table("exam_bookings").select(
        "*, units(name, code), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, classes(name)), user_profiles!exam_bookings_approved_by_fkey(full_name)"
    ).eq("status", "approved")
    
    # Apply filters
    if admission_no:
        query = query.ilike("user_profiles.admission_no", f"%{admission_no}%")
    if trainee_name:
        query = query.ilike("user_profiles.full_name", f"%{trainee_name}%")
    if class_id:
        query = query.eq("user_profiles.classes.id", class_id)
    if year:
        query = query.gte("exam_date", f"{year}-01-01").lte("exam_date", f"{year}-12-31")
    
    bookings = query.order("exam_date", desc=True).execute().data or []
    
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
    
    booking = (db.table("exam_bookings")
               .select("*, units(name, code), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, classes(name, departments(name))), user_profiles!exam_bookings_approved_by_fkey(full_name)")
               .eq("id", booking_id)
               .single()
               .execute().data)
    
    if not booking:
        flash("Booking not found.", "danger")
        return redirect(url_for("examination_officer.exam_bookings"))
    
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
             .select("*, units(name, code), user_profiles!marks_student_id_fkey(full_name, admission_no), user_profiles!marks_trainer_id_fkey(full_name), classes(name, departments(name))")
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
             .select("*, units(name, code), user_profiles!marks_student_id_fkey(full_name, admission_no), user_profiles!marks_trainer_id_fkey(full_name), classes(name, departments(name))")
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
