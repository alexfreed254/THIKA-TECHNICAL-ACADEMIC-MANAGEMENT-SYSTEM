"""
routes/liaison_officer.py — Industrial Liaison Officer blueprint.
Manages attachment placements, approves processes, monitors placement progress,
coordinates supervisors and attachment records.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from auth_utils import login_required, liaison_officer_required, current_user, write_audit_log
from db import get_service_client
from datetime import datetime

liaison_officer_bp = Blueprint("liaison_officer", __name__)


@liaison_officer_bp.route("/")
@liaison_officer_bp.route("/dashboard")
@login_required
@liaison_officer_required
def dashboard():
    db = get_service_client()
    user = current_user()
    stats = {}
    pending_attachments = []
    active_attachments = []
    recent_logbooks = []

    try:
        stats["total"]    = db.table("industrial_attachments").select("id", count="exact").execute().count or 0
        stats["pending"]  = db.table("industrial_attachments").select("id", count="exact").eq("status", "pending").execute().count or 0
        stats["active"]   = db.table("industrial_attachments").select("id", count="exact").eq("status", "active").execute().count or 0
        stats["approved"] = db.table("industrial_attachments").select("id", count="exact").eq("status", "approved").execute().count or 0
        stats["companies"]= db.table("companies").select("id", count="exact").execute().count or 0

        pending_attachments = (db.table("industrial_attachments")
            .select("*, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no, departments(name)), companies(name, address)")
            .eq("status", "pending")
            .order("created_at", desc=True)
            .limit(15)
            .execute().data or [])

        active_attachments = (db.table("industrial_attachments")
            .select("*, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no), companies(name, address)")
            .eq("status", "active")
            .order("start_date", desc=True)
            .limit(10)
            .execute().data or [])

        recent_logbooks = (db.table("digital_logbook")
            .select("*, user_profiles!digital_logbook_student_id_fkey(full_name, admission_no), units(name, code)")
            .order("log_date", desc=True)
            .limit(8)
            .execute().data or [])
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")

    return render_template("liaison_officer/dashboard.html",
                           stats=stats,
                           pending_attachments=pending_attachments,
                           active_attachments=active_attachments,
                           recent_logbooks=recent_logbooks,
                           current_month=datetime.now().strftime("%B %Y"))


@liaison_officer_bp.route("/attachments")
@login_required
@liaison_officer_required
def attachments():
    db = get_service_client()
    status_filter = request.args.get("status", "")
    query = (db.table("industrial_attachments")
               .select("*, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no, departments(name)), companies(name, address)")
               .order("created_at", desc=True)
               .limit(200))
    if status_filter:
        query = query.eq("status", status_filter)
    attachments = query.execute().data or []
    return render_template("liaison_officer/attachments.html",
                           attachments=attachments, status_filter=status_filter)


@liaison_officer_bp.route("/attachments/<att_id>/approve", methods=["POST"])
@login_required
@liaison_officer_required
def approve_attachment(att_id):
    db = get_service_client()
    user = current_user()
    new_status = request.form.get("status", "approved")
    if new_status not in ("approved", "active", "rejected", "completed"):
        flash("Invalid status.", "warning")
        return redirect(url_for("liaison_officer.attachments"))
    try:
        db.table("industrial_attachments").update({"status": new_status}).eq("id", att_id).execute()
        write_audit_log(user["id"], "update_attachment_status",
                        f"Attachment {att_id} set to {new_status}")
        flash(f"Attachment status updated to {new_status}.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("liaison_officer.attachments"))


@liaison_officer_bp.route("/companies")
@login_required
@liaison_officer_required
def companies():
    db = get_service_client()
    records = db.table("companies").select("*").order("name").execute().data or []
    return render_template("liaison_officer/companies.html", companies=records)


@liaison_officer_bp.route("/logbooks")
@login_required
@liaison_officer_required
def logbooks():
    db = get_service_client()
    records = (db.table("digital_logbook")
                 .select("*, user_profiles!digital_logbook_student_id_fkey(full_name, admission_no), units(name, code)")
                 .order("log_date", desc=True)
                 .limit(200)
                 .execute().data or [])
    return render_template("liaison_officer/logbooks.html", logbooks=records)
