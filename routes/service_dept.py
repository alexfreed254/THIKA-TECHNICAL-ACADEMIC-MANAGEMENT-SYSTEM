"""
routes/service_dept.py — Independent Service Department Clearance Portals.

Serves three standalone portals:
  - library_hod              → Institute Library
  - sports_hod               → Games Department
  - service_clearance_officer → General Service Clearance (all svc depts)

Super Admin creates the login credentials; users land here after login.
"""

from flask import Blueprint, render_template, redirect, url_for, flash
from auth_utils import login_required, current_user
from db import get_service_client

service_dept_bp = Blueprint("service_dept", __name__)

DEPT_CONFIG = {
    "library_hod": {
        "label":    "Institute Library",
        "role_lbl": "Library Officer",
        "icon":     "fa-book",
        "gradient": "linear-gradient(160deg, #1e3a8a 0%, #1d4ed8 100%)",
        "accent":   "#1d4ed8",
        "light":    "#dbeafe",
        "cats":     ["svc_library"],
    },
    "sports_hod": {
        "label":    "Games Department",
        "role_lbl": "Games Officer",
        "icon":     "fa-futbol",
        "gradient": "linear-gradient(160deg, #14532d 0%, #16a34a 100%)",
        "accent":   "#16a34a",
        "light":    "#dcfce7",
        "cats":     ["svc_games"],
    },
    "service_clearance_officer": {
        "label":    "Service Clearance",
        "role_lbl": "Service Clearance Officer",
        "icon":     "fa-clipboard-check",
        "gradient": "linear-gradient(160deg, #78350f 0%, #d97706 100%)",
        "accent":   "#d97706",
        "light":    "#fef3c7",
        "cats":     ["svc_library", "svc_ict", "svc_games", "svc_kitchen", "svc_store"],
    },
}

CATEGORY_LABELS = {
    "svc_library":  "Institute Library",
    "svc_ict":      "ICT Department",
    "svc_games":    "Games Department",
    "svc_kitchen":  "Kitchen / Cafeteria",
    "svc_store":    "Store Department",
}


def _require_service_role(user):
    return user["role"] in DEPT_CONFIG


@service_dept_bp.route("/")
@login_required
def dashboard():
    import traceback as _tb
    user = current_user()
    role = user["role"]

    if not _require_service_role(user):
        flash("Access denied.", "error")
        return redirect(url_for("auth.login"))

    config = DEPT_CONFIG[role]
    cats   = config["cats"]
    uid    = user["id"]
    db     = get_service_client()

    # Two-step query: approvals first, then enrich
    try:
        assigned = (db.table("clearance_approvals")
                      .select("id, approver_category, status, comments, approved_at, "
                              "created_at, approver_id, is_waived, clearance_request_id")
                      .eq("approver_id", uid)
                      .in_("approver_category", cats)
                      .order("created_at", desc=True)
                      .execute().data or [])
    except Exception:
        print("[service_dept] assigned query error:\n" + _tb.format_exc())
        assigned = []

    try:
        unassigned = (db.table("clearance_approvals")
                        .select("id, approver_category, status, comments, approved_at, "
                                "created_at, approver_id, is_waived, clearance_request_id")
                        .is_("approver_id", "null")
                        .in_("approver_category", cats)
                        .eq("status", "pending")
                        .order("created_at", desc=True)
                        .execute().data or [])
    except Exception:
        print("[service_dept] unassigned query error:\n" + _tb.format_exc())
        unassigned = []

    # Collect request IDs to batch-fetch clearance_requests
    req_ids = list({r["clearance_request_id"] for r in assigned + unassigned
                    if r.get("clearance_request_id")})
    req_map = {}
    student_map = {}
    dept_map = {}

    if req_ids:
        try:
            req_rows = (db.table("clearance_requests")
                          .select("id, student_id, status, stage, created_at, department_id")
                          .in_("id", req_ids)
                          .execute().data or [])
            req_map = {r["id"]: r for r in req_rows}

            student_ids = list({r["student_id"] for r in req_rows if r.get("student_id")})
            dept_ids_set = {r["department_id"] for r in req_rows if r.get("department_id")}

            if student_ids:
                sp_rows = (db.table("user_profiles")
                             .select("id, full_name, admission_no, mobile_number, department_id")
                             .in_("id", student_ids)
                             .execute().data or [])
                student_map = {s["id"]: s for s in sp_rows}
                dept_ids_set.update(s["department_id"] for s in sp_rows if s.get("department_id"))

            if dept_ids_set:
                d_rows = (db.table("departments")
                            .select("id, name")
                            .in_("id", list(dept_ids_set))
                            .execute().data or [])
                dept_map = {d["id"]: d["name"] for d in d_rows}
        except Exception:
            print("[service_dept] enrichment query error:\n" + _tb.format_exc())

    seen = set()
    rows = []
    for row in assigned + unassigned:
        rid = row.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        req = req_map.get(row.get("clearance_request_id") or "") or {}
        sp  = student_map.get(req.get("student_id") or "") or {}
        did = sp.get("department_id") or req.get("department_id")
        row["_student"]    = sp
        row["_dept"]       = {"name": dept_map.get(did, "—")} if did else {}
        row["_course"]     = {}
        row["_req_status"] = req.get("status", "")
        row["_cat_label"]  = CATEGORY_LABELS.get(row.get("approver_category", ""), "")
        rows.append(row)

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
