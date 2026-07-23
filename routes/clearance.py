"""
Clearance Blueprint — Parallel Stage 1 + Sequential Stage 2

Flow:
  Stage 1 (ALL in parallel on initiation):
    - trainer        : all trainers who taught the student
    - tech_1 / tech_2: first & second workshop technician in home dept
    - svc_library    : Institute Library
    - svc_ict        : ICT Department
    - svc_games      : Games Department
    - svc_kitchen    : Kitchen / Cafeteria
    - svc_store      : Store Department
    - ext_knls       : Kenya National Library Service
    - ext_community  : Community / County Library
    - hod_other      : ALL dept_admin users in other departments

  Stage 1 complete when:
    - >= min(7, total_active_trainers) trainers approved (waived count as approved)
    - all workshop technicians in home dept approved or waived by HOD
    - all service dept approvals approved
    - all external service approvals approved
    - all hod_other approvals approved

  Stage 2 (unlocked by Stage 1):
    - hod_home: home dept HOD final review → approve / reject / return for correction

  Stage 3 (completed):
    - certificate available for download with serial number + QR code
"""

import uuid as _uuid
from datetime import datetime
from flask import (Blueprint, render_template, request, flash,
                   redirect, url_for, abort, jsonify)
from auth_utils import login_required, student_required, current_user, write_audit_log
from db import get_service_client
from notifications import create_notification

clearance_bp = Blueprint("clearance", __name__)

# Trainee-owned clearance lifecycle helpers
_ACTIVE_CLEARANCE = ("pending", "in_progress", "returned")
_STOPPABLE_CLEARANCE = ("pending", "in_progress", "returned", "rejected")

# ── Constants ─────────────────────────────────────────────────────────────────

MIN_TRAINERS = 7

STAGE1_CATEGORIES = {
    "trainer", "tech_1", "tech_2",
    "svc_library", "svc_ict", "svc_games", "svc_kitchen", "svc_store",
    "ext_knls", "ext_community",
    "hod_other",
}

STAGE2_CATEGORIES = {"hod_home"}

SERVICE_DEPT_CATEGORIES = {
    "svc_library", "svc_ict", "svc_games", "svc_kitchen", "svc_store",
    "ext_knls", "ext_community",
}

CATEGORY_LABELS = {
    "trainer":      "Trainer Clearance",
    "tech_1":       "Workshop Technician 1",
    "tech_2":       "Workshop Technician 2",
    "svc_library":  "Institute Library",
    "svc_ict":      "ICT Department",
    "svc_games":    "Games Department",
    "svc_kitchen":  "Kitchen / Cafeteria",
    "svc_store":    "Store Department",
    "ext_knls":     "Kenya National Library Service",
    "ext_community":"Community / County Library",
    "hod_other":    "Other Department HOD",
    "hod_home":     "Home Department HOD (Final)",
}

# Portal base template per role (clearance pages reuse the role's sidebar/layout)
CLEARANCE_PORTAL_BASE = {
    "trainer":               "trainer/base.html",
    "dept_admin":            "dept_admin/base.html",
    "liaison_officer":       "liaison_officer/base.html",
    "workshop_technician":   "workshop_technician/base.html",
    "super_admin":           "super_admin/base.html",
    "library_hod":           "service_dept/base.html",
    "sports_hod":            "service_dept/base.html",
    "service_clearance_officer": "service_dept/base.html",
    "environment_hod":       "admin_oversight/base.html",
    "dean_students":         "admin_oversight/base.html",
    "finance_officer":       "admin_oversight/base.html",
    "registrar":             "admin_oversight/base.html",
    "deputy_principal":      "admin_oversight/base.html",
    "quality_assurance_officer": "admin_oversight/base.html",
}


def _portal_base_template(role: str) -> str:
    return CLEARANCE_PORTAL_BASE.get(role, "dept_admin/base.html")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serial(request_id: str) -> str:
    """Generate unique clearance serial: TTTI/CLR/{year}/{hex8}."""
    year = datetime.now().year
    hex8 = str(request_id).replace("-", "")[:8].upper()
    return f"TTTI/CLR/{year}/{hex8}"


def _infer_category(approval: dict) -> str:
    """
    Infer approver_category from stage name keywords when the column is absent
    or NULL. Returns empty string if unable to infer.
    """
    stage = approval.get("clearance_stages") or {}
    name  = (stage.get("stage_name") or "").lower()
    role  = (stage.get("approver_role") or "").lower()

    if role == "trainer" and "technician" not in name:
        return "trainer"
    if "technician" in name or role == "workshop_technician":
        return "tech_1"
    if "library" in name or "lib" in name:
        if "kenya" in name or "knls" in name:
            return "ext_knls"
        if "community" in name or "county" in name:
            return "ext_community"
        return "svc_library"
    if "ict" in name or "computer" in name:
        return "svc_ict"
    if "games" in name or "sports" in name:
        return "svc_games"
    if "kitchen" in name or "cafeteria" in name:
        return "svc_kitchen"
    if "store" in name or "stores" in name:
        return "svc_store"
    if role == "dept_admin":
        return "hod_other"
    return ""


def _get_category(approval: dict) -> str:
    """Return the approver_category, falling back to inference."""
    cat = approval.get("approver_category") or ""
    if cat:
        return cat
    return _infer_category(approval)


def _map_stage_name_to_category(name: str, dept_name: str) -> str:
    """Map a clearance stage name / dept name to a service category."""
    n = name.lower()
    d = dept_name.lower()
    combined = n + " " + d
    if "kenya" in combined or "knls" in combined:
        return "ext_knls"
    if "community" in combined or "county" in combined:
        return "ext_community"
    if "library" in combined or "lib" in combined:
        return "svc_library"
    if "ict" in combined or "computer" in combined:
        return "svc_ict"
    if "games" in combined or "sports" in combined:
        return "svc_games"
    if "kitchen" in combined or "cafeteria" in combined:
        return "svc_kitchen"
    if "store" in combined or "stores" in combined:
        return "svc_store"
    return ""


def _fetch_all_approvals(db, request_id: str) -> list:
    """Return all approval rows for a request (with stage info)."""
    return (db.table("clearance_approvals")
              .select("*, clearance_stages(stage_name, approver_role, "
                      "  clearance_departments(name, clearance_type, code))")
              .eq("clearance_request_id", request_id)
              .execute().data or [])


ROLE_TO_SVC_CAT = {
    "library_hod": "svc_library",
    "sports_hod":  "svc_games",
}


def _approver_back(role: str) -> str:
    """Return post-action redirect for the given approver role."""
    if role in ("library_hod", "sports_hod", "service_clearance_officer"):
        return url_for("service_dept.dashboard")
    return url_for("clearance.approver_dashboard")


# ── Stage 1 completion logic ──────────────────────────────────────────────────

def _stage1_complete(db, request_id: str, home_dept_id: str) -> bool:
    """
    Returns True when ALL Stage 1 requirements are satisfied:
      - Enough trainers approved / waived
      - tech_1 and tech_2 approved / waived
      - All service dept approvals approved / waived
      - All external service approvals approved / waived
      - All hod_other approvals approved / waived
    """
    approvals = _fetch_all_approvals(db, request_id)
    s1 = [a for a in approvals if _get_category(a) in STAGE1_CATEGORIES]

    if not s1:
        return False

    def _ok(a):
        return a.get("status") == "approved" or a.get("is_waived") is True

    # Trainers
    trainers = [a for a in s1 if _get_category(a) == "trainer"]
    if trainers:
        approved_t = sum(1 for a in trainers if _ok(a))
        required_t = min(MIN_TRAINERS, len(trainers))
        if approved_t < required_t:
            return False

    # All workshop technicians (tech_1 rows — one per technician; tech_2 for legacy rows)
    for cat in ("tech_1", "tech_2"):
        items = [a for a in s1 if _get_category(a) == cat]
        if items and not all(_ok(a) for a in items):
            return False

    # Service depts and external services
    for cat in SERVICE_DEPT_CATEGORIES:
        items = [a for a in s1 if _get_category(a) == cat]
        if items and not all(_ok(a) for a in items):
            return False

    # Other HODs
    hod_others = [a for a in s1 if _get_category(a) == "hod_other"]
    if hod_others and not all(_ok(a) for a in hod_others):
        return False

    return True


