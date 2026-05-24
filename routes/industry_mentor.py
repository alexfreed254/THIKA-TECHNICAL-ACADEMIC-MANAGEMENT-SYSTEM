"""
Industry Mentor Blueprint for Dual Training System
Manages mentor-based workplace assessment, logbook approval, and competency tracking
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from datetime import datetime
from auth_utils import login_required, industry_mentor_required, current_user, write_audit_log
from db import get_service_client

industry_mentor_bp = Blueprint('industry_mentor', __name__, url_prefix='/industry-mentor')


# ── Dashboard ───────────────────────────────────────────────────────────────

@industry_mentor_bp.route("/dashboard")
@login_required
@industry_mentor_required
def dashboard():
    """Industry mentor dashboard showing assigned trainees and pending tasks."""
    db = get_service_client()
    user = current_user()
    
    # Get mentor's company
    mentor = (db.table("mentors")
             .select("*, companies(name, address)")
             .eq("user_id", user["id"])
             .single()
             .execute().data)
    
    if not mentor:
        flash("Mentor profile not found. Please contact administrator.", "error")
        return redirect(url_for("main.index"))
    
    company_id = mentor["company_id"]
    
    # Get active attachments for mentor's company
    attachments = (db.table("industrial_attachments")
                  .select("*, user_profiles(full_name, admission_no), units(name, code), companies(name)")
                  .eq("company_id", company_id)
                  .eq("status", "active")
                  .execute().data or [])
    
    # Get pending logbook approvals
    pending_logbooks = (db.table("digital_logbook")
                       .select("*, user_profiles(full_name, admission_no)")
                       .eq("mentor_approval_status", "pending")
                       .execute().data or [])
    
    # Filter logbooks by company
    company_logbooks = []
    for log in pending_logbooks:
        attachment = (db.table("industrial_attachments")
                     .select("company_id")
                     .eq("id", log["attachment_id"])
                     .single()
                     .execute().data)
        if attachment and attachment.get("company_id") == company_id:
            company_logbooks.append(log)
    
    # Get competency assessments pending verification
    pending_competencies = (db.table("competency_tracking")
                           .select("*, user_profiles(full_name, admission_no), units(name, code)")
                           .eq("verification_status", "pending")
                           .execute().data or [])
    
    # Filter competencies by company
    company_competencies = []
    for comp in pending_competencies:
        attachment = (db.table("industrial_attachments")
                     .select("company_id")
                     .eq("id", comp["attachment_id"])
                     .single()
                     .execute().data)
        if attachment and attachment.get("company_id") == company_id:
            company_competencies.append(comp)
    
    return render_template("industry_mentor/dashboard.html",
                          mentor=mentor,
                          attachments=attachments,
                          pending_logbooks=company_logbooks,
                          pending_competencies=company_competencies)


# ── Logbook Management ───────────────────────────────────────────────────────

@industry_mentor_bp.route("/logbook")
@login_required
@industry_mentor_required
def logbook():
    """View and approve trainee logbook entries."""
    db = get_service_client()
    user = current_user()
    
    # Get mentor's company
    mentor = (db.table("mentors")
             .select("company_id")
             .eq("user_id", user["id"])
             .single()
             .execute().data)
    
    if not mentor:
        abort(403)
    
    company_id = mentor["company_id"]
    
    # Get filter parameters
    status = request.args.get("status", "pending")
    
    # Build query
    query = (db.table("digital_logbook")
            .select("*, user_profiles(full_name, admission_no), industrial_attachments(start_date, end_date, companies(name))")
            .eq("mentor_approval_status", status))
    
    logbooks = query.order("log_date", desc=True).execute().data or []
    
    # Filter by company
    company_logbooks = []
    for log in logbooks:
        attachment = log.get("industrial_attachments", {})
        if attachment.get("companies", {}).get("id") == company_id:
            company_logbooks.append(log)
    
    return render_template("industry_mentor/logbook.html",
                          logbooks=company_logbooks,
                          status=status)


@industry_mentor_bp.route("/logbook/<log_id>/approve", methods=["POST"])
@login_required
@industry_mentor_required
def approve_logbook(log_id):
    """Approve a logbook entry."""
    db = get_service_client()
    user = current_user()
    
    try:
        # Get logbook
        logbook = (db.table("digital_logbook")
                  .select("*")
                  .eq("id", log_id)
                  .single()
                  .execute().data)
        
        if not logbook:
            flash("Logbook entry not found.", "error")
            return redirect(url_for("industry_mentor.logbook"))
        
        # Verify mentor can approve this logbook
        mentor = (db.table("mentors")
                 .select("company_id")
                 .eq("user_id", user["id"])
                 .single()
                 .execute().data)
        
        if not mentor:
            abort(403)
        
        attachment = (db.table("industrial_attachments")
                     .select("company_id")
                     .eq("id", logbook["attachment_id"])
                     .single()
                     .execute().data)
        
        if attachment.get("company_id") != mentor["company_id"]:
            abort(403)
        
        # Update logbook
        db.table("digital_logbook").update({
            "mentor_approval_status": "approved",
            "mentor_approved_by": user["id"],
            "mentor_approved_at": datetime.now().isoformat()
        }).eq("id", log_id).execute()
        
        write_audit_log("approve_logbook", target=f"logbook:{log_id}")
        flash("Logbook approved successfully.", "success")
    except Exception as e:
        flash(f"Error approving logbook: {e}", "error")
    
    return redirect(url_for("industry_mentor.logbook"))


@industry_mentor_bp.route("/logbook/<log_id>/reject", methods=["POST"])
@login_required
@industry_mentor_required
def reject_logbook(log_id):
    """Reject a logbook entry."""
    db = get_service_client()
    user = current_user()
    
    comments = request.form.get("comments", "")
    
    try:
        # Get logbook
        logbook = (db.table("digital_logbook")
                  .select("*")
                  .eq("id", log_id)
                  .single()
                  .execute().data)
        
        if not logbook:
            flash("Logbook entry not found.", "error")
            return redirect(url_for("industry_mentor.logbook"))
        
        # Verify mentor can approve this logbook
        mentor = (db.table("mentors")
                 .select("company_id")
                 .eq("user_id", user["id"])
                 .single()
                 .execute().data)
        
        if not mentor:
            abort(403)
        
        attachment = (db.table("industrial_attachments")
                     .select("company_id")
                     .eq("id", logbook["attachment_id"])
                     .single()
                     .execute().data)
        
        if attachment.get("company_id") != mentor["company_id"]:
            abort(403)
        
        # Update logbook
        db.table("digital_logbook").update({
            "mentor_approval_status": "rejected",
            "mentor_comments": comments,
            "mentor_approved_by": user["id"],
            "mentor_approved_at": datetime.now().isoformat()
        }).eq("id", log_id).execute()
        
        write_audit_log("reject_logbook", target=f"logbook:{log_id}")
        flash("Logbook rejected.", "warning")
    except Exception as e:
        flash(f"Error rejecting logbook: {e}", "error")
    
    return redirect(url_for("industry_mentor.logbook"))


# ── Competency Assessment ─────────────────────────────────────────────────────

@industry_mentor_bp.route("/competency")
@login_required
@industry_mentor_required
def competency():
    """View and assess trainee competencies."""
    db = get_service_client()
    user = current_user()
    
    # Get mentor's company
    mentor = (db.table("mentors")
             .select("company_id")
             .eq("user_id", user["id"])
             .single()
             .execute().data)
    
    if not mentor:
        abort(403)
    
    company_id = mentor["company_id"]
    
    # Get filter parameters
    status = request.args.get("status", "NYC")
    
    # Build query
    query = (db.table("competency_tracking")
            .select("*, user_profiles(full_name, admission_no), units(name, code), industrial_attachments(start_date, end_date, companies(name))")
            .eq("competency_status", status))
    
    competencies = query.order("assessment_date", desc=True).execute().data or []
    
    # Filter by company
    company_competencies = []
    for comp in competencies:
        attachment = comp.get("industrial_attachments", {})
        if attachment.get("companies", {}).get("id") == company_id:
            company_competencies.append(comp)
    
    return render_template("industry_mentor/competency.html",
                          competencies=company_competencies,
                          status=status)


@industry_mentor_bp.route("/competency/<comp_id>/assess", methods=["POST"])
@login_required
@industry_mentor_required
def assess_competency(comp_id):
    """Assess a competency entry."""
    db = get_service_client()
    user = current_user()
    
    competency_status = request.form.get("competency_status")
    assessor_comments = request.form.get("assessor_comments", "")
    
    if not competency_status:
        flash("Competency status is required.", "error")
        return redirect(url_for("industry_mentor.competency"))
    
    try:
        # Get competency
        competency = (db.table("competency_tracking")
                     .select("*")
                     .eq("id", comp_id)
                     .single()
                     .execute().data)
        
        if not competency:
            flash("Competency entry not found.", "error")
            return redirect(url_for("industry_mentor.competency"))
        
        # Verify mentor can assess this competency
        mentor = (db.table("mentors")
                 .select("company_id")
                 .eq("user_id", user["id"])
                 .single()
                 .execute().data)
        
        if not mentor:
            abort(403)
        
        attachment = (db.table("industrial_attachments")
                     .select("company_id")
                     .eq("id", competency["attachment_id"])
                     .single()
                     .execute().data)
        
        if attachment.get("company_id") != mentor["company_id"]:
            abort(403)
        
        # Update competency
        db.table("competency_tracking").update({
            "competency_status": competency_status,
            "assessed_by": user["id"],
            "assessment_date": datetime.now().date().isoformat(),
            "assessor_comments": assessor_comments
        }).eq("id", comp_id).execute()
        
        write_audit_log("assess_competency", target=f"competency:{comp_id}")
        flash("Competency assessed successfully.", "success")
    except Exception as e:
        flash(f"Error assessing competency: {e}", "error")
    
    return redirect(url_for("industry_mentor.competency"))


# ── Trainee Monitoring ───────────────────────────────────────────────────────

@industry_mentor_bp.route("/trainees")
@login_required
@industry_mentor_required
def trainees():
    """View all trainees assigned to mentor's company."""
    db = get_service_client()
    user = current_user()
    
    # Get mentor's company
    mentor = (db.table("mentors")
             .select("*, companies(name, address)")
             .eq("user_id", user["id"])
             .single()
             .execute().data)
    
    if not mentor:
        abort(403)
    
    company_id = mentor["company_id"]
    
    # Get all attachments for mentor's company
    attachments = (db.table("industrial_attachments")
                  .select("*, user_profiles(full_name, admission_no, mobile_number), units(name, code), companies(name)")
                  .eq("company_id", company_id)
                  .execute().data or [])
    
    return render_template("industry_mentor/trainees.html",
                          mentor=mentor,
                          attachments=attachments)


# ── Location Monitoring ───────────────────────────────────────────────────────

@industry_mentor_bp.route("/location")
@login_required
@industry_mentor_required
def location():
    """View trainee location logs for monitoring."""
    db = get_service_client()
    user = current_user()
    
    # Get mentor's company
    mentor = (db.table("mentors")
             .select("company_id")
             .eq("user_id", user["id"])
             .single()
             .execute().data)
    
    if not mentor:
        abort(403)
    
    company_id = mentor["company_id"]
    
    # Get recent location logs
    location_logs = (db.table("location_logs")
                    .select("*, user_profiles(full_name, admission_no), companies(name, latitude, longitude, geofence_radius_meters)")
                    .order("check_in_time", desc=True)
                    .limit(100)
                    .execute().data or [])
    
    # Filter by company
    company_logs = []
    for log in location_logs:
        attachment = (db.table("industrial_attachments")
                     .select("company_id")
                     .eq("id", log["attachment_id"])
                     .single()
                     .execute().data)
        if attachment and attachment.get("company_id") == company_id:
            company_logs.append(log)
    
    return render_template("industry_mentor/location.html",
                          location_logs=company_logs)
