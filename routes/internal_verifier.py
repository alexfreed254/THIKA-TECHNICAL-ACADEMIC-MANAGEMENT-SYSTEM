"""
Internal Verifier Blueprint for Dual Training System
Manages verification of competency assessments and CDACC compliance
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from datetime import datetime
from auth_utils import login_required, internal_verifier_required, current_user, write_audit_log
from db import get_service_client

internal_verifier_bp = Blueprint('internal_verifier', __name__)


# ── Dashboard ───────────────────────────────────────────────────────────────

@internal_verifier_bp.route("/dashboard")
@login_required
@internal_verifier_required
def dashboard():
    """Internal verifier dashboard showing pending verifications."""
    db = get_service_client()
    
    # Get pending competency verifications
    pending_competencies = (db.table("competency_tracking")
                           .select("*, user_profiles(full_name, admission_no), units(name, code), user_profiles!competency_tracking_assessed_by_fkey(full_name) as assessor_name")
                           .eq("verification_status", "pending")
                           .order("assessment_date", desc=True)
                           .execute().data or [])
    
    # Get statistics
    total_pending = len(pending_competencies)
    verified_count = (db.table("competency_tracking")
                     .select("*")
                     .eq("verification_status", "verified")
                     .execute().data or [])
    verified_count = len(verified_count)
    
    rejected_count = (db.table("competency_tracking")
                     .select("*")
                     .eq("verification_status", "rejected")
                     .execute().data or [])
    rejected_count = len(rejected_count)
    
    return render_template("internal_verifier/dashboard.html",
                          pending_competencies=pending_competencies,
                          total_pending=total_pending,
                          verified_count=verified_count,
                          rejected_count=rejected_count)


# ── Competency Verification ─────────────────────────────────────────────────────

@internal_verifier_bp.route("/competency")
@login_required
@internal_verifier_required
def competency():
    """View and verify competency assessments."""
    db = get_service_client()
    
    # Get filter parameters
    status = request.args.get("status", "pending")
    department_id = request.args.get("department_id", "").strip()
    
    # Build query
    query = (db.table("competency_tracking")
            .select("*, user_profiles(full_name, admission_no), units(name, code, department_id), user_profiles!competency_tracking_assessed_by_fkey(full_name) as assessor_name")
            .eq("verification_status", status))
    
    competencies = query.order("assessment_date", desc=True).execute().data or []
    
    # Filter by department if specified
    if department_id:
        competencies = [c for c in competencies if c.get("units", {}).get("department_id") == department_id]
    
    # Get departments for filter
    departments = db.table("departments").select("*").execute().data or []
    
    return render_template("internal_verifier/competency.html",
                          competencies=competencies,
                          departments=departments,
                          status=status,
                          department_id=department_id)


@internal_verifier_bp.route("/competency/<comp_id>/verify", methods=["POST"])
@login_required
@internal_verifier_required
def verify_competency(comp_id):
    """Verify a competency assessment."""
    db = get_service_client()
    user = current_user()
    
    verification_status = request.form.get("verification_status")
    verifier_comments = request.form.get("verifier_comments", "")
    
    if not verification_status:
        flash("Verification status is required.", "error")
        return redirect(url_for("internal_verifier.competency"))
    
    try:
        # Get competency
        competency = (db.table("competency_tracking")
                     .select("*")
                     .eq("id", comp_id)
                     .single()
                     .execute().data)
        
        if not competency:
            flash("Competency entry not found.", "error")
            return redirect(url_for("internal_verifier.competency"))
        
        # Update competency
        db.table("competency_tracking").update({
            "verification_status": verification_status,
            "verified_by": user["id"],
            "verified_at": datetime.now().isoformat()
        }).eq("id", comp_id).execute()
        
        # Add verifier comments if provided
        if verifier_comments:
            db.table("competency_tracking").update({
                "assessor_comments": (competency.get("assessor_comments", "") + f"\n\nVerifier Comments: {verifier_comments}")
            }).eq("id", comp_id).execute()
        
        write_audit_log("verify_competency", target=f"competency:{comp_id}")
        flash(f"Competency {verification_status} successfully.", "success")
    except Exception as e:
        flash(f"Error verifying competency: {e}", "error")
    
    return redirect(url_for("internal_verifier.competency"))


# ── Attachment Verification ───────────────────────────────────────────────────

@internal_verifier_bp.route("/attachments")
@login_required
@internal_verifier_required
def attachments():
    """View industrial attachments for verification."""
    db = get_service_client()
    
    # Get filter parameters
    status = request.args.get("status", "completed")
    department_id = request.args.get("department_id", "").strip()
    
    # Build query
    query = (db.table("industrial_attachments")
            .select("*, user_profiles(full_name, admission_no), units(name, code, department_id), companies(name)")
            .eq("status", status))
    
    attachments = query.order("end_date", desc=True).execute().data or []
    
    # Filter by department if specified
    if department_id:
        attachments = [a for a in attachments if a.get("units", {}).get("department_id") == department_id]
    
    # Get departments for filter
    departments = db.table("departments").select("*").execute().data or []
    
    return render_template("internal_verifier/attachments.html",
                          attachments=attachments,
                          departments=departments,
                          status=status,
                          department_id=department_id)


@internal_verifier_bp.route("/attachment/<attachment_id>/view")
@login_required
@internal_verifier_required
def view_attachment(attachment_id):
    """View detailed attachment information."""
    db = get_service_client()
    
    attachment = (db.table("industrial_attachments")
                 .select("*, user_profiles(full_name, admission_no, mobile_number), units(name, code), companies(name, address, contact_person, contact_phone), user_profiles!industrial_attachments_mentor_id_fkey(full_name) as mentor_name")
                 .eq("id", attachment_id)
                 .single()
                 .execute().data)
    
    if not attachment:
        flash("Attachment not found.", "error")
        return redirect(url_for("internal_verifier.attachments"))
    
    # Get competency tracking for this attachment
    competencies = (db.table("competency_tracking")
                   .select("*, units(name, code)")
                   .eq("attachment_id", attachment_id)
                   .execute().data or [])
    
    # Get digital logbook entries for this attachment
    logbooks = (db.table("digital_logbook")
               .select("*")
               .eq("attachment_id", attachment_id)
               .order("log_date", desc=True)
               .execute().data or [])
    
    return render_template("internal_verifier/view_attachment.html",
                          attachment=attachment,
                          competencies=competencies,
                          logbooks=logbooks)


# ── CDACC Compliance Reports ───────────────────────────────────────────────────

@internal_verifier_bp.route("/reports")
@login_required
@internal_verifier_required
def reports():
    """Generate CDACC compliance reports."""
    db = get_service_client()
    
    # Get filter parameters
    year = request.args.get("year", str(datetime.now().year))
    department_id = request.args.get("department_id", "").strip()
    
    # Get all completed attachments in the year
    attachments = (db.table("industrial_attachments")
                  .select("*, user_profiles(full_name, admission_no), units(name, code, department_id), companies(name)")
                  .eq("status", "completed")
                  .execute().data or [])
    
    # Filter by year
    attachments = [a for a in attachments if a.get("end_date") and str(a["end_date"]).startswith(year)]
    
    # Filter by department if specified
    if department_id:
        attachments = [a for a in attachments if a.get("units", {}).get("department_id") == department_id]
    
    # Get departments for filter
    departments = db.table("departments").select("*").execute().data or []
    
    # Calculate statistics
    total_attachments = len(attachments)
    graded_attachments = [a for a in attachments if a.get("final_grade")]
    competency_achieved = len([a for a in graded_attachments if a.get("final_grade") in ['C', 'P', 'M']])
    
    return render_template("internal_verifier/reports.html",
                          attachments=attachments,
                          departments=departments,
                          year=year,
                          department_id=department_id,
                          total_attachments=total_attachments,
                          graded_attachments=len(graded_attachments),
                          competency_achieved=competency_achieved)