def _check_stage1_and_advance(db, request_id: str):
    """
    After any Stage 1 approval, check if Stage 1 is complete.
    If so, create the Stage 2 hod_home approval and notify.
    """
    # Get request info
    cr = (db.table("clearance_requests")
          .select("id, student_id, department_id, stage, status")
          .eq("id", request_id)
          .single()
          .execute().data)
    if not cr:
        return
    if cr.get("stage", 1) >= 2:
        return  # already advanced
    if cr.get("status") in ("completed", "rejected"):
        return

    home_dept_id = cr.get("department_id")

    if not _stage1_complete(db, request_id, home_dept_id):
        return

    # Stage 1 complete — advance to Stage 2
    db.table("clearance_requests").update({"stage": 2}).eq("id", request_id).execute()

    # Find home dept HOD(s)
    hod_rows = (db.table("user_profiles")
                .select("id, full_name")
                .eq("role", "dept_admin")
                .eq("department_id", home_dept_id)
                .execute().data or [])

    for hod in hod_rows:
        # Check if Stage 2 approval already exists for this HOD
        existing = (db.table("clearance_approvals")
                    .select("id")
                    .eq("clearance_request_id", request_id)
                    .eq("approver_category", "hod_home")
                    .eq("approver_id", hod["id"])
                    .execute().data or [])
        if existing:
            continue

        db.table("clearance_approvals").insert({
            "clearance_request_id": request_id,
            "clearance_stage_id":   None,
            "approver_id":          hod["id"],
            "approver_category":    "hod_home",
            "clearance_stage":      2,
            "status":               "pending",
        }).execute()

        try:
            sp = (db.table("user_profiles")
                  .select("full_name")
                  .eq("id", cr["student_id"])
                  .single()
                  .execute().data)
            sname = (sp or {}).get("full_name", "A trainee")
            create_notification(
                user_id=hod["id"],
                title="Stage 1 Complete — Final Clearance Review Needed",
                message=(
                    f"{sname} has completed all Stage 1 clearances. "
                    "Please review and issue the final clearance."
                ),
                notification_type="info",
                action_url="/clearance/approver",
            )
        except Exception:
            pass


def _check_clearance_completion(db, request_id: str):
    """
    Check if Stage 2 hod_home approval is done.
    If approved → mark clearance completed and issue certificate.
    If rejected → mark rejected.
    """
    approvals = _fetch_all_approvals(db, request_id)
    s2 = [a for a in approvals if _get_category(a) == "hod_home"]

    if not s2:
        return

    any_rejected = any(a.get("status") == "rejected" for a in s2)
    all_approved = all(a.get("status") == "approved" for a in s2)

    if any_rejected:
        db.table("clearance_requests").update({"status": "rejected"}).eq("id", request_id).execute()
    elif all_approved:
        serial = _serial(request_id)
        update = {
            "status":       "completed",
            "completed_at": datetime.now().isoformat(),
        }
        try:
            db.table("clearance_requests").update({
                **update, "serial_number": serial
            }).eq("id", request_id).execute()
        except Exception:
            db.table("clearance_requests").update(update).eq("id", request_id).execute()

        # Notify student
        try:
            cr = (db.table("clearance_requests")
                  .select("student_id")
                  .eq("id", request_id)
                  .single()
                  .execute().data)
            if cr:
                create_notification(
                    user_id=cr["student_id"],
                    title="Clearance Complete!",
                    message=(
                        f"All stages approved. Serial: {serial}. "
                        "Download your clearance certificate now."
                    ),
                    notification_type="success",
                    action_url="/clearance",
                )
        except Exception:
            pass

        write_audit_log("clearance_completed", target=f"request:{request_id}")


