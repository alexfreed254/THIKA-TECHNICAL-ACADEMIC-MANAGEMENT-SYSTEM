"""
routes/workshop_technician.py — Workshop Technician portal.

Responsibilities:
- Workshop inventory management (CRUD) scoped to their department
- Clearance approvals for trainees in their assigned department
"""

from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from auth_utils import workshop_technician_required, current_user, write_audit_log
from db import get_service_client

workshop_technician_bp = Blueprint("workshop_technician", __name__)

INVENTORY_CATEGORIES = [
    "Power Tools", "Hand Tools", "Safety Equipment",
    "Measuring Instruments", "Electrical Equipment", "Machinery",
    "Computer / ICT Equipment", "Furniture / Fixtures", "Consumables", "Other",
]
CONDITIONS = ["good", "fair", "poor", "damaged"]


# ── Dashboard ─────────────────────────────────────────────────────────────────

@workshop_technician_bp.route("/dashboard")
@workshop_technician_required
def dashboard():
    db      = get_service_client()
    user    = current_user()
    dept_id = user.get("department_id")

    inv_total = inv_low = inv_damaged = 0
    recent_items = []
    dept_name = None

    if dept_id:
        inv_rows = (db.table("workshop_inventory")
                    .select("id, condition, quantity")
                    .eq("department_id", dept_id)
                    .execute().data or [])
        inv_total   = len(inv_rows)
        inv_low     = sum(1 for i in inv_rows if (i.get("quantity") or 0) < 3)
        inv_damaged = sum(1 for i in inv_rows if i.get("condition") in ("poor", "damaged"))

        recent_items = (db.table("workshop_inventory")
                        .select("id, item_name, category, quantity, condition, created_at")
                        .eq("department_id", dept_id)
                        .order("created_at", desc=True)
                        .limit(6)
                        .execute().data or [])

        try:
            d = db.table("departments").select("name").eq("id", dept_id).single().execute().data
            dept_name = d.get("name") if d else None
        except Exception:
            pass

    pending_clearances = 0
    try:
        pending_clearances = len(
            db.table("clearance_approvals")
            .select("id")
            .eq("approver_id", user["id"])
            .eq("status", "pending")
            .execute().data or []
        )
    except Exception:
        pass

    return render_template(
        "workshop_technician/dashboard.html",
        inv_total=inv_total,
        inv_low=inv_low,
        inv_damaged=inv_damaged,
        pending_clearances=pending_clearances,
        recent_items=recent_items,
        dept_name=dept_name,
        INVENTORY_CATEGORIES=INVENTORY_CATEGORIES,
        CONDITIONS=CONDITIONS,
    )


# ── Inventory ─────────────────────────────────────────────────────────────────

@workshop_technician_bp.route("/inventory", methods=["GET", "POST"])
@workshop_technician_required
def inventory():
    db      = get_service_client()
    user    = current_user()
    dept_id = user.get("department_id")

    if not dept_id:
        flash("Your account is not assigned to a department. Contact the administrator.", "error")
        return redirect(url_for("workshop_technician.dashboard"))

    if request.method == "POST":
        action  = request.form.get("action", "add")
        item_id = request.form.get("item_id", "").strip()

        if action == "delete" and item_id:
            db.table("workshop_inventory").delete().eq("id", item_id).eq("department_id", dept_id).execute()
            write_audit_log("delete_inventory_item", target=f"item:{item_id}")
            flash("Item removed from inventory.", "success")
            return redirect(url_for("workshop_technician.inventory"))

        item_name = request.form.get("item_name", "").strip()
        if not item_name:
            flash("Item name is required.", "error")
            return redirect(url_for("workshop_technician.inventory"))

        qty_raw = request.form.get("quantity", "0")
        try:
            qty = max(0, int(qty_raw))
        except (ValueError, TypeError):
            qty = 0

        payload = {
            "item_name":     item_name,
            "category":      request.form.get("category", "").strip() or None,
            "quantity":      qty,
            "condition":     request.form.get("condition", "good"),
            "serial_number": request.form.get("serial_number", "").strip() or None,
            "description":   request.form.get("description", "").strip() or None,
            "location":      request.form.get("location", "").strip() or None,
            "last_serviced": request.form.get("last_serviced") or None,
            "notes":         request.form.get("notes", "").strip() or None,
        }

        if action == "add":
            payload["department_id"] = dept_id
            payload["created_by"]    = user["id"]
            db.table("workshop_inventory").insert(payload).execute()
            write_audit_log("add_inventory_item", target=f"item:{item_name}")
            flash(f'"{item_name}" added to inventory.', "success")

        elif action == "edit" and item_id:
            payload["updated_at"] = datetime.utcnow().isoformat() + "Z"
            db.table("workshop_inventory").update(payload).eq("id", item_id).eq("department_id", dept_id).execute()
            write_audit_log("edit_inventory_item", target=f"item:{item_id}")
            flash("Item updated.", "success")

        return redirect(url_for("workshop_technician.inventory"))

    # ── GET ──────────────────────────────────────────────────────────────────
    search     = request.args.get("q", "").strip()
    cat_filter = request.args.get("category", "").strip()
    cond_filter = request.args.get("condition", "").strip()

    query = db.table("workshop_inventory").select("*").eq("department_id", dept_id)
    if cat_filter:
        query = query.eq("category", cat_filter)
    if cond_filter:
        query = query.eq("condition", cond_filter)
    items = query.order("item_name").execute().data or []

    if search:
        sl = search.lower()
        items = [i for i in items if
                 sl in (i.get("item_name") or "").lower()
                 or sl in (i.get("serial_number") or "").lower()
                 or sl in (i.get("description") or "").lower()
                 or sl in (i.get("location") or "").lower()]

    all_cats = sorted({i.get("category") for i in
                       (db.table("workshop_inventory").select("category")
                        .eq("department_id", dept_id).execute().data or [])
                       if i.get("category")})

    return render_template(
        "workshop_technician/inventory.html",
        items=items,
        search=search,
        cat_filter=cat_filter,
        cond_filter=cond_filter,
        all_cats=all_cats,
        INVENTORY_CATEGORIES=INVENTORY_CATEGORIES,
        CONDITIONS=CONDITIONS,
    )


# ── Clearances ────────────────────────────────────────────────────────────────

@workshop_technician_bp.route("/clearances")
@workshop_technician_required
def clearances():
    db   = get_service_client()
    user = current_user()

    status_filter = request.args.get("status", "").strip()

    query = (db.table("clearance_approvals")
             .select("*, "
                     "clearance_requests(id, status, department_id, initiated_at, "
                     "  user_profiles:user_profiles!clearance_requests_student_id_fkey"
                     "  (full_name, admission_no)), "
                     "clearance_stages(stage_name, approver_role, stage_order, "
                     "  clearance_departments(name, clearance_type))")
             .eq("approver_id", user["id"]))

    if status_filter:
        query = query.eq("status", status_filter)

    approvals = query.order("created_at", desc=True).execute().data or []

    cnt_pending  = sum(1 for a in approvals if a.get("status") == "pending")
    cnt_approved = sum(1 for a in approvals if a.get("status") == "approved")
    cnt_rejected = sum(1 for a in approvals if a.get("status") == "rejected")

    return render_template(
        "workshop_technician/clearances.html",
        approvals=approvals,
        status_filter=status_filter,
        cnt_pending=cnt_pending,
        cnt_approved=cnt_approved,
        cnt_rejected=cnt_rejected,
    )
