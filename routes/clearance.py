"""
Clearance Blueprint — Sequential 8-Stage Institutional Clearance System

Flow:
  1  Trainer Clearance      (ALL trainers who taught student)
  2  Home Dept Technicians  (ALL technicians in dept)
  3  Home Dept HOD          (dept_admin of home department)
  4  Other Academic Depts   (dept_admin of other clearance depts)
  5  Institutional Sections (Library, Sports, Environment, DoS office)
  6  Finance Office
  7  Dean of Students / Deputy Principal (final authority)
  ✓  Clearance Issued       (download enabled, QR-verified certificate)
"""

import uuid as _uuid
from datetime import datetime
from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, abort, jsonify)
from auth_utils import login_required, student_required, current_user, write_audit_log
from db import get_service_client
from notifications import create_notification

clearance_bp = Blueprint("clearance", __name__)


# ── Global stage-order mapping ────────────────────────────────────────────────
# Each clearance_approval belongs to one sequential group (1–7).
# Approval of group N is blocked until ALL approvals in groups < N are done.

def _global_group(stage: dict) -> int:
    """Return 1–7 sequential group for a clearance_stage dict."""
    role  = (stage.get("approver_role") or "").lower()
    name  = (stage.get("stage_name")    or "").lower()
    dept  = stage.get("clearance_departments") or {}
    ctype = (dept.get("clearance_type") or "").lower()

    if role == "trainer" and "technician" not in name:
        return 1  # Trainer Clearance
    if "technician" in name or role == "workshop_technician":
        return 2  # Home Dept Technicians
    if role == "dept_admin" and ctype == "department":
        return 3  # HOD (home or other depts — gated by HOD completing first)
    if ctype == "institutional":
        return 4  # Library / Sports / Environment / DoS
    if role in ("finance_officer", "finance"):
        return 5  # Finance
    if role in ("dean_students", "dean_of_students", "deputy_principal",
                "registrar", "academic_registrar"):
        return 6  # Final authority
    return 4  # Default to institutional

GROUP_LABELS = {
    1: "Trainer Clearance",
    2: "Technician Clearance",
    3: "HOD Approval",
    4: "Institutional Sections",
    5: "Finance",
    6: "Final Authority (Dean / Registrar)",
}

def _serial(request_id: str) -> str:
    year = datetime.now().year
    return f"CLR/{year}/{str(request_id).replace('-','')[:6].upper()}"


def _fetch_all_approvals(db, request_id: str) -> list:
    """Return all approval rows for a request with stage info attached."""
    return (db.table("clearance_approvals")
              .select("*, clearance_stages(stage_name, approver_role, "
                      "  clearance_departments(name, clearance_type))")
              .eq("clearance_request_id", request_id)
              .execute().data or [])


def _groups_complete_before(approvals: list, target_group: int) -> bool:
    """Return True if every approval with group < target_group is 'approved'."""
    for a in approvals:
        stage = a.get("clearance_stages") or {}
        g = _global_group(stage)
        if g < target_group and a.get("status") != "approved":
            return False
    return True


# ── Student: clearance dashboard ─────────────────────────────────────────────

@clearance_bp.route("/")
@login_required
@student_required
def dashboard():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    req_rows = (db.table("clearance_requests")
                .select("*, courses(name, code), departments(name)")
                .eq("student_id", student_id)
                .order("initiated_at", desc=True)
                .limit(1)
                .execute().data or [])

    enrollments = (db.table("enrollments")
                   .select("*, classes(course_id, courses(name, code))")
                   .eq("student_id", student_id)
                   .execute().data or [])

    if not req_rows:
        return render_template("clearance/student_dashboard.html",
                               clearance_request=None,
                               has_request=False,
                               enrollments=enrollments,
                               steps=[])

    cr = req_rows[0]
    serial = cr.get("serial_number") or _serial(cr["id"])

    approvals = _fetch_all_approvals(db, cr["id"])

    # Build per-group summary for the progress steps (groups 1–4 only).
    # Groups 5 (Finance) and 6 (Dean/Registrar) are signed manually on the form.
    groups = {i: {"label": GROUP_LABELS[i], "approvals": [], "status": "locked"}
              for i in range(1, 5)}

    for a in approvals:
        stage = a.get("clearance_stages") or {}
        g = _global_group(stage)
        if g in groups:
            groups[g]["approvals"].append(a)

    # Determine each group's display status
    for g, info in groups.items():
        app_list = info["approvals"]
        if not app_list:
            # No approvals for this group → skip / not applicable
            info["status"] = "n_a"
            continue
        statuses = [a.get("status", "pending") for a in app_list]
        if all(s == "approved" for s in statuses):
            info["status"] = "approved"
        elif any(s == "rejected" for s in statuses):
            info["status"] = "rejected"
        else:
            # Check if previous groups are done (unlocked for action)
            prev_done = all(
                groups[pg]["status"] in ("approved", "n_a")
                for pg in range(1, g)
            )
            info["status"] = "in_progress" if prev_done else "locked"

    steps = list(groups.values())

    return render_template("clearance/student_dashboard.html",
                           clearance_request=cr,
                           has_request=True,
                           serial=serial,
                           steps=steps,
                           approvals=approvals,
                           enrollments=enrollments)


