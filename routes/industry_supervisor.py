"""
routes/industry_supervisor.py — Industry Supervisor blueprint.
Monitor attached trainees, fill trainee evaluations,
approve digital logbooks, submit attachment performance reports.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for
from auth_utils import login_required, industry_supervisor_required, current_user, write_audit_log
from db import get_service_client
from datetime import datetime

industry_supervisor_bp = Blueprint("industry_supervisor", __name__)


def _get_supervisor_company(db, user_id):
    """Return the company linked to this supervisor (via companies.created_by or mentors table)."""
    try:
        res = db.table("mentors").select("company_id, companies(name, id)").eq("user_id", user_id).limit(1).execute()
        if res.data:
            return res.data[0]
    except Exception:
        pass
    return None


@industry_supervisor_bp.route("/")
@industry_supervisor_bp.route("/dashboard")
@login_required
@industry_supervisor_required
def dashboard():
    db = get_service_client()
    user = current_user()
    mentor = _get_supervisor_company(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    stats = {}
    trainees = []
    pending_logbooks = []

    try:
        if company_id:
            stats["trainees"]  = db.table("industrial_attachments").select("id", count="exact").eq("company_id", company_id).eq("status", "active").execute().count or 0
            stats["logbooks"]  = db.table("digital_logbook").select("id", count="exact").execute().count or 0
            stats["pending_logs"] = db.table("digital_logbook").select("id", count="exact").eq("mentor_approval_status", "pending").execute().count or 0

            trainees = (db.table("industrial_attachments")
                .select("*, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no, departments(name))")
                .eq("company_id", company_id)
                .eq("status", "active")
                .execute().data or [])

            pending_logbooks = (db.table("digital_logbook")
                .select("*, user_profiles!digital_logbook_student_id_fkey(full_name, admission_no), units(name, code)")
                .eq("mentor_approval_status", "pending")
                .order("log_date", desc=True)
                .limit(15)
                .execute().data or [])
        else:
            stats = {"trainees": 0, "logbooks": 0, "pending_logs": 0}
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")

    return render_template("industry_supervisor/dashboard.html",
                           stats=stats,
                           trainees=trainees,
                           pending_logbooks=pending_logbooks,
                           mentor=mentor,
                           current_month=datetime.now().strftime("%B %Y"))


@industry_supervisor_bp.route("/trainees")
@login_required
@industry_supervisor_required
def trainees():
    db = get_service_client()
    user = current_user()
    mentor = _get_supervisor_company(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    records = []
    if company_id:
        records = (db.table("industrial_attachments")
            .select("*, user_profiles!industrial_attachments_student_id_fkey(full_name, admission_no, departments(name), mobile_number)")
            .eq("company_id", company_id)
            .order("start_date", desc=True)
            .execute().data or [])
    return render_template("industry_supervisor/trainees.html", trainees=records)


@industry_supervisor_bp.route("/logbooks")
@login_required
@industry_supervisor_required
def logbooks():
    db = get_service_client()
    status_filter = request.args.get("status", "")
    query = (db.table("digital_logbook")
               .select("*, user_profiles!digital_logbook_student_id_fkey(full_name, admission_no), units(name, code)")
               .order("log_date", desc=True)
               .limit(200))
    if status_filter:
        query = query.eq("mentor_approval_status", status_filter)
    records = query.execute().data or []
    return render_template("industry_supervisor/logbooks.html",
                           logbooks=records, status_filter=status_filter)


@industry_supervisor_bp.route("/logbooks/<log_id>/approve", methods=["POST"])
@login_required
@industry_supervisor_required
def approve_logbook(log_id):
    db = get_service_client()
    user = current_user()
    new_status = request.form.get("status", "approved")
    feedback   = (request.form.get("feedback") or "").strip()
    if new_status not in ("approved", "rejected"):
        flash("Invalid status.", "warning")
        return redirect(url_for("industry_supervisor.logbooks"))
    try:
        update_data = {"mentor_approval_status": new_status}
        if feedback:
            update_data["mentor_feedback"] = feedback
        db.table("digital_logbook").update(update_data).eq("id", log_id).execute()
        write_audit_log(user["id"], "approve_logbook", f"Logbook {log_id} → {new_status}")
        flash(f"Logbook entry {new_status}.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("industry_supervisor.logbooks"))