# ── Student: clearance dashboard ──────────────────────────────────────────────

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
                .limit(10)
                .execute().data or [])

    enrollments = (db.table("enrollments")
                   .select("*, classes(course_id, courses(name, code))")
                   .eq("student_id", student_id)
                   .execute().data or [])

    # Prefer an active request; otherwise a completed one (certificate).
    # Cancelled / rejected do not block initiate — trainee can start again.
    active_cr = next(
        (r for r in req_rows if (r.get("status") or "") in _ACTIVE_CLEARANCE),
        None,
    )
    completed_cr = next(
        (r for r in req_rows if (r.get("status") or "") == "completed"),
        None,
    )
    cr = active_cr or completed_cr

    if not cr:
        return render_template(
            "clearance/student_dashboard.html",
            clearance_request=None,
            has_request=False,
            can_stop=False,
            enrollments=enrollments,
            stage1_sections=[],
            stage2_approval=None,
            serial=None,
            last_cancelled=next(
                (r for r in req_rows if (r.get("status") or "") in ("cancelled", "rejected")),
                None,
            ),
        )

    serial = cr.get("serial_number") or _serial(cr["id"])
    approvals = _fetch_all_approvals(db, cr["id"])
    can_stop = (cr.get("status") or "") in _STOPPABLE_CLEARANCE

    # ── Attach approver names to all approval records ────────────────────────
    approver_ids = [a["approver_id"] for a in approvals if a.get("approver_id")]
    _approver_map = {}
    if approver_ids:
        _ap_rows = (db.table("user_profiles")
                    .select("id, full_name, role")
                    .in_("id", approver_ids)
                    .execute().data or [])
        _approver_map = {p["id"]: p for p in _ap_rows}
    for a in approvals:
        a["_approver"] = _approver_map.get(a.get("approver_id") or "", {})

    # ── Build stage 1 summary sections ──────────────────────────────────────
    s1_cats_order = [
        "trainer", "tech_1", "tech_2",
        "svc_library", "svc_ict", "svc_games", "svc_kitchen", "svc_store",
        "ext_knls", "ext_community",
        "hod_other",
    ]

    def _ok(a):
        return a.get("status") == "approved" or a.get("is_waived") is True

    # Flag if fewer than MIN_TRAINERS trainers were identified
    all_trainer_approvals = [a for a in approvals if _get_category(a) == "trainer"]
    low_trainers = len(all_trainer_approvals) < MIN_TRAINERS

    stage1_sections = []
    for cat in s1_cats_order:
        items = [a for a in approvals if _get_category(a) == cat]
        if not items:
            continue
        approved = sum(1 for a in items if _ok(a))
        total    = len(items)
        rejected = any(a.get("status") == "rejected" for a in items)
        if all(_ok(a) for a in items):
            status = "approved"
        elif rejected:
            status = "rejected"
        else:
            status = "pending"
        stage1_sections.append({
            "category": cat,
            "label":    CATEGORY_LABELS.get(cat, cat),
            "status":   status,
            "approved": approved,
            "total":    total,
            "approvals": items,
        })

    # ── Stage 2 ──────────────────────────────────────────────────────────────
    stage2_items = [a for a in approvals if _get_category(a) == "hod_home"]
    stage2_approval = stage2_items[0] if stage2_items else None

    # Compute stage 1 overall completion
    stage1_done = (cr.get("stage", 1) >= 2) or (
        cr.get("status") == "completed"
    )

    return render_template(
        "clearance/student_dashboard.html",
        clearance_request=cr,
        has_request=True,
        can_stop=can_stop,
        serial=serial,
        approvals=approvals,
        enrollments=enrollments,
        stage1_sections=stage1_sections,
        stage2_approval=stage2_approval,
        stage1_done=stage1_done,
        low_trainers=low_trainers,
        MIN_TRAINERS=MIN_TRAINERS,
        CATEGORY_LABELS=CATEGORY_LABELS,
    )


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
              .in_("status", ["pending", "in_progress", "returned"])
              .execute().data):
            flash("You already have an active clearance request.", "warning")
            return redirect(url_for("clearance.dashboard"))

        dept_id = course["departments"]["id"]

        # Create clearance request
        result = db.table("clearance_requests").insert({
            "student_id":    student_id,
            "course_id":     course_id,
            "department_id": dept_id,
            "status":        "in_progress",
            "stage":         1,
            "created_by":    user["id"],
        }).execute()
        request_id = result.data[0]["id"]
        serial     = _serial(request_id)

        # Save serial_number (non-fatal if column missing)
        try:
            db.table("clearance_requests").update(
                {"serial_number": serial}
            ).eq("id", request_id).execute()
        except Exception:
            pass

        # ── Collect all approver data ──────────────────────────────────────

        # 1. Trainers who taught this student
        att = (db.table("attendance")
               .select("trainer_id")
               .eq("student_id", student_id)
               .execute().data or [])
        trainer_ids = list({r["trainer_id"] for r in att if r.get("trainer_id")})

        # 2. ALL workshop technicians in home dept (one row each, all as tech_1)
        tech_rows = (db.table("user_profiles")
                     .select("id")
                     .eq("role", "workshop_technician")
                     .eq("department_id", dept_id)
                     .order("created_at")
                     .execute().data or [])
        tech_ids = [t["id"] for t in tech_rows]

        # 3. Other dept HODs (all dept_admin users not in home dept)
        other_hod_rows = (db.table("user_profiles")
                          .select("id, full_name, department_id")
                          .eq("role", "dept_admin")
                          .neq("department_id", dept_id)
                          .execute().data or [])

        # 4. Service depts — look up from clearance_stages
        try:
            stage_rows = (db.table("clearance_stages")
                          .select("*, clearance_departments(name, clearance_type, code)")
                          .execute().data or [])
        except Exception:
            stage_rows = []

        # Map each stage to a service category
        svc_approver_map = {}  # category -> approver_id (or None)
        for row in stage_rows:
            cd    = row.get("clearance_departments") or {}
            ctype = (cd.get("clearance_type") or "").lower()
            sname = row.get("stage_name") or ""
            dname = cd.get("name") or ""
            if ctype not in ("institutional", "external"):
                continue
            cat = _map_stage_name_to_category(sname, dname)
            if not cat:
                continue
            approver_id = row.get("approver_id")  # may be NULL
            if cat not in svc_approver_map:
                svc_approver_map[cat] = approver_id

        # Ensure all required service categories are present
        required_svc = [
            "svc_library", "svc_ict", "svc_games", "svc_kitchen", "svc_store",
            "ext_knls", "ext_community",
        ]
        for cat in required_svc:
            if cat not in svc_approver_map:
                svc_approver_map[cat] = None  # no assigned approver yet

        # ── Insert all Stage 1 approval records ───────────────────────────

        def _insert(approver_id=None, category="", stage_num=1):
            try:
                db.table("clearance_approvals").insert({
                    "clearance_request_id": request_id,
                    "clearance_stage_id":   None,
                    "approver_id":          approver_id,
                    "approver_category":    category,
                    "clearance_stage":      stage_num,
                    "status":               "pending",
                }).execute()
            except Exception:
                # Fallback: without new columns
                db.table("clearance_approvals").insert({
                    "clearance_request_id": request_id,
                    "clearance_stage_id":   None,
                    "approver_id":          approver_id,
                    "status":               "pending",
                }).execute()

        # Trainers — flag if fewer than 7 identified
        if trainer_ids:
            for tid in trainer_ids:
                _insert(approver_id=tid, category="trainer")
            if len(trainer_ids) < MIN_TRAINERS:
                flash(
                    f"⚠ Only {len(trainer_ids)} trainer(s) identified from attendance records "
                    f"(minimum {MIN_TRAINERS} required). The Home Department HOD may waive "
                    f"remaining trainer approvals on your behalf.",
                    "warning",
                )
        else:
            _insert(category="trainer")

        # ALL workshop technicians in home dept (one tech_1 row per technician)
        if tech_ids:
            for tid in tech_ids:
                _insert(approver_id=tid, category="tech_1")
        else:
            _insert(category="tech_1")  # placeholder if no technicians assigned

        # Service depts
        for cat, approver_id in svc_approver_map.items():
            _insert(approver_id=approver_id, category=cat)

        # Other dept HODs
        for hod in other_hod_rows:
            _insert(approver_id=hod["id"], category="hod_other")

        # ── Send notifications ────────────────────────────────────────────

        try:
            sp = (db.table("user_profiles")
                  .select("full_name")
                  .eq("id", student_id)
                  .single()
                  .execute().data)
            sname = (sp or {}).get("full_name", "A trainee")

            for tid in trainer_ids:
                create_notification(
                    user_id=tid,
                    title="Clearance Approval Required",
                    message=f"{sname} has initiated clearance and requires your sign-off.",
                    notification_type="info",
                    action_url="/clearance/approver",
                )
            for tid in tech_ids:
                create_notification(
                    user_id=tid,
                    title="Trainee Clearance — Workshop Sign-Off Needed",
                    message=f"{sname} requires your workshop clearance approval.",
                    notification_type="info",
                    action_url="/clearance/approver",
                )
            for hod in other_hod_rows:
                create_notification(
                    user_id=hod["id"],
                    title="Clearance Approval Required — Other Dept HOD",
                    message=f"{sname} requires your department's clearance sign-off.",
                    notification_type="info",
                    action_url="/clearance/approver",
                )
            # Service department approvers (library, ICT, games, kitchen, store, external)
            for cat, approver_id in svc_approver_map.items():
                if approver_id:
                    create_notification(
                        user_id=approver_id,
                        title="Trainee Clearance — Service Sign-Off Needed",
                        message=(f"{sname} requires clearance from "
                                 f"{CATEGORY_LABELS.get(cat, 'your service department')}."),
                        notification_type="info",
                        action_url="/clearance/approver",
                    )
        except Exception:
            pass

        write_audit_log("initiate_clearance", target=f"request:{request_id}")
        flash(
            f"Clearance initiated successfully. Your serial number is {serial}.",
            "success",
        )

    except Exception as e:
        flash(f"Error initiating clearance: {e}", "error")

    return redirect(url_for("clearance.dashboard"))


# ── Student: stop / delete clearance ──────────────────────────────────────────

@clearance_bp.route("/stop/<request_id>", methods=["POST"])
@login_required
@student_required
def stop_clearance(request_id):
    """
    Trainee stops (cancels) their own active clearance process.
    Soft-cancels the request and removes pending approval rows so
    they can initiate a new clearance afterwards.
    Completed clearances cannot be stopped.
    """
    db = get_service_client()
    user = current_user()

    try:
        cr = (db.table("clearance_requests")
              .select("id, student_id, status, serial_number")
              .eq("id", request_id)
              .single()
              .execute().data)

        if not cr:
            abort(404)
        if cr.get("student_id") != user["id"]:
            abort(403)

        status = cr.get("status") or ""
        if status == "completed":
            flash("A completed clearance with an issued certificate cannot be stopped.", "error")
            return redirect(url_for("clearance.dashboard"))
        if status not in _STOPPABLE_CLEARANCE:
            flash("This clearance cannot be stopped in its current state.", "warning")
            return redirect(url_for("clearance.dashboard"))

        # Soft-cancel (preferred for audit). Fall back to hard-delete if the
        # DB status constraint has not yet been migrated to allow 'cancelled'.
        cancelled = False
        try:
            db.table("clearance_requests").update({
                "status": "cancelled",
            }).eq("id", request_id).eq("student_id", user["id"]).execute()
            cancelled = True
            try:
                db.table("clearance_requests").update({
                    "cancelled_at": datetime.now().isoformat(),
                    "cancelled_by": user["id"],
                }).eq("id", request_id).execute()
            except Exception:
                pass
        except Exception:
            cancelled = False

        if not cancelled:
            # Hard-delete removes the request; approvals cascade if FK is set.
            db.table("clearance_approvals").delete().eq("clearance_request_id", request_id).execute()
            db.table("clearance_requests").delete().eq("id", request_id).eq("student_id", user["id"]).execute()
        else:
            # Clear pending approval work from approver queues
            try:
                (db.table("clearance_approvals")
                   .delete()
                   .eq("clearance_request_id", request_id)
                   .eq("status", "pending")
                   .execute())
            except Exception:
                pass

        write_audit_log(
            "stop_clearance",
            target=f"request:{request_id}",
            detail={"status_was": status, "serial": cr.get("serial_number") or ""},
        )
        flash(
            "Clearance process stopped. You can start a new clearance when ready.",
            "success",
        )

    except Exception as e:
        flash(f"Error stopping clearance: {e}", "error")

    return redirect(url_for("clearance.dashboard"))


