"""
routes/liaison_officer.py — Industrial Liaison Officer blueprint.
Manages attachment placements, approves processes, monitors placement progress,
coordinates supervisors and attachment records.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, Response
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
    if new_status not in ("active", "rejected", "completed"):
        flash("Invalid status.", "warning")
        return redirect(url_for("liaison_officer.attachments"))
    try:
        current = (db.table("industrial_attachments")
                     .select("id, status, acceptance_letter_status")
                     .eq("id", att_id)
                     .limit(1)
                     .execute().data or [])
        if not current:
            flash("Attachment record was not found.", "warning")
            return redirect(url_for("liaison_officer.attachments"))

        record = current[0]
        if new_status == "active":
            if record.get("status") != "approved":
                flash("Only department-approved attachments can be activated.", "warning")
                return redirect(url_for("liaison_officer.attachments"))
            if (record.get("acceptance_letter_status") or "pending") != "approved":
                flash("The acceptance letter must be approved by the department before activation.", "warning")
                return redirect(url_for("liaison_officer.attachments"))

        db.table("industrial_attachments").update({"status": new_status}).eq("id", att_id).execute()
        write_audit_log("update_attachment_status",
                        target=f"Attachment {att_id} set to {new_status}")
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
    import os
    db = get_service_client()
    supabase_url  = os.environ.get("SUPABASE_URL", "").strip()
    status_filter = request.args.get("status", "")
    adm_filter    = request.args.get("admission_no", "").strip().upper()

    query = (db.table("digital_logbook")
               .select("id, student_id, log_date, entry_time, tasks_performed, "
                       "skills_applied, hours_worked, challenges_encountered, "
                       "achievements, mentor_approval_status, mentor_comments, "
                       "trainer_comments, evidence_urls, created_at, "
                       "student:user_profiles!digital_logbook_student_id_fkey"
                       "(full_name, admission_no), "
                       "attachment:industrial_attachments!digital_logbook_attachment_id_fkey"
                       "(companies(name))")
               .order("log_date", desc=True)
               .limit(500))

    if status_filter:
        query = query.eq("mentor_approval_status", status_filter)

    records = query.execute().data or []

    if adm_filter:
        records = [r for r in records
                   if adm_filter in (r.get("student") or {}).get("admission_no", "").upper()]

    for entry in records:
        ev_paths = entry.get("evidence_urls") or []
        entry["_evidence"] = [
            {
                "url":  f"{supabase_url}/storage/v1/object/public/assessment-evidence/{p}",
                "ext":  p.rsplit(".", 1)[-1].lower() if "." in p else "bin",
                "name": p.rsplit("/", 1)[-1],
            }
            for p in ev_paths if p
        ]

    return render_template("liaison_officer/logbooks.html",
                           logbooks=records, status_filter=status_filter,
                           adm_filter=adm_filter)


@liaison_officer_bp.route("/logbooks/<log_id>/review", methods=["POST"])
@login_required
@liaison_officer_required
def review_logbook(log_id):
    db  = get_service_client()
    user = current_user()
    action  = request.form.get("action", "")
    comment = (request.form.get("comment") or "").strip()

    if action not in ("approve", "reject"):
        flash("Invalid action.", "error")
        return redirect(url_for("liaison_officer.logbooks"))

    new_status = "approved" if action == "approve" else "rejected"
    payload = {
        "mentor_approval_status": new_status,
        "mentor_approved_by":     user["id"],
        "mentor_approved_at":     datetime.utcnow().isoformat(),
    }
    if comment:
        payload["mentor_comments"] = comment

    try:
        db.table("digital_logbook").update(payload).eq("id", log_id).execute()
        write_audit_log(f"{action}_logbook", target=f"Log {log_id}")
        flash(f"Log entry {new_status}.", "success")
    except Exception as exc:
        flash(f"Error: {exc}", "error")

    return redirect(url_for("liaison_officer.logbooks",
                            status=request.form.get("status_filter", "")))


# ── Attachment Export ──────────────────────────────────────────────────────────

def _get_period_range(year: int, period: str):
    ranges = {
        "1": (f"{year}-01-01", f"{year}-04-30"),
        "2": (f"{year}-05-01", f"{year}-08-31"),
        "3": (f"{year}-09-01", f"{year}-12-31"),
    }
    return ranges.get(period, (f"{year}-01-01", f"{year}-12-31"))


def _period_label(period: str) -> str:
    return {"1": "January–April", "2": "May–August", "3": "September–December"}.get(period, "Full Year")


@liaison_officer_bp.route("/attachments/export")
@login_required
@liaison_officer_required
def export_attachments():
    import io
    from datetime import date
    db = get_service_client()
    fmt    = request.args.get("format", "excel")
    period = request.args.get("period", "")
    year   = int(request.args.get("year", date.today().year))

    start_date, end_date = _get_period_range(year, period)
    rows_raw = (db.table("industrial_attachments")
                  .select("id, student_id, start_date, end_date, status, "
                          "student:user_profiles!industrial_attachments_student_id_fkey"
                          "(full_name, admission_no, mobile_number), "
                          "companies(name, address, contact_person, contact_phone)")
                  .gte("start_date", start_date)
                  .lte("start_date", end_date)
                  .order("student_id")
                  .execute().data or [])

    rows = []
    for r in rows_raw:
        st = r.get("student") or {}
        co = r.get("companies") or {}
        rows.append({
            "Admission No":       st.get("admission_no", ""),
            "Full Name":          st.get("full_name", ""),
            "Trainee Phone":      st.get("mobile_number", ""),
            "Company Attached":   co.get("name", ""),
            "Location / Address": co.get("address", ""),
            "Supervisor Name":    co.get("contact_person", ""),
            "Supervisor Phone":   co.get("contact_phone", ""),
            "Start Date":         r.get("start_date", ""),
            "End Date":           r.get("end_date", ""),
            "Status":             (r.get("status") or "").title(),
        })

    label = _period_label(period)
    title = "Industrial Attachments — All Departments"

    if fmt == "pdf":
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=landscape(A4),
                                leftMargin=15*mm, rightMargin=15*mm,
                                topMargin=15*mm, bottomMargin=15*mm)
        styles = getSampleStyleSheet()
        navy = colors.HexColor("#1565C0")
        title_style = ParagraphStyle("t", parent=styles["Heading1"], textColor=navy, fontSize=14, spaceAfter=4)
        sub_style   = ParagraphStyle("s", parent=styles["Normal"], textColor=colors.grey, fontSize=9, spaceAfter=10)

        col_headers = ["Adm No", "Full Name", "Phone", "Company", "Address", "Supervisor", "Sup. Phone", "Start", "End", "Status"]
        keys = ["Admission No", "Full Name", "Trainee Phone", "Company Attached",
                "Location / Address", "Supervisor Name", "Supervisor Phone", "Start Date", "End Date", "Status"]
        data = [col_headers] + [[r.get(k, "") for k in keys] for r in rows]
        col_widths_pt = [w * mm for w in [22, 48, 26, 48, 52, 40, 26, 20, 20, 18]]
        tbl = Table(data, colWidths=col_widths_pt, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0), navy),
            ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
            ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",     (0, 0), (-1, 0), 8),
            ("FONTSIZE",     (0, 1), (-1, -1), 7.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EFF6FF")]),
            ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#D1D5DB")),
            ("ALIGN",        (0, 0), (-1, -1), "LEFT"),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",   (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ]))
        story = [Paragraph(title, title_style),
                 Paragraph(f"Period: {label} {year}  |  Total: {len(rows)}", sub_style),
                 Spacer(1, 4), tbl]
        doc.build(story)
        buf.seek(0)
        fname = f"attachments_{label.replace('–','-')}_{year}.pdf"
        return Response(buf.read(), mimetype="application/pdf",
                        headers={"Content-Disposition": f"attachment; filename={fname}"})

    # Excel
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    ws = wb.active
    ws.title = "Attachments"
    hdr_fill = PatternFill("solid", fgColor="1565C0")
    hdr_font = Font(color="FFFFFF", bold=True, size=11)
    thin = Side(style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.merge_cells("A1:J1")
    ws["A1"] = f"{title} — {label} {year}"
    ws["A1"].font = Font(bold=True, size=13, color="0D2167")
    ws["A1"].alignment = Alignment(horizontal="center")

    headers = ["Admission No", "Full Name", "Trainee Phone", "Company Attached",
               "Location / Address", "Supervisor Name", "Supervisor Phone",
               "Start Date", "End Date", "Status"]
    ws.append([])
    ws.append(headers)
    hdr_row = ws.max_row
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=hdr_row, column=col_idx)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = border

    for row in rows:
        ws.append([row.get(h, "") for h in headers])
        for col_idx in range(1, len(headers) + 1):
            ws.cell(row=ws.max_row, column=col_idx).border = border

    for i, w in enumerate([16, 28, 18, 28, 32, 24, 18, 14, 14, 12], 1):
        ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"attachments_{label.replace('–','-')}_{year}.xlsx"
    return Response(buf.read(),
                    mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename={fname}"})
