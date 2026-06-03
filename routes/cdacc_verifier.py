"""
routes/cdacc_verifier.py — CDACC External Verifier blueprint.
View assessment evidence, verify assessment records, review competency docs,
generate verification reports.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from auth_utils import login_required, cdacc_verifier_required, current_user, write_audit_log
from db import get_service_client
from datetime import datetime

cdacc_verifier_bp = Blueprint("cdacc_verifier", __name__)


@cdacc_verifier_bp.route("/")
@cdacc_verifier_bp.route("/dashboard")
@login_required
@cdacc_verifier_required
def dashboard():
    db = get_service_client()
    user = current_user()
    stats = {}
    pending_assessments = []
    recent_verified = []

    try:
        stats["total"]    = db.table("assessments").select("id", count="exact").execute().count or 0
        stats["pending"]  = db.table("assessments").select("id", count="exact").eq("status", "pending").execute().count or 0
        stats["approved"] = db.table("assessments").select("id", count="exact").eq("status", "approved").execute().count or 0
        stats["rejected"] = db.table("assessments").select("id", count="exact").eq("status", "rejected").execute().count or 0

        pending_assessments = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no, departments(name)), units(name, code), classes(name)")
            .eq("status", "pending")
            .order("uploaded_at", desc=True)
            .limit(15)
            .execute().data or [])

        recent_verified = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name, code)")
            .in_("status", ["approved", "rejected"])
            .order("uploaded_at", desc=True)
            .limit(10)
            .execute().data or [])
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")

    return render_template("cdacc_verifier/dashboard.html",
                           stats=stats,
                           pending_assessments=pending_assessments,
                           recent_verified=recent_verified,
                           current_month=datetime.now().strftime("%B %Y"))


@cdacc_verifier_bp.route("/assessments")
@login_required
@cdacc_verifier_required
def assessments():
    db = get_service_client()
    status_filter = request.args.get("status", "")
    dept_filter   = request.args.get("dept", "")
    query = (db.table("assessments")
               .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no, departments(name)), units(name, code), classes(name)")
               .order("uploaded_at", desc=True)
               .limit(300))
    if status_filter:
        query = query.eq("status", status_filter)
    records = query.execute().data or []
    departments = db.table("departments").select("id, name").order("name").execute().data or []
    return render_template("cdacc_verifier/assessments.html",
                           assessments=records, departments=departments,
                           status_filter=status_filter, dept_filter=dept_filter)


@cdacc_verifier_bp.route("/assessments/<assessment_id>/verify", methods=["POST"])
@login_required
@cdacc_verifier_required
def verify_assessment(assessment_id):
    db = get_service_client()
    user = current_user()
    new_status = request.form.get("status")
    feedback   = (request.form.get("feedback") or "").strip()
    if new_status not in ("approved", "rejected"):
        flash("Invalid status.", "warning")
        return redirect(url_for("cdacc_verifier.assessments"))
    try:
        update_data = {"status": new_status}
        if feedback:
            update_data["feedback"] = feedback
        db.table("assessments").update(update_data).eq("id", assessment_id).execute()
        write_audit_log(user["id"], "cdacc_verify_assessment",
                        f"Assessment {assessment_id} → {new_status}")
        flash(f"Assessment {new_status} successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("cdacc_verifier.assessments"))