# ── Service Department Clearance Dashboard (Library HOD / Sports HOD) ────────

SVC_DEPT_META = {
    "svc_library": {"label": "Institute Library",  "icon": "fa-book",   "color": "#1d4ed8", "bg": "#dbeafe"},
    "svc_games":   {"label": "Games Department",   "icon": "fa-futbol", "color": "#16a34a", "bg": "#dcfce7"},
    "svc_ict":     {"label": "ICT Department",     "icon": "fa-laptop", "color": "#7c3aed", "bg": "#ede9fe"},
    "svc_kitchen": {"label": "Kitchen / Cafeteria","icon": "fa-utensils","color":"#b45309", "bg": "#fef3c7"},
    "svc_store":   {"label": "Store Department",   "icon": "fa-warehouse","color":"#0e7490","bg": "#cffafe"},
}


@clearance_bp.route("/service-dept")
@login_required
def service_dept_dashboard():
    db   = get_service_client()
    user = current_user()
    role = user["role"]
    uid  = user["id"]

    # Determine which category this role manages
    cat = ROLE_TO_SVC_CAT.get(role)
    if not cat:
        # Fallback for unknown roles
        return redirect(url_for("clearance.approver_dashboard"))

    meta = SVC_DEPT_META.get(cat, {"label": cat, "icon": "fa-cog", "color": "#374151", "bg": "#f3f4f6"})

    base_sel = (
        "id, approver_category, status, comments, approved_at, created_at, approver_id, is_waived, "
        "clearance_requests(id, student_id, status, stage, created_at, "
        "  user_profiles:user_profiles!clearance_requests_student_id_fkey"
        "  (full_name, admission_no, phone), "
        "  courses(name, code), departments(name))"
    )

    # Records assigned to this user
    assigned = (db.table("clearance_approvals")
                  .select(base_sel)
                  .eq("approver_id", uid)
                  .eq("approver_category", cat)
                  .order("created_at", desc=True)
                  .execute().data or [])

    # Unassigned (null approver_id) pending records for this category
    unassigned = (db.table("clearance_approvals")
                    .select(base_sel)
                    .is_("approver_id", "null")
                    .eq("approver_category", cat)
                    .eq("status", "pending")
                    .order("created_at", desc=True)
                    .execute().data or [])

    seen = set()
    all_rows = []
    for row in assigned + unassigned:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        req = row.get("clearance_requests") or {}
        row["_student"]    = req.get("user_profiles") or {}
        row["_course"]     = req.get("courses") or {}
        row["_dept"]       = req.get("departments") or {}
        row["_req_id"]     = req.get("id", "")
        row["_req_status"] = req.get("status", "")
        row["_claimable"]  = row.get("approver_id") is None
        all_rows.append(row)

    pending   = [r for r in all_rows if r.get("status") == "pending"
                 and r.get("_req_status") not in ("completed", "rejected")]
    cleared   = [r for r in all_rows if r.get("status") == "approved"]
    rejected  = [r for r in all_rows if r.get("status") == "rejected"]

    template_kwargs = dict(
        pending=pending,
        cleared=cleared,
        rejected=rejected,
        cat=cat,
        meta=meta,
        user_role=role,
        CATEGORY_LABELS=CATEGORY_LABELS,
        portal_base=_portal_base_template(role),
    )
    try:
        from routes.service_dept import DEPT_CONFIG
        if role in DEPT_CONFIG:
            template_kwargs["config"] = DEPT_CONFIG[role]
            template_kwargs["user"] = user
    except ImportError:
        pass

    return render_template("clearance/service_dept_dashboard.html", **template_kwargs)


# ── Approver dashboard ────────────────────────────────────────────────────────

@clearance_bp.route("/approver")
@login_required
def approver_dashboard():
    db   = get_service_client()
    user = current_user()
    role = user["role"]
    uid  = user["id"]

    base_select = (
        "*, "
        "clearance_requests(id, student_id, status, department_id, stage, "
        "  user_profiles:user_profiles!clearance_requests_student_id_fkey"
        "  (full_name, admission_no, department_id)), "
        "clearance_stages(stage_name, approver_role, stage_order, "
        "  clearance_departments(name, clearance_type))"
    )

    # Fetch approvals assigned to this user directly
    assigned = (db.table("clearance_approvals")
                .select(base_select)
                .eq("approver_id", uid)
                .in_("status", ["pending", "approved", "rejected"])
                .execute().data or [])

    # Also fetch unassigned service dept approvals (approver_id is NULL)
    # that are claimable by certain roles
    claimable = []
    if role in ("liaison_officer", "workshop_technician", "trainer", "dept_admin"):
        try:
            null_rows = (db.table("clearance_approvals")
                         .select(base_select)
                         .is_("approver_id", "null")
                         .eq("status", "pending")
                         .execute().data or [])
            hod_dept_id = user.get("department_id")
            for row in null_rows:
                cat = row.get("approver_category") or _infer_category(row)
                if cat in SERVICE_DEPT_CATEGORIES:
                    row["_claimable"] = True
                    claimable.append(row)
                elif cat == "hod_other" and role == "dept_admin":
                    # Show to any dept_admin whose own dept ≠ student's home dept
                    req_inner = row.get("clearance_requests") or {}
                    student_dept = (
                        (req_inner.get("user_profiles") or {}).get("department_id")
                        or req_inner.get("department_id")
                    )
                    if student_dept and student_dept != hod_dept_id:
                        row["_claimable"] = True
                        claimable.append(row)
        except Exception:
            pass

    # Combine and annotate
    seen_ids = set()
    my_approvals = []

    for a in assigned + claimable:
        aid = a.get("id")
        if aid in seen_ids:
            continue
        seen_ids.add(aid)

        req = a.get("clearance_requests") or {}
        cat = a.get("approver_category") or _infer_category(a)
        a["_category"]  = cat
        a["_cat_label"] = CATEGORY_LABELS.get(cat, cat)
        a["_is_stage1"] = cat in STAGE1_CATEGORIES
        a["_is_stage2"] = cat in STAGE2_CATEGORIES
        # Stage 1 approvals are always active (parallel)
        # Stage 2 approvals are active only when request.stage >= 2
        req_stage = req.get("stage", 1)
        if cat in STAGE1_CATEGORIES:
            a["_is_active"] = (req.get("status") not in ("completed", "rejected"))
        else:
            a["_is_active"] = (
                req_stage >= 2
                and req.get("status") not in ("completed", "rejected", "returned")
            )
        a["user_profiles"] = req.get("user_profiles") or {}
        my_approvals.append(a)

    # Filter to only pending items (already approved/rejected shown differently)
    pending   = [a for a in my_approvals if a.get("status") == "pending"]
    completed = [a for a in my_approvals if a.get("status") in ("approved", "rejected")]

    # For dept_admin: split into stage1 (hod_other) and stage2 (hod_home)
    stage1_pending = [a for a in pending if a.get("_is_stage1")]
    stage2_pending = [a for a in pending if a.get("_is_stage2")]

    # For trainers: attach taught units info
    if role == "trainer":
        att_rows = (db.table("attendance")
                    .select("student_id, unit_id, units(name, code)")
                    .eq("trainer_id", uid)
                    .execute().data or [])
        taught = {}
        for r in att_rows:
            sid = r["student_id"]
            u   = r.get("units") or {}
            if sid not in taught:
                taught[sid] = []
            if u.get("code"):
                taught[sid].append(u)
        for a in pending:
            sid = (a.get("clearance_requests") or {}).get("student_id", "")
            a["taught_units"] = taught.get(sid, [])

    # For dept_admin Stage 2: attach trainer approvals so HOD can waive them
    if role == "dept_admin" and stage2_pending:
        for a in stage2_pending:
            req_id = (a.get("clearance_requests") or {}).get("id") or ""
            if not req_id:
                a["trainer_approvals"] = []
                continue
            try:
                t_rows = (db.table("clearance_approvals")
                          .select("id, approver_id, approver_category, status, is_waived")
                          .eq("clearance_request_id", req_id)
                          .eq("approver_category", "trainer")
                          .execute().data or [])
                # Attach trainer name
                t_ids = [r["approver_id"] for r in t_rows if r.get("approver_id")]
                t_map = {}
                if t_ids:
                    t_profiles = (db.table("user_profiles")
                                  .select("id, full_name")
                                  .in_("id", t_ids)
                                  .execute().data or [])
                    t_map = {p["id"]: p.get("full_name", "Trainer") for p in t_profiles}
                for r in t_rows:
                    r["trainer_name"] = t_map.get(r.get("approver_id"), "Trainer")
                a["trainer_approvals"] = t_rows
            except Exception:
                a["trainer_approvals"] = []

    # For home dept HOD: Stage 1 requests in their department with pending
    # trainer approvals — so the HOD can open the trainer waiver page early
    home_stage1_requests = []
    if role == "dept_admin" and user.get("department_id"):
        try:
            reqs = (db.table("clearance_requests")
                    .select("id, status, stage, created_at, "
                            "user_profiles:user_profiles!clearance_requests_student_id_fkey"
                            "(full_name, admission_no)")
                    .eq("department_id", user["department_id"])
                    .eq("status", "in_progress")
                    .eq("stage", 1)
                    .order("created_at", desc=True)
                    .execute().data or [])
            for r in reqs:
                t_rows = (db.table("clearance_approvals")
                          .select("id, status, is_waived")
                          .eq("clearance_request_id", r["id"])
                          .eq("approver_category", "trainer")
                          .execute().data or [])
                total = len(t_rows)
                done  = sum(1 for t in t_rows
                            if t.get("status") == "approved" or t.get("is_waived"))
                required = min(MIN_TRAINERS, total) if total else 0
                if total and done < required:
                    r["_trainers_total"]    = total
                    r["_trainers_done"]     = done
                    r["_trainers_required"] = required
                    home_stage1_requests.append(r)
        except Exception:
            home_stage1_requests = []

    return render_template(
        "clearance/approver_dashboard.html",
        my_approvals=pending,
        completed_approvals=completed,
        stage1_pending=stage1_pending,
        stage2_pending=stage2_pending,
        home_stage1_requests=home_stage1_requests,
        user_role=role,
        CATEGORY_LABELS=CATEGORY_LABELS,
        portal_base=_portal_base_template(role),
    )


