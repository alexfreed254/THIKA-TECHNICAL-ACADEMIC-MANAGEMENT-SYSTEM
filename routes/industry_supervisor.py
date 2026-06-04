"""
routes/industry_supervisor.py — Industry Supervisor blueprint.
Review trainee digital logbooks (weekly), mark attendance, evaluate trainees.
"""

import os
from collections import defaultdict
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from auth_utils import login_required, industry_supervisor_required, current_user, write_audit_log
from db import get_service_client

industry_supervisor_bp = Blueprint("industry_supervisor", __name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()


def _get_mentor(db, user_id):
    """Return mentor row (with company) for this supervisor."""
    try:
        res = (db.table("mentors")
                 .select("*, companies(name, id, address, contact_phone)")
                 .eq("user_id", user_id)
                 .limit(1)
                 .execute())
        return res.data[0] if res.data else None
    except Exception:
        return None


def _week_label(monday_str: str) -> str:
    try:
        ws = datetime.strptime(monday_str, "%Y-%m-%d")
        we = ws + timedelta(days=6)
        return f"{ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}"
    except Exception:
        return monday_str


# ── Dashboard ─────────────────────────────────────────────────────────────────

@industry_supervisor_bp.route("/")
@industry_supervisor_bp.route("/dashboard")
@login_required
@industry_supervisor_required
def dashboard():
    db   = get_service_client()
    user = current_user()
    mentor     = _get_mentor(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    stats = {"trainees": 0, "pending_logs": 0, "approved_logs": 0, "total_logs": 0}
    trainees  = []
    pending   = []

    if company_id:
        try:
            trainees = (db.table("industrial_attachments")
                .select("*, student:user_profiles!industrial_attachments_student_id_fkey"
                        "(full_name, admission_no, mobile_number, departments(name))")
                .eq("company_id", company_id)
                .in_("status", ["active", "approved"])
                .order("start_date", desc=True)
                .execute().data or [])

            stats["trainees"] = len(trainees)

            if trainees:
                sids = [t["student_id"] for t in trainees if t.get("student_id")]
                if sids:
                    logs = (db.table("digital_logbook")
                              .select("id, mentor_approval_status")
                              .in_("student_id", sids)
                              .execute().data or [])
                    stats["total_logs"]    = len(logs)
                    stats["pending_logs"]  = sum(1 for l in logs if l.get("mentor_approval_status") == "pending")
                    stats["approved_logs"] = sum(1 for l in logs if l.get("mentor_approval_status") == "approved")

                    pending = (db.table("digital_logbook")
                                 .select("id, student_id, log_date, entry_time, tasks_performed, "
                                         "mentor_approval_status, "
                                         "student:user_profiles!digital_logbook_student_id_fkey"
                                         "(full_name, admission_no)")
                                 .in_("student_id", sids)
                                 .eq("mentor_approval_status", "pending")
                                 .order("log_date", desc=True)
                                 .limit(10)
                                 .execute().data or [])
        except Exception as e:
            flash(f"Error loading dashboard: {e}", "danger")

    return render_template("industry_supervisor/dashboard.html",
                           stats=stats, trainees=trainees,
                           pending_logbooks=pending, mentor=mentor,
                           current_month=datetime.now().strftime("%B %Y"))


# ── My Trainees ───────────────────────────────────────────────────────────────

@industry_supervisor_bp.route("/trainees")
@login_required
@industry_supervisor_required
def trainees():
    db         = get_service_client()
    user       = current_user()
    mentor     = _get_mentor(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    records = []
    if company_id:
        try:
            records = (db.table("industrial_attachments")
                .select("*, student:user_profiles!industrial_attachments_student_id_fkey"
                        "(full_name, admission_no, mobile_number, departments(name))")
                .eq("company_id", company_id)
                .order("start_date", desc=True)
                .execute().data or [])
        except Exception as e:
            flash(f"Error loading trainees: {e}", "danger")

    return render_template("industry_supervisor/trainees.html",
                           trainees=records, mentor=mentor)


# ── Logbooks (search + weekly review) ────────────────────────────────────────

@industry_supervisor_bp.route("/logbooks")
@login_required
@industry_supervisor_required
def logbooks():
    db   = get_service_client()
    user = current_user()
    mentor     = _get_mentor(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    search     = request.args.get("q", "").strip()
    status_f   = request.args.get("status", "")

    entries = []
    if company_id:
        try:
            trainees = (db.table("industrial_attachments")
                          .select("student_id")
                          .eq("company_id", company_id)
                          .in_("status", ["active", "approved"])
                          .execute().data or [])
            sids = [t["student_id"] for t in trainees if t.get("student_id")]

            if sids:
                q = (db.table("digital_logbook")
                       .select("id, student_id, log_date, entry_time, tasks_performed, "
                               "skills_applied, hours_worked, challenges_encountered, "
                               "achievements, mentor_approval_status, mentor_comments, "
                               "evidence_urls, created_at, "
                               "student:user_profiles!digital_logbook_student_id_fkey"
                               "(full_name, admission_no)")
                       .in_("student_id", sids)
                       .order("log_date", desc=True)
                       .limit(500))
                if status_f:
                    q = q.eq("mentor_approval_status", status_f)
                entries = q.execute().data or []

                # Search filter
                if search:
                    sl = search.lower()
                    entries = [e for e in entries if
                               sl in (e.get("student") or {}).get("full_name", "").lower() or
                               sl in (e.get("student") or {}).get("admission_no", "").lower()]

                # Build evidence URLs
                for e in entries:
                    paths = e.get("evidence_urls") or []
                    e["_evidence"] = [
                        {"url": f"{SUPABASE_URL}/storage/v1/object/public/assessment-evidence/{p}",
                         "ext": p.rsplit(".", 1)[-1].lower() if "." in p else "bin",
                         "name": p.rsplit("/", 1)[-1]}
                        for p in paths if p
                    ]

        except Exception as ex:
            flash(f"Error loading logbooks: {ex}", "danger")

    # Group by (student, week)
    weeks_map = {}  # key: (student_id, week_start)
    for e in entries:
        try:
            d = datetime.strptime(e["log_date"], "%Y-%m-%d")
        except Exception:
            d = datetime.now()
        monday = (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")
        key = (e.get("student_id"), monday)
        if key not in weeks_map:
            weeks_map[key] = {
                "student":     e.get("student") or {},
                "week_start":  monday,
                "week_label":  _week_label(monday),
                "entries":     [],
            }
        weeks_map[key]["entries"].append(e)

    # Compute week-level status
    weeks = []
    for wk in sorted(weeks_map.values(), key=lambda x: x["week_start"], reverse=True):
        statuses = [en.get("mentor_approval_status", "pending") for en in wk["entries"]]
        if all(s == "approved" for s in statuses):
            wk["week_status"] = "approved"
        elif any(s == "rejected" for s in statuses):
            wk["week_status"] = "rejected"
        elif any(s == "approved" for s in statuses):
            wk["week_status"] = "partial"
        else:
            wk["week_status"] = "pending"
        weeks.append(wk)

    return render_template("industry_supervisor/logbooks.html",
                           weeks=weeks,
                           total_entries=len(entries),
                           search=search,
                           status_filter=status_f,
                           mentor=mentor)


@industry_supervisor_bp.route("/logbooks/<log_id>/review", methods=["POST"])
@login_required
@industry_supervisor_required
def review_logbook(log_id):
    db      = get_service_client()
    user    = current_user()
    status  = request.form.get("status", "approved")
    comment = (request.form.get("comment") or "").strip()

    if status not in ("approved", "rejected"):
        flash("Invalid status.", "warning")
        return redirect(url_for("industry_supervisor.logbooks"))
    try:
        update = {"mentor_approval_status": status}
        if comment:
            update["mentor_comments"] = comment
        db.table("digital_logbook").update(update).eq("id", log_id).execute()
        write_audit_log(user["id"], "review_logbook", f"Logbook {log_id} → {status}")
        flash(f"Entry {status}.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(request.referrer or url_for("industry_supervisor.logbooks"))


# ── Attendance ────────────────────────────────────────────────────────────────

@industry_supervisor_bp.route("/attendance")
@login_required
@industry_supervisor_required
def attendance():
    db   = get_service_client()
    user = current_user()
    mentor     = _get_mentor(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    trainees   = []
    records    = []
    adm_filter = request.args.get("q", "").strip().lower()

    if company_id:
        try:
            trainees = (db.table("industrial_attachments")
                .select("id, student_id, start_date, end_date, "
                        "student:user_profiles!industrial_attachments_student_id_fkey"
                        "(full_name, admission_no, mobile_number)")
                .eq("company_id", company_id)
                .in_("status", ["active", "approved"])
                .execute().data or [])

            if adm_filter:
                trainees = [t for t in trainees if
                            adm_filter in (t.get("student") or {}).get("admission_no", "").lower() or
                            adm_filter in (t.get("student") or {}).get("full_name", "").lower()]

            a_ids = [t["id"] for t in trainees if t.get("id")]
            if a_ids:
                records = (db.table("supervisor_attendance")
                             .select("*")
                             .in_("attachment_id", a_ids)
                             .order("date", desc=True)
                             .execute().data or [])
        except Exception as e:
            # Table might not exist yet
            print(f"[supervisor.attendance] {e}")

    # Build attendance map: attachment_id → {date: status}
    att_map = defaultdict(dict)
    for r in records:
        att_map[r.get("attachment_id")][r.get("date")] = r.get("status", "present")

    today = datetime.now().strftime("%Y-%m-%d")
    return render_template("industry_supervisor/attendance.html",
                           trainees=trainees,
                           att_map=dict(att_map),
                           today=today,
                           search=adm_filter,
                           mentor=mentor)


@industry_supervisor_bp.route("/attendance/mark", methods=["POST"])
@login_required
@industry_supervisor_required
def mark_attendance():
    db          = get_service_client()
    user        = current_user()
    attachment_id = request.form.get("attachment_id")
    date          = request.form.get("date")
    status        = request.form.get("status", "present")
    notes         = (request.form.get("notes") or "").strip()

    if not attachment_id or not date:
        flash("Attachment and date are required.", "warning")
        return redirect(url_for("industry_supervisor.attendance"))

    if status not in ("present", "absent", "half-day", "late"):
        status = "present"

    try:
        # Upsert attendance record
        existing = (db.table("supervisor_attendance")
                      .select("id")
                      .eq("attachment_id", attachment_id)
                      .eq("date", date)
                      .limit(1)
                      .execute().data or [])
        payload = {
            "attachment_id":  attachment_id,
            "supervisor_id":  user["id"],
            "date":           date,
            "status":         status,
            "notes":          notes,
        }
        if existing:
            db.table("supervisor_attendance").update({"status": status, "notes": notes}).eq("id", existing[0]["id"]).execute()
        else:
            db.table("supervisor_attendance").insert(payload).execute()

        write_audit_log(user["id"], "mark_attendance", f"att:{attachment_id} {date}={status}")
        flash(f"Attendance marked: {status.title()} for {date}.", "success")
    except Exception as e:
        flash(f"Error marking attendance: {e}. Ensure the supervisor_attendance table exists.", "danger")

    return redirect(url_for("industry_supervisor.attendance"))


# ── Trainee Evaluation ────────────────────────────────────────────────────────

@industry_supervisor_bp.route("/evaluate")
@login_required
@industry_supervisor_required
def evaluate():
    db   = get_service_client()
    user = current_user()
    mentor     = _get_mentor(db, user["id"])
    company_id = mentor["company_id"] if mentor else None

    trainees   = []
    adm_filter = request.args.get("q", "").strip().lower()

    if company_id:
        try:
            trainees = (db.table("industrial_attachments")
                .select("id, student_id, start_date, end_date, status, final_grade, "
                        "supervisor_score, supervisor_notes, supervisor_evaluated_at, "
                        "student:user_profiles!industrial_attachments_student_id_fkey"
                        "(full_name, admission_no, departments(name), mobile_number)")
                .eq("company_id", company_id)
                .order("start_date", desc=True)
                .execute().data or [])

            if adm_filter:
                trainees = [t for t in trainees if
                            adm_filter in (t.get("student") or {}).get("admission_no", "").lower() or
                            adm_filter in (t.get("student") or {}).get("full_name", "").lower()]
        except Exception as e:
            flash(f"Error loading trainees: {e}", "danger")

    return render_template("industry_supervisor/evaluate.html",
                           trainees=trainees,
                           search=adm_filter,
                           mentor=mentor)


@industry_supervisor_bp.route("/evaluate/<attachment_id>", methods=["POST"])
@login_required
@industry_supervisor_required
def submit_evaluation(attachment_id):
    db   = get_service_client()
    user = current_user()

    score_raw = (request.form.get("score") or "").strip()
    notes     = (request.form.get("notes") or "").strip()

    try:
        score = int(score_raw)
        if not 0 <= score <= 100:
            raise ValueError("Score must be 0–100")
    except ValueError as ve:
        flash(f"Invalid score: {ve}", "warning")
        return redirect(url_for("industry_supervisor.evaluate"))

    # Grade mapping (same as formative system)
    if score >= 80:   grade = "4 — Mastery"
    elif score >= 65: grade = "3 — Proficiency"
    elif score >= 50: grade = "2 — Competent"
    else:             grade = "1 — Not Yet Competent"

    try:
        db.table("industrial_attachments").update({
            "final_grade":           grade,
            "supervisor_score":      score,
            "supervisor_notes":      notes,
            "supervisor_evaluated_at": datetime.now().isoformat(),
        }).eq("id", attachment_id).execute()

        write_audit_log(user["id"], "evaluate_trainee",
                        f"att:{attachment_id} score={score}/100 grade={grade}")
        flash(f"Evaluation saved: {score}/100 — {grade}.", "success")
    except Exception as e:
        flash(f"Error saving evaluation: {e}", "danger")

    return redirect(url_for("industry_supervisor.evaluate"))