# ── Student: initiate clearance ───────────────────────────────────────────────

@clearance_bp.route("/initiate", methods=["POST"])
@login_required
@student_required
def initiate_clearance():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    course_id  = request.form.get("course_id", "").strip()

    if not course_id:
        flash("Please select your course.", "error")
        return redirect(url_for("clearance.dashboard"))

    try:
        course = (db.table("courses")
                  .select("*, departments(id, name)")
                  .eq("id", course_id)
                  .single()
                  .execute().data)
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("clearance.dashboard"))

        if (db.table("clearance_requests")
              .select("id")
              .eq("student_id", student_id)
              .in_("status", ["pending", "in_progress"])
              .execute().data):
            flash("You already have an active clearance request.", "warning")
            return redirect(url_for("clearance.dashboard"))

        dept_id = course["departments"]["id"]

        # Create clearance request
        result = db.table("clearance_requests").insert({
            "student_id": student_id,
            "course_id":  course_id,
            "department_id": dept_id,
            "status":     "in_progress",
            "created_by": user["id"],
        }).execute()
        request_id = result.data[0]["id"]
        serial     = _serial(request_id)

        # Save serial_number (may fail if column not added yet — non-fatal)
        try:
            db.table("clearance_requests").update({"serial_number": serial}).eq("id", request_id).execute()
        except Exception:
            pass

        # ── Identify approvers for multi-approver stages ──────────────────
        # Trainers who taught this student
        att = (db.table("attendance")
               .select("trainer_id")
               .eq("student_id", student_id)
               .execute().data or [])
        trainer_ids = list({r["trainer_id"] for r in att if r.get("trainer_id")})

        # Technicians in home department
        tech_rows = (db.table("user_profiles")
                     .select("id")
                     .eq("role", "workshop_technician")
                     .eq("department_id", dept_id)
                     .eq("is_active", True)
                     .execute().data or [])
        tech_ids = [t["id"] for t in tech_rows]

        # Home dept HOD(s)
        hod_rows = (db.table("user_profiles")
                    .select("id")
                    .eq("role", "dept_admin")
                    .eq("department_id", dept_id)
                    .execute().data or [])
        hod_ids = [h["id"] for h in hod_rows]

        # ── Fetch all clearance stages ────────────────────────────────────
        stages = (db.table("clearance_stages")
                  .select("*, clearance_departments(name, clearance_type, code)")
                  .order("stage_order")
                  .execute().data or [])

        # ── Create approval records (digital groups 1–4 only) ────────────
        # Groups 5 (Finance) and 6 (Dean/Registrar) are handled manually
        # on the physical clearance form — no digital approval records created.
        for stage in stages:
            s_name = (stage.get("stage_name") or "").lower()
            s_role = (stage.get("approver_role") or "").lower()
            cd     = stage.get("clearance_departments") or {}
            ctype  = (cd.get("clearance_type") or "").lower()

            # Build a temporary stage dict to check its group
            _tmp_stage = {"approver_role": s_role, "stage_name": s_name,
                          "clearance_departments": cd}
            if _global_group(_tmp_stage) >= 5:
                continue   # skip Finance and Final Authority — done manually

            def _insert(approver_id=None, extra_comment=""):
                db.table("clearance_approvals").insert({
                    "clearance_request_id": request_id,
                    "clearance_stage_id":   stage["id"],
                    "approver_id":          approver_id,
                    "status":               "pending",
                    "comments":             extra_comment or None,
                }).execute()

            if s_role == "trainer" and "technician" not in s_name and ctype == "department":
                if trainer_ids:
                    for tid in trainer_ids:
                        _insert(approver_id=tid)
                else:
                    _insert()
            elif "technician" in s_name and ctype == "department":
                if tech_ids:
                    for tid in tech_ids:
                        _insert(approver_id=tid)
                else:
                    _insert()
            elif s_role == "dept_admin" and ctype == "department":
                if hod_ids:
                    for hid in hod_ids:
                        _insert(approver_id=hid)
                else:
                    _insert()
            else:
                _insert()

        # Notify trainers
        try:
            sp = db.table("user_profiles").select("full_name").eq("id", student_id).single().execute().data
            sname = sp["full_name"] if sp else "A student"
            for tid in trainer_ids:
                create_notification(
                    user_id=tid,
                    title="Clearance Approval Required",
                    message=f"{sname} has initiated clearance and requires your sign-off.",
                    notification_type="info",
                    action_url="/clearance/approver",
                )
        except Exception:
            pass

        write_audit_log("initiate_clearance", target=f"request:{request_id}")
        flash(f"Clearance initiated successfully. Your serial number is {serial}.", "success")
    except Exception as e:
        flash(f"Error initiating clearance: {e}", "error")

    return redirect(url_for("clearance.dashboard"))