# ── Approve a clearance approval ──────────────────────────────────────────────

@clearance_bp.route("/approve/<approval_id>", methods=["POST"])
@login_required
def approve_clearance(approval_id):
    db   = get_service_client()
    user = current_user()
    role = user["role"]
    uid  = user["id"]
    comments = request.form.get("comments", "").strip()

    try:
        approval = (db.table("clearance_approvals")
                    .select("*, clearance_stages(stage_name, approver_role), "
                            "clearance_requests(id, student_id, status, stage, department_id)")
                    .eq("id", approval_id)
                    .single()
                    .execute().data)

        if not approval:
            flash("Approval record not found.", "error")
            return redirect(_approver_back(role))

        req = approval.get("clearance_requests") or {}
        cat = approval.get("approver_category") or _infer_category(approval)

        # Security: must be assigned to this user OR be a claimable record
        if approval.get("approver_id") != uid:
            if cat in SERVICE_DEPT_CATEGORIES:
                pass  # claimable by service dept users
            elif (cat == "hod_other" and role == "dept_admin"
                  and approval.get("approver_id") is None):
                # HOD can claim this only if the student is NOT from their own dept
                if req.get("department_id") == user.get("department_id"):
                    abort(403)
            else:
                abort(403)

        # Stage 2 gating: check stage 1 is complete
        if cat in STAGE2_CATEGORIES:
            req_stage = req.get("stage", 1)
            if req_stage < 2:
                flash("Stage 1 must be fully completed before Stage 2 can be acted on.", "warning")
                return redirect(_approver_back(role))

        # Mark approved
        db.table("clearance_approvals").update({
            "status":      "approved",
            "approver_id": uid,
            "comments":    comments or None,
            "approved_at": datetime.now().isoformat(),
        }).eq("id", approval_id).execute()

        student_id = req.get("student_id")

        if cat in STAGE1_CATEGORIES:
            # Check if Stage 1 is now complete → advance to Stage 2
            _check_stage1_and_advance(db, req["id"])

            if student_id:
                create_notification(
                    user_id=student_id,
                    title=f"Stage Approved: {CATEGORY_LABELS.get(cat, cat)}",
                    message="A clearance approval has been granted. Check your clearance status.",
                    notification_type="success",
                    action_url="/clearance",
                )
        elif cat in STAGE2_CATEGORIES:
            # Check overall completion
            _check_clearance_completion(db, req["id"])

            if student_id:
                create_notification(
                    user_id=student_id,
                    title="HOD Final Clearance Approved",
                    message="Your home department HOD has approved your clearance. Certificate ready!",
                    notification_type="success",
                    action_url="/clearance",
                )

        write_audit_log("approve_clearance", target=f"approval:{approval_id}")
        flash("Clearance approval granted successfully.", "success")

    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(_approver_back(role))


# ── Reject a clearance approval ───────────────────────────────────────────────

