"""
routes/service_dept.py — Independent Service Department Clearance Portals.

Serves three standalone portals:
  - library_hod              → Institute Library
  - sports_hod               → Games Department
  - service_clearance_officer → General Service Clearance (all svc depts)

Query strategy:
  Primary  — approver_category IN (cats)        [works for all rows, old+new]
  Fallback — clearance_stage_id IN (stage_ids)  [catches any row still missing category]
  Results are merged and deduplicated.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from auth_utils import login_required, current_user
from db import get_service_client

service_dept_bp = Blueprint("service_dept", __name__)

DEPT_CONFIG = {
    "library_hod": {
        "label":         "Institute Library",
        "role_lbl":      "Library Officer",
        "icon":          "fa-book",
        "gradient":      "linear-gradient(160deg, #1e3a8a 0%, #1d4ed8 100%)",
        "accent":        "#1d4ed8",
        "light":         "#dbeafe",
        "cats":          ["svc_library"],
        "approver_roles": ["library_hod"],
    },
    "sports_hod": {
        "label":         "Games Department",
        "role_lbl":      "Games Officer",
        "icon":          "fa-futbol",
        "gradient":      "linear-gradient(160deg, #14532d 0%, #16a34a 100%)",
        "accent":        "#16a34a",
        "light":         "#dcfce7",
        "cats":          ["svc_games"],
        "approver_roles": ["sports_hod"],
    },
    "service_clearance_officer": {
        "label":         "Service Clearance",
        "role_lbl":      "Service Clearance Officer",
        "icon":          "fa-clipboard-check",
        "gradient":      "linear-gradient(160deg, #78350f 0%, #d97706 100%)",
        "accent":        "#d97706",
        "light":         "#fef3c7",
        "cats":          ["svc_library", "svc_ict", "svc_games", "svc_kitchen", "svc_store"],
        "approver_roles": ["library_hod", "sports_hod"],
    },
}

CATEGORY_LABELS = {
    "svc_library":  "Institute Library",
    "svc_ict":      "ICT Department",
    "svc_games":    "Games Department",
    "svc_kitchen":  "Kitchen / Cafeteria",
    "svc_store":    "Store Department",
}

ROLE_POSITION = {
    "library_hod":               "Library HOD",
    "sports_hod":                "Games & Sports HOD",
    "service_clearance_officer": "Service Clearance Officer",
    "finance_officer":           "Finance Officer",
    "registrar":                 "Academic Registrar",
    "deputy_principal":          "Deputy Principal (Academics)",
    "dean_students":             "Dean of Students",
    "environment_hod":           "Environment HOD",
    "dept_admin":                "Head of Department",
    "trainer":                   "Lecturer / Trainer",
    "workshop_technician":       "Workshop Technician",
    "quality_assurance_officer": "Quality Assurance Officer",
    "super_admin":               "System Administrator",
}

_APPROVAL_SEL = ("id, clearance_stage_id, clearance_request_id, "
                 "approver_id, approver_category, status, "
                 "comments, approved_at, created_at, is_waived")


def _require_service_role(user):
    return user["role"] in DEPT_CONFIG


@service_dept_bp.route("/")
@login_required
def dashboard():
    user   = current_user()
    role   = user["role"]

    if not _require_service_role(user):
        flash("Access denied.", "error")
        return redirect(url_for("auth.login"))

    config          = DEPT_CONFIG[role]
    cats            = config["cats"]
    approver_roles  = config["approver_roles"]
    db              = get_service_client()

    # ── Primary query: by approver_category ──────────────────────────────────
    # Covers all rows created by the current clearance initiation code and all
    # rows that have been backfilled.
    primary = (db.table("clearance_approvals")
                 .select(_APPROVAL_SEL)
                 .in_("approver_category", cats)
                 .order("created_at", desc=True)
                 .execute().data or [])

    # ── Fallback query: by clearance_stage_id ────────────────────────────────
    # Catches any rows that still have approver_category NULL (e.g. rows inserted
    # by a very old code path that set clearance_stage_id but not approver_category).
    stage_rows = (db.table("clearance_stages")
                    .select("id, stage_name, approver_role")
                    .in_("approver_role", approver_roles)
                    .execute().data or [])
    stage_ids  = [s["id"] for s in stage_rows]
    stage_meta = {s["id"]: s for s in stage_rows}

    fallback = []
    if stage_ids:
        fallback = (db.table("clearance_approvals")
                      .select(_APPROVAL_SEL)
                      .in_("clearance_stage_id", stage_ids)
                      .is_("approver_category", "null")
                      .order("created_at", desc=True)
                      .execute().data or [])

    # Merge, deduplicate
    seen = set()
    all_approvals = []
    for row in primary + fallback:
        rid = row["id"]
        if rid not in seen:
            seen.add(rid)
            all_approvals.append(row)

    # ── Batch-fetch clearance_requests ────────────────────────────────────────
    req_ids = list({r["clearance_request_id"] for r in all_approvals
                    if r.get("clearance_request_id")})
    req_map = {}
    if req_ids:
        req_rows = (db.table("clearance_requests")
                      .select("id, student_id, status, stage, created_at, department_id")
                      .in_("id", req_ids)
                      .execute().data or [])
        req_map = {r["id"]: r for r in req_rows}

    # ── Batch-fetch student profiles ──────────────────────────────────────────
    student_ids = list({r["student_id"] for r in req_map.values() if r.get("student_id")})
    student_map = {}
    if student_ids:
        sp_rows = (db.table("user_profiles")
                     .select("id, full_name, admission_no, mobile_number, department_id")
                     .in_("id", student_ids)
                     .execute().data or [])
        student_map = {s["id"]: s for s in sp_rows}

    # ── Batch-fetch department names ──────────────────────────────────────────
    dept_ids_set = set()
    for req in req_map.values():
        if req.get("department_id"):
            dept_ids_set.add(req["department_id"])
    for sp in student_map.values():
        if sp.get("department_id"):
            dept_ids_set.add(sp["department_id"])
    dept_map = {}
    if dept_ids_set:
        d_rows = (db.table("departments")
                    .select("id, name")
                    .in_("id", list(dept_ids_set))
                    .execute().data or [])
        dept_map = {d["id"]: d["name"] for d in d_rows}

    # ── Batch-fetch approver profiles ────────────────────────────────────────
    approver_ids = list({r["approver_id"] for r in all_approvals if r.get("approver_id")})
    approver_map = {}
    if approver_ids:
        ap_rows = (db.table("user_profiles")
                     .select("id, full_name, role")
                     .in_("id", approver_ids)
                     .execute().data or [])
        approver_map = {a["id"]: a for a in ap_rows}

    # ── Batch-fetch lost items for all approvals ──────────────────────────────
    approval_ids = [r["id"] for r in all_approvals]
    lost_map = {}
    if approval_ids:
        try:
            li_rows = (db.table("clearance_lost_items")
                         .select("id, clearance_approval_id, item_name, quantity, notes, created_at")
                         .in_("clearance_approval_id", approval_ids)
                         .order("created_at")
                         .execute().data or [])
            for li in li_rows:
                lost_map.setdefault(li["clearance_approval_id"], []).append(li)
        except Exception:
            pass

    # ── Annotate rows ─────────────────────────────────────────────────────────
    rows = []
    for row in all_approvals:
        req = req_map.get(row.get("clearance_request_id") or "") or {}
        sp  = student_map.get(req.get("student_id") or "") or {}
        did = sp.get("department_id") or req.get("department_id")
        stg = stage_meta.get(row.get("clearance_stage_id") or "") or {}
        apr = approver_map.get(row.get("approver_id") or "") or {}

        row["_student"]    = sp
        row["_dept"]       = {"name": dept_map.get(did, "—")} if did else {}
        row["_course"]     = {}
        row["_req_status"] = req.get("status", "")
        row["_stage_name"] = stg.get("stage_name", "")
        row["_cat_label"]  = CATEGORY_LABELS.get(row.get("approver_category") or "", "")
        row["_lost_items"] = lost_map.get(row["id"], [])
        row["_approver"]   = apr   # {full_name, role} of whoever approved/rejected
        rows.append(row)

    # ── Split by status ───────────────────────────────────────────────────────
    pending  = [r for r in rows if r.get("status") == "pending"
                and r.get("_req_status") not in ("completed", "rejected")]
    cleared  = [r for r in rows if r.get("status") == "approved"]
    rejected = [r for r in rows if r.get("status") == "rejected"]

    return render_template(
        "service_dept/dashboard.html",
        config=config,
        pending=pending,
        cleared=cleared,
        rejected=rejected,
        user=user,
        ROLE_POSITION=ROLE_POSITION,
    )


# ── Add a lost item to a clearance approval ───────────────────────────────────

@service_dept_bp.route("/lost-items/add", methods=["POST"])
@login_required
def add_lost_item():
    user = current_user()
    if not _require_service_role(user):
        flash("Access denied.", "error")
        return redirect(url_for("auth.login"))

    approval_id = request.form.get("approval_id", "").strip()
    item_name   = request.form.get("item_name", "").strip()
    notes       = request.form.get("notes", "").strip()
    try:
        quantity = max(1, int(request.form.get("quantity", 1)))
    except (ValueError, TypeError):
        quantity = 1

    if not approval_id or not item_name:
        flash("Item name is required.", "error")
        return redirect(url_for("service_dept.dashboard"))

    db = get_service_client()

    # Verify this approval belongs to a stage this user manages
    approval = (db.table("clearance_approvals")
                  .select("id, approver_category, clearance_stage_id")
                  .eq("id", approval_id)
                  .single()
                  .execute().data)
    if not approval:
        flash("Clearance record not found.", "error")
        return redirect(url_for("service_dept.dashboard"))

    config = DEPT_CONFIG[user["role"]]
    cats   = config["cats"]
    approver_roles = config["approver_roles"]

    # Check via approver_category or via stage
    allowed = False
    if approval.get("approver_category") in cats:
        allowed = True
    else:
        stage_rows = (db.table("clearance_stages")
                        .select("id")
                        .in_("approver_role", approver_roles)
                        .execute().data or [])
        stage_ids = [s["id"] for s in stage_rows]
        if approval.get("clearance_stage_id") in stage_ids:
            allowed = True

    if not allowed:
        flash("You do not manage this clearance record.", "error")
        return redirect(url_for("service_dept.dashboard"))

    db.table("clearance_lost_items").insert({
        "clearance_approval_id": approval_id,
        "item_name":  item_name,
        "quantity":   quantity,
        "notes":      notes or None,
        "added_by":   user["id"],
    }).execute()

    flash(f"Lost item recorded: {item_name} (qty {quantity}).", "success")
    return redirect(url_for("service_dept.dashboard"))


# ── Remove a lost item ────────────────────────────────────────────────────────

@service_dept_bp.route("/lost-items/remove/<item_id>", methods=["POST"])
@login_required
def remove_lost_item(item_id):
    user = current_user()
    if not _require_service_role(user):
        flash("Access denied.", "error")
        return redirect(url_for("auth.login"))

    db = get_service_client()
    db.table("clearance_lost_items").delete().eq("id", item_id).execute()
    flash("Lost item removed.", "success")
    return redirect(url_for("service_dept.dashboard"))
