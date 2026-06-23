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

from flask import Blueprint, render_template, redirect, url_for, flash
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

    # ── Annotate rows ─────────────────────────────────────────────────────────
    rows = []
    for row in all_approvals:
        req = req_map.get(row.get("clearance_request_id") or "") or {}
        sp  = student_map.get(req.get("student_id") or "") or {}
        did = sp.get("department_id") or req.get("department_id")
        stg = stage_meta.get(row.get("clearance_stage_id") or "") or {}

        row["_student"]    = sp
        row["_dept"]       = {"name": dept_map.get(did, "—")} if did else {}
        row["_req_status"] = req.get("status", "")
        row["_stage_name"] = stg.get("stage_name", "")
        row["_cat_label"]  = CATEGORY_LABELS.get(row.get("approver_category") or "", "")
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
    )