@clearance_bp.route("/reject/<approval_id>", methods=["POST"])
@login_required
def reject_clearance(approval_id):
    db   = get_service_client()
    user = current_user()
    role = user["role"]
    uid  = user["id"]
    comments = request.form.get("comments", "").strip()

    if not comments:
        flash("Reason for rejection is required.", "error")
        return redirect(_approver_back(role))

    try:
        approval = (db.table("clearance_approvals")
                    .select("*, clearance_stages(stage_name, approver_role), "
                            "clearance_requests(id, student_id, status, department_id)")
                    .eq("id", approval_id)
                    .single()
                    .execute().data)

        if not approval:
            flash("Approval record not found.", "error")
            return redirect(_approver_back(role))

        req = approval.get("clearance_requests") or {}
        cat = approval.get("approver_category") or _infer_category(approval)

        if approval.get("approver_id") != uid:
            if cat in SERVICE_DEPT_CATEGORIES:
                pass  # claimable by service dept users
            elif (cat == "hod_other" and role == "dept_admin"
                  and approval.get("approver_id") is None):
                if req.get("department_id") == user.get("department_id"):
                    abort(403)
            else:
                abort(403)

        db.table("clearance_approvals").update({
            "status":      "rejected",
            "approver_id": uid,
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
                title=f"Clearance Rejected: {CATEGORY_LABELS.get(cat, cat)}",
                message=f"A clearance approval was rejected. Reason: {comments}",
                notification_type="warning",
                action_url="/clearance",
            )

        write_audit_log("reject_clearance", target=f"approval:{approval_id}")
        flash("Clearance stage rejected.", "warning")

    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(_approver_back(role))


# ── HOD: Return for correction ────────────────────────────────────────────────

@clearance_bp.route("/return-correction/<request_id>", methods=["POST"])
@login_required
def return_for_correction(request_id):
    """
    Stage 2: Home HOD returns the clearance for correction.
    Sets request status to 'returned', stores reason, notifies student.
    """
    db   = get_service_client()
    user = current_user()
    uid  = user["id"]
    reason = request.form.get("reason", "").strip()

    if not reason:
        flash("A reason for return is required.", "error")
        return redirect(_approver_back(user["role"]))

    try:
        cr = (db.table("clearance_requests")
              .select("id, student_id, stage, department_id")
              .eq("id", request_id)
              .single()
              .execute().data)

        if not cr:
            abort(404)

        # Verify this user is the home dept HOD
        home_dept_id = cr.get("department_id")
        hod_check = (db.table("user_profiles")
                     .select("id")
                     .eq("id", uid)
                     .eq("role", "dept_admin")
                     .eq("department_id", home_dept_id)
                     .execute().data or [])
        if not hod_check:
            abort(403)

        if cr.get("stage", 1) < 2:
            flash("Cannot return a clearance that has not reached Stage 2.", "warning")
            return redirect(_approver_back(user["role"]))

        db.table("clearance_requests").update({
            "status":      "returned",
            "return_reason": reason,
            "returned_at": datetime.now().isoformat(),
        }).eq("id", request_id).execute()

        student_id = cr.get("student_id")
        if student_id:
            create_notification(
                user_id=student_id,
                title="Clearance Returned for Correction",
                message=f"Your HOD has returned your clearance. Reason: {reason}",
                notification_type="warning",
                action_url="/clearance",
            )

        write_audit_log("return_clearance", target=f"request:{request_id}")
        flash("Clearance returned for correction.", "warning")

    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(_approver_back(user["role"]))


# ── Student: Resubmit after correction ───────────────────────────────────────

@clearance_bp.route("/resubmit/<request_id>", methods=["POST"])
@login_required
@student_required
def resubmit_clearance(request_id):
    """
    Student marks a 'returned' clearance as corrected and resubmits it.
    Puts the request back to 'in_progress' at Stage 2 and notifies the
    home department HOD(s) to re-review.
    """
    db   = get_service_client()
    user = current_user()

    try:
        cr = (db.table("clearance_requests")
              .select("id, student_id, status, stage, department_id, return_reason")
              .eq("id", request_id)
              .single()
              .execute().data)

        if not cr:
            abort(404)
        if cr.get("student_id") != user["id"]:
            abort(403)
        if cr.get("status") != "returned":
            flash("Only a clearance returned for correction can be resubmitted.", "warning")
            return redirect(url_for("clearance.dashboard"))

        update = {"status": "in_progress"}
        db.table("clearance_requests").update(update).eq("id", request_id).execute()

        # Record resubmission time if the column exists (non-fatal otherwise)
        try:
            db.table("clearance_requests").update(
                {"resubmitted_at": datetime.now().isoformat()}
            ).eq("id", request_id).execute()
        except Exception:
            pass

        # Notify home dept HOD(s) to re-review
        try:
            hods = (db.table("user_profiles")
                    .select("id")
                    .eq("role", "dept_admin")
                    .eq("department_id", cr.get("department_id"))
                    .execute().data or [])
            for hod in hods:
                create_notification(
                    user_id=hod["id"],
                    title="Clearance Resubmitted After Correction",
                    message=(f"{user.get('full_name', 'A trainee')} has corrected and "
                             f"resubmitted their clearance for your final review."),
                    notification_type="info",
                    action_url="/clearance/approver",
                )
        except Exception:
            pass

        write_audit_log("resubmit_clearance", target=f"request:{request_id}")
        flash("Clearance resubmitted for final review.", "success")

    except Exception as e:
        flash(f"Error resubmitting clearance: {e}", "error")

    return redirect(url_for("clearance.dashboard"))


# ── HOD: Waive inactive trainer ───────────────────────────────────────────────

@clearance_bp.route("/waive-trainer/<approval_id>", methods=["POST"])
@login_required
def waive_trainer(approval_id):
    """
    HOD waives an inactive trainer Stage 1 approval record.
    Only home dept HOD (dept_admin) can waive trainers for their students.
    """
    db   = get_service_client()
    user = current_user()
    uid  = user["id"]

    if user["role"] != "dept_admin":
        abort(403)

    try:
        approval = (db.table("clearance_approvals")
                    .select("*, clearance_requests(id, student_id, department_id, stage)")
                    .eq("id", approval_id)
                    .single()
                    .execute().data)

        if not approval:
            abort(404)

        cat = approval.get("approver_category") or _infer_category(approval)
        if cat != "trainer":
            flash("Only trainer approvals can be waived.", "error")
            return redirect(_approver_back(user["role"]))

        req          = approval.get("clearance_requests") or {}
        home_dept_id = req.get("department_id")

        # Verify HOD belongs to this department
        hod_check = (db.table("user_profiles")
                     .select("id")
                     .eq("id", uid)
                     .eq("role", "dept_admin")
                     .eq("department_id", home_dept_id)
                     .execute().data or [])
        if not hod_check:
            abort(403)

        now_iso = datetime.now().isoformat()
        db.table("clearance_approvals").update({
            "is_waived":  True,
            "waived_by":  uid,
            "waived_at":  now_iso,
            "status":     "approved",
            "comments":   "Waived by HOD — trainer inactive",
            "approved_at": now_iso,
        }).eq("id", approval_id).execute()

        # Re-check Stage 1 completion
        _check_stage1_and_advance(db, req["id"])

        write_audit_log("waive_trainer", target=f"approval:{approval_id}")
        flash("Trainer approval waived.", "success")

    except Exception as e:
        flash(f"Error: {e}", "error")

    return redirect(_approver_back(user["role"]))


# ── Certificate (HTML view) ───────────────────────────────────────────────────

@clearance_bp.route("/certificate/<request_id>")
@login_required
def certificate(request_id):
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
        flash("Clearance certificate is only available after all stages are approved.", "warning")
        return redirect(url_for("clearance.dashboard"))

    serial    = cr.get("serial_number") or _serial(cr["id"])
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
        a["_approver"]  = approver_map.get(a.get("approver_id"), {})
        a["_category"]  = _get_category(a)
        a["_cat_label"] = CATEGORY_LABELS.get(_get_category(a), "")

    # Fetch lost items recorded by service dept staff
    approval_ids = [a["id"] for a in approvals]
    lost_items = []
    if approval_ids:
        try:
            lost_items = (db.table("clearance_lost_items")
                            .select("item_name, quantity, notes, "
                                    "clearance_approval_id, added_by, "
                                    "user_profiles:user_profiles!clearance_lost_items_added_by_fkey"
                                    "(full_name)")
                            .in_("clearance_approval_id", approval_ids)
                            .order("created_at")
                            .execute().data or [])
        except Exception:
            lost_items = []

    student = cr.get("user_profiles") or {}

    import os
    base_url   = os.environ.get("APP_BASE_URL", request.host_url.rstrip("/"))
    verify_url = f"{base_url}/clearance/verify/{serial}"

    return render_template(
        "clearance/clearance_certificate.html",
        cr=cr,
        student=student,
        serial=serial,
        verify_url=verify_url,
        approvals=approvals,
        lost_items=lost_items,
        CATEGORY_LABELS=CATEGORY_LABELS,
    )


# ── Certificate PDF download ──────────────────────────────────────────────────

@clearance_bp.route("/certificate/<request_id>/pdf")
@login_required
def certificate_pdf(request_id):
    """Generate and stream the TTTI Clearance Certificate as a PDF."""
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

    approver_ids = [a["approver_id"] for a in approvals if a.get("approver_id")]
    approver_map = {}
    if approver_ids:
        profiles = (db.table("user_profiles")
                    .select("id, full_name, role")
                    .in_("id", approver_ids)
                    .execute().data or [])
        approver_map = {p["id"]: p for p in profiles}

    for a in approvals:
        a["_approver"]  = approver_map.get(a.get("approver_id") or "", {})
        a["_category"]  = _get_category(a)
        a["_cat_label"] = CATEGORY_LABELS.get(_get_category(a), "")

    student = cr.get("user_profiles") or {}

    try:
        import io as _io
        import os as _os
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

        base   = getSampleStyleSheet()
        DARK   = colors.HexColor("#0f2c54")
        MID    = colors.HexColor("#DCE6F4")   # light visible header fill
        HDRTXT = colors.HexColor("#0F2744")   # dark text on light header
        BORDER = colors.HexColor("#e2e8f0")
        LGREY  = colors.HexColor("#f8fafc")
        GTEXT  = colors.HexColor("#15803d")

        ctr14b = ParagraphStyle("c14", parent=base["Normal"], fontSize=14,
                                fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2)
        ctr11b = ParagraphStyle("c11", parent=base["Normal"], fontSize=11,
                                fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2)
        ctr9   = ParagraphStyle("c9",  parent=base["Normal"], fontSize=9,
                                fontName="Helvetica", alignment=TA_CENTER, spaceAfter=1)
        lft10b = ParagraphStyle("l10", parent=base["Normal"], fontSize=10,
                                fontName="Helvetica-Bold")
        lft9b  = ParagraphStyle("l9b", parent=base["Normal"], fontSize=9,
                                fontName="Helvetica-Bold")
        lft9   = ParagraphStyle("l9",  parent=base["Normal"], fontSize=9,
                                fontName="Helvetica")
        tbl_h  = ParagraphStyle("th",  parent=base["Normal"], fontSize=8,
                                fontName="Helvetica-Bold", alignment=TA_CENTER,
                                textColor=HDRTXT)
        tbl_c  = ParagraphStyle("tc",  parent=base["Normal"], fontSize=8,
                                fontName="Helvetica", alignment=TA_CENTER)
        tbl_l  = ParagraphStyle("tl",  parent=base["Normal"], fontSize=8,
                                fontName="Helvetica", alignment=TA_LEFT)

        story = []

        # Header
        ttti_logo_path = _os.path.join(_os.path.dirname(__file__),
                                       "..", "static", "assets", "THIKATTILOGO.jpg")
        ttti_logo_cell = Paragraph("", lft9)
        if _os.path.exists(ttti_logo_path):
            try:
                ttti_logo_cell = RLImage(ttti_logo_path, width=22*mm, height=22*mm)
            except Exception:
                pass

        govt_logo_path = _os.path.join(_os.path.dirname(__file__),
                                       "..", "static", "assets", "KENYACOATOFARMS.png")
        govt_logo_cell = Paragraph("", lft9)
        if _os.path.exists(govt_logo_path):
            try:
                govt_logo_cell = RLImage(govt_logo_path, width=22*mm, height=22*mm)
            except Exception:
                pass

        hdr = Table([[
            govt_logo_cell,
            [Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", ctr14b),
             Paragraph("CLEARANCE CERTIFICATE", ctr11b),
             Paragraph("Academic Management System", ctr9),
             Paragraph(f"Serial No: {serial}", ctr9)],
            ttti_logo_cell,
        ]], colWidths=[24*mm, W - 48*mm, 24*mm])
        hdr.setStyle(TableStyle([
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("ALIGN",         (1,0), (1,0),   "CENTER"),
            ("TOPPADDING",    (0,0), (-1,-1),  0),
            ("BOTTOMPADDING", (0,0), (-1,-1),  0),
        ]))
        story.append(hdr)
        story.append(HRFlowable(width="100%", thickness=2, color=DARK, spaceAfter=6))

        # Student details
        course = cr.get("courses")    or {}
        dept   = cr.get("departments") or {}

        def _info_row(l1, v1, l2, v2):
            t = Table(
                [[Paragraph(l1, lft9b), Paragraph(str(v1), lft9),
                  Paragraph(l2, lft9b), Paragraph(str(v2), lft9)]],
                colWidths=[28*mm, W/2-28*mm, 28*mm, W/2-28*mm])
            t.setStyle(TableStyle([
                ("TOPPADDING",    (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("LINEBELOW",     (1,0), (1,0),   0.5, colors.grey),
                ("LINEBELOW",     (3,0), (3,0),   0.5, colors.grey),
                ("VALIGN",        (0,0), (-1,-1), "BOTTOM"),
            ]))
            return t

        story.append(_info_row("Student Name:", student.get("full_name", "—"),
                               "Admission No:", student.get("admission_no", "—")))
        story.append(_info_row("Course:",       course.get("name", "—"),
                               "Course Code:",  course.get("code", "—")))
        story.append(_info_row("Department:",   dept.get("name", "—"),
                               "Completed:",    (cr.get("completed_at") or "")[:10] or "—"))
        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=5))

        # Approvals table
        story.append(Paragraph("DIGITAL CLEARANCE APPROVALS", lft10b))
        story.append(Spacer(1, 5))

        appr_hdr = [
            Paragraph("#",           tbl_h),
            Paragraph("Category",    tbl_h),
            Paragraph("Approved By", tbl_l),
            Paragraph("Date",        tbl_c),
            Paragraph("Status",      tbl_c),
        ]
        appr_data  = [appr_hdr]
        appr_style = [
            ("BACKGROUND",    (0,0), (-1,0), MID),
            ("TEXTCOLOR",     (0,0), (-1,0), HDRTXT),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("LINEBELOW",     (0,0), (-1,0), 0.8, HDRTXT),
            ("FONTSIZE",      (0,0), (-1,-1), 8),
            ("GRID",          (0,0), (-1,-1), 0.4, BORDER),
            ("TOPPADDING",    (0,0), (-1,-1), 3),
            ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ("LEFTPADDING",   (0,0), (-1,-1), 4),
            ("RIGHTPADDING",  (0,0), (-1,-1), 4),
            ("ALIGN",         (0,0), (-1,-1), "CENTER"),
            ("ALIGN",         (1,0), (2,-1),  "LEFT"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LGREY]),
        ]

        for i, a in enumerate(approvals, 1):
            approver = a.get("_approver") or {}
            status   = a.get("status", "pending")
            cat_lbl  = a.get("_cat_label") or CATEGORY_LABELS.get(_get_category(a), "—")
            appr_nm  = approver.get("full_name", "—") if status == "approved" else "—"
            appr_dt  = (a.get("approved_at") or "")[:10] if status == "approved" else "—"
            waived   = a.get("is_waived")
            if waived:
                status_txt = "Waived"
            elif status == "approved":
                status_txt = "Approved"
            else:
                status_txt = "Pending"
            ri = len(appr_data)
            appr_data.append([
                Paragraph(str(i),       tbl_c),
                Paragraph(cat_lbl,      tbl_l),
                Paragraph(appr_nm,      tbl_l),
                Paragraph(appr_dt,      tbl_c),
                Paragraph(status_txt,   tbl_c),
            ])
            if status == "approved":
                appr_style.append(("TEXTCOLOR", (4,ri), (4,ri), GTEXT))
                appr_style.append(("FONTNAME",  (4,ri), (4,ri), "Helvetica-Bold"))

        appr_tbl = Table(
            appr_data,
            colWidths=[8*mm, 52*mm, W-8*mm-52*mm-28*mm-22*mm, 28*mm, 22*mm],
            repeatRows=1,
        )
        appr_tbl.setStyle(TableStyle(appr_style))
        story += [appr_tbl, Spacer(1, 12)]

        # Lost / Missing Items section
        lost_items = locals().get("lost_items") or []
        # Re-fetch if not already in scope (called from certificate_pdf route)
        if not lost_items:
            try:
                _aid_list = [a["id"] for a in approvals]
                if _aid_list:
                    lost_items = (db.table("clearance_lost_items")
                                    .select("item_name, quantity, notes")
                                    .in_("clearance_approval_id", _aid_list)
                                    .order("created_at")
                                    .execute().data or [])
            except Exception:
                lost_items = []

        if lost_items:
            AMBER = colors.HexColor("#b45309")
            AMBER_BG = colors.HexColor("#fef3c7")
            story.append(HRFlowable(width="100%", thickness=1, color=AMBER, spaceAfter=5))
            story.append(Paragraph("LOST / MISSING ITEMS", ParagraphStyle(
                "amber_hdr", parent=base["Normal"], fontSize=10,
                fontName="Helvetica-Bold", textColor=AMBER)))
            story.append(Spacer(1, 4))

            li_hdr = [
                Paragraph("#",       tbl_h),
                Paragraph("Item",    tbl_h),
                Paragraph("Qty",     tbl_h),
                Paragraph("Notes",   tbl_h),
            ]
            li_data = [li_hdr]
            li_style = [
                ("BACKGROUND",    (0,0), (-1,0), AMBER_BG),
                ("TEXTCOLOR",     (0,0), (-1,0), AMBER),
                ("FONTSIZE",      (0,0), (-1,-1), 8),
                ("GRID",          (0,0), (-1,-1), 0.4, colors.HexColor("#fde68a")),
                ("TOPPADDING",    (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("LEFTPADDING",   (0,0), (-1,-1), 4),
                ("RIGHTPADDING",  (0,0), (-1,-1), 4),
                ("ALIGN",         (0,0), (-1,-1), "CENTER"),
                ("ALIGN",         (1,0), (3,-1),  "LEFT"),
                ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#fffbeb")]),
            ]
            for i, li in enumerate(lost_items, 1):
                li_data.append([
                    Paragraph(str(i),                     tbl_c),
                    Paragraph(li.get("item_name", "—"),   tbl_l),
                    Paragraph(str(li.get("quantity", 1)), tbl_c),
                    Paragraph(li.get("notes") or "—",     tbl_l),
                ])
            li_tbl = Table(li_data, colWidths=[8*mm, 80*mm, 20*mm, W-108*mm], repeatRows=1)
            li_tbl.setStyle(TableStyle(li_style))
            story += [li_tbl, Spacer(1, 4)]
            story.append(Paragraph(
                "The above items were reported lost/missing by the department during clearance. "
                "The trainee is responsible for settlement before issuance of academic documents.",
                ParagraphStyle("li_note", parent=base["Normal"], fontSize=7,
                               textColor=colors.grey, italics=1)))
            story.append(Spacer(1, 10))

        # Manual signature blocks
        story.append(HRFlowable(width="100%", thickness=1, color=DARK, spaceAfter=8))
        story.append(Paragraph("OFFICIAL SIGN-OFF", lft10b))
        story.append(Paragraph(
            "The following officials must sign and stamp this form to complete clearance.",
            lft9))
        story.append(Spacer(1, 8))

        officials = [
            "HOME DEPARTMENT HOD",
            "FINANCE DEPARTMENT",
            "DEAN OF STUDENTS",
            "REGISTRAR",
            "CHIEF PRINCIPAL",
        ]
        line = "_" * 34

        def _sig_block(title):
            half = W / 2 - 5*mm
            rows = [
                [Paragraph(f"<b>{title}</b>", lft9b)],
                [Spacer(1,4)],
                [Paragraph(f"Name:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
                [Spacer(1,3)],
                [Paragraph(f"Signature: {line}", lft9)],
                [Spacer(1,3)],
                [Paragraph(f"Date:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
                [Spacer(1,3)],
                [Paragraph(f"Stamp:&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
            ]
            t = Table(rows, colWidths=[half])
            t.setStyle(TableStyle([
                ("TOPPADDING",    (0,0), (-1,-1), 2),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2),
                ("BOX",           (0,0), (-1,-1), 0.5, BORDER),
                ("BACKGROUND",    (0,0), (0,0),   LGREY),
            ]))
            return t

        half = W / 2 - 5*mm
        for i in range(0, len(officials), 2):
            left  = _sig_block(officials[i])
            right = _sig_block(officials[i+1]) if i+1 < len(officials) else Paragraph("", lft9)
            row_tbl = Table([[left, Spacer(10*mm, 1), right]],
                            colWidths=[half, 10*mm, half])
            row_tbl.setStyle(TableStyle([
                ("VALIGN",        (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",    (0,0), (-1,-1), 0),
                ("BOTTOMPADDING", (0,0), (-1,-1), 8),
            ]))
            story.append(row_tbl)

        # Footer
        import os as _os2
        base_url   = _os2.environ.get("APP_BASE_URL", "")
        verify_url = f"{base_url}/clearance/verify/{serial}" if base_url else f"/clearance/verify/{serial}"
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=3))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%d %B %Y %H:%M')}  "
            f"Serial: {serial}  Verify at: {verify_url}",
            ctr9))

        # Watermark
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
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="Clearance_{safe}_{student.get("admission_no","")}.pdf"'
        )
        return resp

    except ImportError:
        flash("PDF generation requires reportlab. Run: pip install reportlab pillow", "warning")
        return redirect(url_for("clearance.certificate", request_id=request_id))
    except Exception as exc:
        flash(f"Could not generate PDF: {exc}", "danger")
        return redirect(url_for("clearance.certificate", request_id=request_id))


# ── Public serial verification ────────────────────────────────────────────────

@clearance_bp.route("/verify", methods=["GET", "POST"])
@clearance_bp.route("/verify/<path:serial_number>")
def verify(serial_number=None):
    db     = get_service_client()
    result = None
    error  = None

    if request.method == "POST":
        serial_number = request.form.get("serial_number", "").strip().upper()

    if serial_number:
        serial_number = serial_number.upper().strip()
        rows = []

        # Primary: search by serial_number column
        try:
            rows = (db.table("clearance_requests")
                    .select("*, courses(name, code), departments(name), "
                            "user_profiles:user_profiles!clearance_requests_student_id_fkey"
                            "(full_name, admission_no)")
                    .eq("serial_number", serial_number)
                    .execute().data or [])
        except Exception:
            pass

        # Fallback: scan completed requests and derive serial
        if not rows:
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
            except Exception as exc:
                error = str(exc)

        if rows:
            cr = rows[0]
            if cr.get("status") == "completed":
                result = cr
                result["_serial"] = cr.get("serial_number") or _serial(cr["id"])
            else:
                error = f"Clearance with serial {serial_number} exists but is not yet completed."
        else:
            error = f"No completed clearance found with serial number '{serial_number}'."

    return render_template(
        "clearance/verify.html",
        serial_number=serial_number,
        result=result,
        error=error,
    )


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


# ── HOD: Manage trainer waivers page ─────────────────────────────────────────

@clearance_bp.route("/manage-trainers/<request_id>")
@login_required
def manage_trainers(request_id):
    """
    Dedicated page for the home dept HOD to view and waive
    trainer Stage 1 approvals for a specific clearance request.
    """
    db   = get_service_client()
    user = current_user()
    uid  = user["id"]

    if user["role"] != "dept_admin":
        abort(403)

    cr = (db.table("clearance_requests")
          .select("id, student_id, status, stage, department_id, "
                  "courses(name, code), departments(name), "
                  "user_profiles:user_profiles!clearance_requests_student_id_fkey"
                  "(full_name, admission_no)")
          .eq("id", request_id)
          .single()
          .execute().data)

    if not cr:
        abort(404)

    home_dept_id = cr.get("department_id")
    hod_check = (db.table("user_profiles")
                 .select("id")
                 .eq("id", uid)
                 .eq("role", "dept_admin")
                 .eq("department_id", home_dept_id)
                 .execute().data or [])
    if not hod_check:
        abort(403)

    # Fetch all trainer approvals for this request
    t_rows = (db.table("clearance_approvals")
              .select("id, approver_id, approver_category, status, is_waived, "
                      "waived_at, approved_at, comments")
              .eq("clearance_request_id", request_id)
              .eq("approver_category", "trainer")
              .execute().data or [])

    t_ids = [r["approver_id"] for r in t_rows if r.get("approver_id")]
    t_map = {}
    if t_ids:
        t_profiles = (db.table("user_profiles")
                      .select("id, full_name, phone")
                      .in_("id", t_ids)
                      .execute().data or [])
        t_map = {p["id"]: p for p in t_profiles}

    for r in t_rows:
        r["_trainer"] = t_map.get(r.get("approver_id") or "", {})

    approved_count = sum(1 for r in t_rows
                         if r.get("status") == "approved" or r.get("is_waived"))
    required_count = min(MIN_TRAINERS, len(t_rows))

    return render_template(
        "clearance/manage_trainers.html",
        cr=cr,
        trainer_approvals=t_rows,
        approved_count=approved_count,
        required_count=required_count,
        stage1_done=(cr.get("stage", 1) >= 2),
        portal_base=_portal_base_template(user["role"]),
    )