# ── Approver dashboard ────────────────────────────────────────────────────────

@clearance_bp.route("/approver")
@login_required
def approver_dashboard():
    db = get_service_client()
    user = current_user()
    role = user["role"]

    # Fetch pending approvals accessible to this user
    if role in ("trainer", "workshop_technician"):
        # Pre-assigned by approver_id
        raw = (db.table("clearance_approvals")
               .select("*, "
                       "clearance_requests(id, student_id, status, department_id, "
                       "  user_profiles:user_profiles!clearance_requests_student_id_fkey"
                       "  (full_name, admission_no)), "
                       "clearance_stages(stage_name, approver_role, stage_order, "
                       "  clearance_departments(name, clearance_type))")
               .eq("approver_id", user["id"])
               .eq("status", "pending")
               .execute().data or [])
    else:
        # Role-based: fetch all pending and filter
        raw = (db.table("clearance_approvals")
               .select("*, "
                       "clearance_requests(id, student_id, status, department_id, "
                       "  user_profiles:user_profiles!clearance_requests_student_id_fkey"
                       "  (full_name, admission_no)), "
                       "clearance_stages(stage_name, approver_role, stage_order, "
                       "  clearance_departments(name, clearance_type))")
               .eq("status", "pending")
               .execute().data or [])
        raw = [a for a in raw
               if (a.get("clearance_stages") or {}).get("approver_role") == role]

    # Flatten and annotate with is_active (sequential gate check)
    my_approvals = []
    req_cache: dict = {}  # request_id → all_approvals

    for a in raw:
        req  = a.get("clearance_requests") or {}
        req_id = req.get("id", "")
        if req_id not in req_cache:
            req_cache[req_id] = _fetch_all_approvals(db, req_id)
        all_app = req_cache[req_id]

        stage = a.get("clearance_stages") or {}
        group = _global_group(stage)
        a["_group"]     = group
        a["_is_active"] = _groups_complete_before(all_app, group)
        a["user_profiles"]    = req.get("user_profiles") or {}
        my_approvals.append(a)

    # Trainer-specific: redirect to trainer template
    if role == "trainer":
        att_rows = (db.table("attendance")
                    .select("student_id, unit_id, units(name, code)")
                    .eq("trainer_id", user["id"])
                    .execute().data or [])
        taught = {}
        for r in att_rows:
            sid = r["student_id"]
            u   = r.get("units") or {}
            if sid not in taught:
                taught[sid] = []
            if u.get("code"):
                taught[sid].append(u)
        for a in my_approvals:
            sid = (a.get("clearance_requests") or {}).get("student_id", "")
            a["taught_units"] = taught.get(sid, [])
        return render_template("trainer/clearance_approvals.html",
                               my_approvals=my_approvals,
                               stats={"total": len(my_approvals), "taught": len(taught)})

    return render_template("clearance/approver_dashboard.html",
                           my_approvals=my_approvals,
                           user_role=role)


# ── Approve a clearance stage ─────────────────────────────────────────────────

@clearance_bp.route("/approve/<approval_id>", methods=["POST"])
@login_required
def approve_clearance(approval_id):
    db = get_service_client()
    user = current_user()
    role = user["role"]
    comments = request.form.get("comments", "").strip()

    try:
        approval = (db.table("clearance_approvals")
                    .select("*, clearance_stages(stage_name, approver_role, "
                            "  clearance_departments(clearance_type)), "
                            "clearance_requests(id, student_id, status)")
                    .eq("id", approval_id)
                    .single()
                    .execute().data)

        if not approval:
            flash("Approval record not found.", "error")
            return redirect(url_for("clearance.approver_dashboard"))

        stage = approval.get("clearance_stages") or {}
        req   = approval.get("clearance_requests") or {}

        # Security: verify this user is allowed to approve
        expected_role = stage.get("approver_role")
        if expected_role != role:
            # Also allow if pre-assigned by approver_id
            if approval.get("approver_id") != user["id"]:
                abort(403)

        # Sequential gate: check all previous groups are approved
        all_app = _fetch_all_approvals(db, req["id"])
        group   = _global_group(stage)
        if not _groups_complete_before(all_app, group):
            flash("Previous clearance stages must be fully approved before you can act on this stage.",
                  "warning")
            return redirect(url_for("clearance.approver_dashboard"))

        # Mark this approval as approved
        db.table("clearance_approvals").update({
            "status":      "approved",
            "approver_id": user["id"],
            "comments":    comments or None,
            "approved_at": datetime.now().isoformat(),
        }).eq("id", approval_id).execute()

        # Check overall completion
        _check_clearance_completion(req["id"])

        # Notify student
        student_id = req.get("student_id")
        if student_id:
            create_notification(
                user_id=student_id,
                title=f"✅ Stage Approved: {stage.get('stage_name','')}",
                message="A clearance stage has been approved. Check your clearance status.",
                notification_type="success",
                action_url="/clearance",
            )

        write_audit_log("approve_clearance", target=f"approval:{approval_id}")
        flash("Clearance stage approved successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(url_for("clearance.approver_dashboard"))


# ── Reject a clearance stage ──────────────────────────────────────────────────

@clearance_bp.route("/reject/<approval_id>", methods=["POST"])
@login_required
def reject_clearance(approval_id):
    db = get_service_client()
    user = current_user()
    role = user["role"]
    comments = request.form.get("comments", "").strip()

    if not comments:
        flash("Reason for rejection is required.", "error")
        return redirect(url_for("clearance.approver_dashboard"))

    try:
        approval = (db.table("clearance_approvals")
                    .select("*, clearance_stages(stage_name, approver_role), "
                            "clearance_requests(id, student_id)")
                    .eq("id", approval_id)
                    .single()
                    .execute().data)

        if not approval:
            flash("Approval record not found.", "error")
            return redirect(url_for("clearance.approver_dashboard"))

        stage = approval.get("clearance_stages") or {}
        req   = approval.get("clearance_requests") or {}

        if stage.get("approver_role") != role and approval.get("approver_id") != user["id"]:
            abort(403)

        db.table("clearance_approvals").update({
            "status":      "rejected",
            "approver_id": user["id"],
            "comments":    comments,
            "approved_at": datetime.now().isoformat(),
        }).eq("id", approval_id).execute()

        db.table("clearance_requests").update({
            "status": "rejected"
        }).eq("id", req["id"]).execute()

        student_id = req.get("student_id")
        if student_id:
            create_notification(
                user_id=student_id,
                title=f"❌ Clearance Rejected: {stage.get('stage_name','')}",
                message=f"A clearance stage was rejected. Reason: {comments}",
                notification_type="warning",
                action_url="/clearance",
            )

        write_audit_log("reject_clearance", target=f"approval:{approval_id}")
        flash("Clearance stage rejected.", "warning")
    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(url_for("clearance.approver_dashboard"))


# ── Clearance certificate (download) ─────────────────────────────────────────

@clearance_bp.route("/certificate/<request_id>")
@login_required
def certificate(request_id):
    db = get_service_client()
    user = current_user()

    cr = (db.table("clearance_requests")
          .select("*, courses(name, code), departments(name), "
                  "user_profiles:user_profiles!clearance_requests_student_id_fkey(*)")
          .eq("id", request_id)
          .single()
          .execute().data)

    if not cr:
        abort(404)

    # Security: student can only access own; admin/dean/finance can access any
    if user["role"] == "student" and cr["student_id"] != user["id"]:
        abort(403)

    # Must be completed before download
    if cr.get("status") != "completed":
        flash("Clearance certificate is only available after all stages are approved.", "warning")
        return redirect(url_for("clearance.dashboard"))

    serial   = cr.get("serial_number") or _serial(cr["id"])
    approvals = _fetch_all_approvals(db, request_id)

    # Attach approver names
    approver_ids = [a["approver_id"] for a in approvals if a.get("approver_id")]
    approver_map = {}
    if approver_ids:
        profiles = (db.table("user_profiles")
                    .select("id, full_name, role")
                    .in_("id", approver_ids)
                    .execute().data or [])
        approver_map = {p["id"]: p for p in profiles}

    for a in approvals:
        a["_approver"] = approver_map.get(a.get("approver_id"), {})

    student = cr.get("user_profiles") or {}

    import os
    base_url = os.environ.get("APP_BASE_URL", request.host_url.rstrip("/"))
    verify_url = f"{base_url}/clearance/verify/{serial}"

    return render_template("clearance/clearance_certificate.html",
                           cr=cr,
                           student=student,
                           serial=serial,
                           verify_url=verify_url,
                           approvals=approvals,
                           GROUP_LABELS=GROUP_LABELS,
                           _global_group=_global_group)


# ── Clearance certificate PDF download ───────────────────────────────────────

@clearance_bp.route("/certificate/<request_id>/pdf")
@login_required
def certificate_pdf(request_id):
    """
    Generate and stream the TTTI Clearance Certificate as a PDF.

    Page layout:
      1. Centred header (logo + institute + Clearance Certificate title)
      2. Left-aligned student & course details
      3. Digital approvals grid  — one row per approver with name + date
      4. Remaining manual signature blocks:
         Finance Dept · Dean of Students · Registrar · Chief Principal
      5. Diagonal watermark (serial number)
    """
    db   = get_service_client()
    user = current_user()

    cr = (db.table("clearance_requests")
          .select("*, courses(name, code), departments(name), "
                  "user_profiles:user_profiles!clearance_requests_student_id_fkey(*)")
          .eq("id", request_id)
          .single()
          .execute().data)

    if not cr:
        abort(404)
    if user["role"] == "student" and cr["student_id"] != user["id"]:
        abort(403)
    if cr.get("status") != "completed":
        flash("The clearance certificate is only available once all stages are approved.", "warning")
        return redirect(url_for("clearance.dashboard"))

    serial    = cr.get("serial_number") or _serial(cr["id"])
    approvals = _fetch_all_approvals(db, request_id)

    # Attach approver profiles
    approver_ids = [a["approver_id"] for a in approvals if a.get("approver_id")]
    approver_map = {}
    if approver_ids:
        profiles = (db.table("user_profiles")
                    .select("id, full_name, role")
                    .in_("id", approver_ids)
                    .execute().data or [])
        approver_map = {p["id"]: p for p in profiles}
    for a in approvals:
        a["_approver"] = approver_map.get(a.get("approver_id") or "", {})

    student = cr.get("user_profiles") or {}

    # ── Build PDF ─────────────────────────────────────────────────────────────
    try:
        import io as _io, os as _os
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, HRFlowable,
                                        Image as RLImage, KeepTogether)

        buf = _io.BytesIO()
        pdf = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=18*mm, rightMargin=18*mm,
                                topMargin=14*mm,  bottomMargin=14*mm)
        W = A4[0] - 36*mm

        base    = getSampleStyleSheet()
        DARK    = colors.HexColor('#0f2c54')
        MID     = colors.HexColor('#1e40af')
        BORDER  = colors.HexColor('#e2e8f0')
        LGREY   = colors.HexColor('#f8fafc')
        GREEN   = colors.HexColor('#dcfce7')
        GTEXT   = colors.HexColor('#15803d')

        ctr14b  = ParagraphStyle('c14', parent=base['Normal'], fontSize=14,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=2)
        ctr11b  = ParagraphStyle('c11', parent=base['Normal'], fontSize=11,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=2)
        ctr9    = ParagraphStyle('c9',  parent=base['Normal'], fontSize=9,
                                 fontName='Helvetica', alignment=TA_CENTER, spaceAfter=1)
        lft10b  = ParagraphStyle('l10', parent=base['Normal'], fontSize=10,
                                 fontName='Helvetica-Bold')
        lft9b   = ParagraphStyle('l9b', parent=base['Normal'], fontSize=9,
                                 fontName='Helvetica-Bold')
        lft9    = ParagraphStyle('l9',  parent=base['Normal'], fontSize=9,
                                 fontName='Helvetica')
        tbl_h   = ParagraphStyle('th',  parent=base['Normal'], fontSize=8,
                                 fontName='Helvetica-Bold', alignment=TA_CENTER)
        tbl_c   = ParagraphStyle('tc',  parent=base['Normal'], fontSize=8,
                                 fontName='Helvetica', alignment=TA_CENTER)
        tbl_l   = ParagraphStyle('tl',  parent=base['Normal'], fontSize=8,
                                 fontName='Helvetica', alignment=TA_LEFT)

        story = []

        # ── 1.  CENTRED HEADER ────────────────────────────────────────────────
        logo_path = _os.path.join(_os.path.dirname(__file__),
                                  '..', 'static', 'assets', 'THIKATTILOGO.jpg')
        logo_cell = Paragraph("", lft9)
        if _os.path.exists(logo_path):
            try:
                logo_cell = RLImage(logo_path, width=22*mm, height=22*mm)
            except Exception:
                pass

        hdr = Table([[
            logo_cell,
            [Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", ctr14b),
             Paragraph("CLEARANCE CERTIFICATE", ctr11b),
             Paragraph("This certifies that the above-named student has been cleared "
                       "by all relevant departments.", ctr9),
             Paragraph(f"Serial No: {serial}", ctr9)],
            logo_cell,
        ]], colWidths=[24*mm, W - 48*mm, 24*mm])
        hdr.setStyle(TableStyle([
            ('VALIGN',        (0,0),(-1,-1),'MIDDLE'),
            ('ALIGN',         (1,0),(1,0), 'CENTER'),
            ('TOPPADDING',    (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ]))
        story.append(hdr)
        story.append(HRFlowable(width="100%", thickness=2, color=DARK, spaceAfter=6))

        # ── 2.  STUDENT & COURSE DETAILS ─────────────────────────────────────
        course = cr.get("courses") or {}
        dept   = cr.get("departments") or {}

        def _info_row(l1, v1, l2, v2):
            t = Table([[Paragraph(l1, lft9b), Paragraph(str(v1), lft9),
                        Paragraph(l2, lft9b), Paragraph(str(v2), lft9)]],
                      colWidths=[28*mm, W/2-28*mm, 28*mm, W/2-28*mm])
            t.setStyle(TableStyle([
                ('TOPPADDING',    (0,0),(-1,-1), 3),
                ('BOTTOMPADDING', (0,0),(-1,-1), 3),
                ('LINEBELOW',     (1,0),(1,0),   0.5, colors.grey),
                ('LINEBELOW',     (3,0),(3,0),   0.5, colors.grey),
                ('VALIGN',        (0,0),(-1,-1), 'BOTTOM'),
            ]))
            return t

        story.append(_info_row("Student Name:", student.get("full_name","—"),
                               "Admission No:", student.get("admission_no","—")))
        story.append(_info_row("Course:",       course.get("name","—"),
                               "Course Code:",  course.get("code","—")))
        story.append(_info_row("Department:",   dept.get("name","—"),
                               "Completed:",    (cr.get("completed_at") or "")[:10] or "—"))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=5))

        # ── 3.  DIGITAL APPROVALS GRID ────────────────────────────────────────
        story.append(Paragraph("DIGITAL CLEARANCE APPROVALS", lft10b))
        story.append(Spacer(1, 5))

        # Group approvals by stage group for display
        grouped = {}
        for a in approvals:
            stage = a.get("clearance_stages") or {}
            g     = _global_group(stage)
            sname = stage.get("stage_name") or GROUP_LABELS.get(g, f"Stage {g}")
            grouped.setdefault(g, {"label": sname, "items": []})["items"].append(a)

        appr_hdr = [Paragraph("#",        tbl_h),
                    Paragraph("Section",  tbl_h),
                    Paragraph("Stage",    tbl_h),
                    Paragraph("Approved by", tbl_l),
                    Paragraph("Date",     tbl_c),
                    Paragraph("Status",   tbl_c)]
        appr_data  = [appr_hdr]
        appr_style = [
            ('BACKGROUND',    (0,0),(-1,0), MID),
            ('TEXTCOLOR',     (0,0),(-1,0), colors.white),
            ('FONTNAME',      (0,0),(-1,-1),'Helvetica'),
            ('FONTSIZE',      (0,0),(-1,-1), 8),
            ('GRID',          (0,0),(-1,-1), 0.4, BORDER),
            ('TOPPADDING',    (0,0),(-1,-1), 3),
            ('BOTTOMPADDING', (0,0),(-1,-1), 3),
            ('LEFTPADDING',   (0,0),(-1,-1), 4),
            ('RIGHTPADDING',  (0,0),(-1,-1), 4),
            ('ALIGN',         (0,0),(-1,-1), 'CENTER'),
            ('ALIGN',         (1,0),(3,-1),  'LEFT'),
            ('VALIGN',        (0,0),(-1,-1), 'MIDDLE'),
            ('ROWBACKGROUNDS',(0,1),(-1,-1), [colors.white, LGREY]),
        ]
        row_n = 0
        for g in sorted(grouped.keys()):
            group_info = grouped[g]
            for a in group_info["items"]:
                row_n += 1
                stage    = a.get("clearance_stages") or {}
                approver = a.get("_approver") or {}
                status   = a.get("status","pending")
                appr_nm  = approver.get("full_name","—") if status == "approved" else "—"
                appr_date= (a.get("approved_at") or "")[:10] if status == "approved" else "—"
                status_txt = "✓ Approved" if status=="approved" else "Pending"
                ri = len(appr_data)
                appr_data.append([
                    Paragraph(str(row_n),                             tbl_c),
                    Paragraph(GROUP_LABELS.get(g, f"Stage {g}"),      tbl_l),
                    Paragraph(stage.get("stage_name","—"),             tbl_l),
                    Paragraph(appr_nm,                                 tbl_l),
                    Paragraph(appr_date,                               tbl_c),
                    Paragraph(status_txt,                              tbl_c),
                ])
                if status == "approved":
                    appr_style.append(('TEXTCOLOR', (5,ri),(5,ri), GTEXT))
                    appr_style.append(('FONTNAME',  (5,ri),(5,ri), 'Helvetica-Bold'))

        appr_tbl = Table(appr_data,
                         colWidths=[8*mm, 36*mm, 40*mm, W-8*mm-36*mm-40*mm-26*mm-20*mm,
                                    26*mm, 20*mm],
                         repeatRows=1)
        appr_tbl.setStyle(TableStyle(appr_style))
        story += [appr_tbl, Spacer(1, 12)]

        # ── 4.  MANUAL SIGNATURE BLOCKS ───────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=1, color=DARK, spaceAfter=8))
        story.append(Paragraph("OFFICIAL SIGN-OFF", lft10b))
        story.append(Paragraph(
            "The following officials must sign and stamp this form to complete clearance.",
            lft9))
        story.append(Spacer(1, 8))

        # 4 officials  — 2 per row
        officials = [
            "FINANCE DEPARTMENT",
            "DEAN OF STUDENTS",
            "REGISTRAR",
            "CHIEF PRINCIPAL",
        ]
        line = "_" * 34

        def _sig_block_clr(title):
            rows = [
                [Paragraph(f"<b>{title}</b>",
                           ParagraphStyle('sh2', parent=lft9b, fontSize=9,
                                          textColor=DARK))],
                [Spacer(1,4)],
                [Paragraph(f"Name:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
                [Spacer(1,3)],
                [Paragraph(f"Signature: {line}", lft9)],
                [Spacer(1,3)],
                [Paragraph(f"Date:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
                [Spacer(1,3)],
                [Paragraph(f"Stamp:&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
            ]
            half = W / 2 - 5*mm
            t = Table(rows, colWidths=[half])
            t.setStyle(TableStyle([
                ('TOPPADDING',    (0,0),(-1,-1), 2),
                ('BOTTOMPADDING', (0,0),(-1,-1), 2),
                ('LEFTPADDING',   (0,0),(-1,-1), 0),
                ('BOX',           (0,0),(-1,-1), 0.5, BORDER),
                ('BACKGROUND',    (0,0),(0,0),   LGREY),
            ]))
            return t

        half = W / 2 - 5*mm
        for i in range(0, len(officials), 2):
            left  = _sig_block_clr(officials[i])
            right = _sig_block_clr(officials[i+1]) if i+1 < len(officials) else Paragraph("", lft9)
            row_tbl = Table([[left, Spacer(10*mm, 1), right]],
                            colWidths=[half, 10*mm, half])
            row_tbl.setStyle(TableStyle([
                ('VALIGN',        (0,0),(-1,-1), 'TOP'),
                ('TOPPADDING',    (0,0),(-1,-1), 0),
                ('BOTTOMPADDING', (0,0),(-1,-1), 8),
            ]))
            story.append(row_tbl)

        # ── 5.  FOOTER ────────────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=3))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}  ·  "
            f"Serial: {serial}  ·  Verify at: /clearance/verify/{serial}",
            ctr9))

        # ── WATERMARK ─────────────────────────────────────────────────────────
        _serial_wm = serial

        def _wm(canvas_obj, doc_obj):
            canvas_obj.saveState()
            canvas_obj.setFont("Helvetica-Bold", 40)
            canvas_obj.setFillColorRGB(0.75, 0.75, 0.75, alpha=0.15)
            canvas_obj.translate(A4[0]/2, A4[1]/2)
            canvas_obj.rotate(45)
            canvas_obj.drawCentredString(0, 20,  "TTTI CLEARANCE CERTIFICATE")
            canvas_obj.drawCentredString(0, -30, _serial_wm)
            canvas_obj.restoreState()

        pdf.build(story, onFirstPage=_wm, onLaterPages=_wm)
        pdf_bytes = buf.getvalue()

        from flask import make_response
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        safe = serial.replace("/", "-")
        resp.headers["Content-Disposition"] = \
            f'attachment; filename="Clearance_{safe}_{student.get("admission_no","")}.pdf"'
        return resp

    except ImportError:
        flash("PDF generation requires reportlab. Run: pip install reportlab pillow", "warning")
        return redirect(url_for("clearance.certificate", request_id=request_id))
    except Exception as exc:
        flash(f"Could not generate PDF: {exc}", "danger")
        return redirect(url_for("clearance.certificate", request_id=request_id))


# ── Public verification ───────────────────────────────────────────────────────

@clearance_bp.route("/verify", methods=["GET", "POST"])
@clearance_bp.route("/verify/<serial_number>")
def verify(serial_number=None):
    db = get_service_client()
    result = None
    error  = None

    if request.method == "POST":
        serial_number = request.form.get("serial_number", "").strip().upper()

    if serial_number:
        # Try to find by serial_number column first
        rows = []
        try:
            rows = (db.table("clearance_requests")
                    .select("*, courses(name, code), departments(name), "
                            "user_profiles:user_profiles!clearance_requests_student_id_fkey"
                            "(full_name, admission_no)")
                    .eq("serial_number", serial_number)
                    .execute().data or [])
        except Exception:
            pass

        # Fallback: derive serial from id prefix and search
        if not rows:
            # serial format: CLR/YYYY/XXXXXXXX  → last 6 chars of UUID (no dashes) uppercased
            # Search completed requests and match
            try:
                completed = (db.table("clearance_requests")
                             .select("id, status, completed_at, serial_number, "
                                     "courses(name, code), departments(name), "
                                     "user_profiles:user_profiles!clearance_requests_student_id_fkey"
                                     "(full_name, admission_no)")
                             .eq("status", "completed")
                             .execute().data or [])
                for row in completed:
                    if _serial(row["id"]) == serial_number:
                        rows = [row]
                        break
            except Exception as e:
                error = str(e)

        if rows:
            cr = rows[0]
            if cr.get("status") == "completed":
                result = cr
                result["_serial"] = cr.get("serial_number") or _serial(cr["id"])
            else:
                error = f"Clearance with serial {serial_number} exists but is not yet completed."
        else:
            error = f"No completed clearance found with serial number '{serial_number}'."

    return render_template("clearance/verify.html",
                           serial_number=serial_number,
                           result=result,
                           error=error)


# ── Internal: completion check ────────────────────────────────────────────────

def _check_clearance_completion(request_id: str):
    db = get_service_client()
    approvals = (db.table("clearance_approvals")
                 .select("status, clearance_stages(stage_name, approver_role, "
                         "  clearance_departments(clearance_type))")
                 .eq("clearance_request_id", request_id)
                 .execute().data or [])

    if not approvals:
        return

    # Only digital groups 1-4 count for completion.
    # Groups 5 (Finance) and 6 (Dean/Registrar) are signed manually on the PDF.
    digital = [a for a in approvals
               if _global_group(a.get("clearance_stages") or {}) <= 4]

    any_rejected = any(a["status"] == "rejected" for a in digital)
    all_approved = bool(digital) and all(a["status"] == "approved" for a in digital)

    if any_rejected:
        db.table("clearance_requests").update({"status": "rejected"}).eq("id", request_id).execute()
    elif all_approved:
        serial = _serial(request_id)
        update = {"status": "completed", "completed_at": datetime.now().isoformat()}
        try:
            db.table("clearance_requests").update({**update, "serial_number": serial}).eq("id", request_id).execute()
        except Exception:
            db.table("clearance_requests").update(update).eq("id", request_id).execute()

        try:
            req = (db.table("clearance_requests")
                   .select("student_id")
                   .eq("id", request_id)
                   .single()
                   .execute().data)
            if req:
                create_notification(
                    user_id=req["student_id"],
                    title="🎓 Clearance Complete!",
                    message=f"All stages approved. Serial: {serial}. Download your clearance certificate.",
                    notification_type="success",
                    action_url="/clearance",
                )
        except Exception:
            pass

        write_audit_log("clearance_completed", target=f"request:{request_id}")


# ── Legacy route aliases ──────────────────────────────────────────────────────

@clearance_bp.route("/clearance-form/<request_id>")
@login_required
def clearance_form(request_id):
    return redirect(url_for("clearance.certificate", request_id=request_id))


@clearance_bp.route("/issue-certificate/<request_id>", methods=["POST"])
@login_required
def issue_certificate(request_id):
    """Legacy: mark certificate as issued (now handled automatically)."""
    return redirect(url_for("clearance.certificate", request_id=request_id))
