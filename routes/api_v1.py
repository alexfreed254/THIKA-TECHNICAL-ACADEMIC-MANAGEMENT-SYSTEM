"""
routes/api_v1.py — JSON API for the separated React + Vite frontend.

Keeps existing Jinja portals working. Does not replace HTML routes.
Auth still uses the Flask session cookie (credentials: include from SPA).
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import wraps

from flask import Blueprint, jsonify, request, session
from auth_utils import (
    SESSION_USER, SESSION_ACCESS, SESSION_REFRESH,
    authenticate_staff, authenticate_student, current_user,
    is_authenticated, write_audit_log,
)
from db import get_service_client

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")

ROLE_HOME = {
    "super_admin": "/super-admin",
    "dept_admin": "/dept-admin",
    "trainer": "/trainer",
    "student": "/student",
    "examination_officer": "/examination-officer",
    "industry_mentor": "/industry-mentor",
    "internal_verifier": "/internal-verifier",
    "liaison_officer": "/liaison-officer",
    "cdacc_verifier": "/cdacc-verifier",
    "workshop_technician": "/workshop-technician",
    "registrar": "/admin-oversight/registrar",
    "deputy_principal": "/admin-oversight/deputy-principal",
    "quality_assurance_officer": "/admin-oversight/quality-assurance",
    "library_hod": "/service-dept",
    "sports_hod": "/service-dept",
    "service_clearance_officer": "/service-dept",
    "environment_hod": "/clearance/approver",
    "dean_students": "/clearance/approver",
    "finance_officer": "/clearance/approver",
}


def _public_user(user: dict | None) -> dict | None:
    if not user:
        return None
    return {
        "id": user.get("id"),
        "full_name": user.get("full_name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "admission_no": user.get("admission_no"),
        "department_id": user.get("department_id"),
        "must_change_password": bool(user.get("must_change_password")),
        "home_path": ROLE_HOME.get(user.get("role") or "", "/auth/profile"),
    }


def _ok(data=None, **extra):
    payload = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return jsonify(payload)


def _err(message: str, status: int = 400, code: str | None = None):
    body = {"ok": False, "error": message}
    if code:
        body["code"] = code
    return jsonify(body), status


def api_login_required(f):
    """JSON 401 instead of HTML redirect — for SPA clients."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return _err("Not authenticated.", 401, "unauthorized")
        return f(*args, **kwargs)
    return decorated


def api_role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not is_authenticated():
                return _err("Not authenticated.", 401, "unauthorized")
            user = current_user()
            if not user or user.get("role") not in roles:
                return _err("Forbidden for this role.", 403, "forbidden")
            return f(*args, **kwargs)
        return decorated
    return decorator


@api_v1_bp.route("/auth/login", methods=["POST"])
def api_login():
    body = request.get_json(silent=True) or {}
    login_type = (body.get("login_type") or "staff").strip().lower()

    if login_type == "staff":
        email = (body.get("email") or "").strip()
        password = body.get("password") or ""
        if not email or not password:
            return _err("Email and password are required.", 400)
        profile = authenticate_staff(email, password)
        if not profile:
            return _err("Invalid email or password.", 401, "invalid_credentials")
        sb_session = profile.pop("_session", None)
        if not sb_session:
            return _err("Authentication session could not be established.", 500)
        session[SESSION_USER] = profile
        session[SESSION_ACCESS] = sb_session.access_token
        session[SESSION_REFRESH] = sb_session.refresh_token
        write_audit_log("login", target=f"user:{profile['id']}")
        return _ok({"user": _public_user(profile)})

    if login_type == "student":
        admission_no = (body.get("admission_no") or "").strip()
        password = body.get("password") or ""
        if not admission_no or not password:
            return _err("Admission number and password are required.", 400)
        profile = authenticate_student(admission_no, password)
        if not profile:
            return _err("Invalid admission number or password.", 401, "invalid_credentials")
        session[SESSION_USER] = profile
        write_audit_log("login", target=f"student:{profile['id']}")
        return _ok({"user": _public_user(profile)})

    return _err("login_type must be 'staff' or 'student'.", 400)


@api_v1_bp.route("/auth/logout", methods=["POST"])
def api_logout():
    user = current_user()
    if user:
        write_audit_log("logout", target=f"user:{user.get('id')}")
    session.clear()
    return _ok({"logged_out": True})


@api_v1_bp.route("/auth/me", methods=["GET"])
def api_me():
    user = current_user()
    if not user:
        return _err("Not authenticated.", 401, "unauthorized")
    return _ok({"user": _public_user(user)})


@api_v1_bp.route("/notifications/recent", methods=["GET"])
@api_login_required
def api_notifications_recent():
    from notifications import get_user_notifications, get_unread_count
    user = current_user()
    limit = min(int(request.args.get("limit", 10)), 30)
    items = get_user_notifications(user["id"], limit=limit)
    return _ok({
        "notifications": items,
        "unread_count": get_unread_count(user["id"]),
    })


@api_v1_bp.route("/notifications/count", methods=["GET"])
@api_login_required
def api_notifications_count():
    from notifications import get_unread_count
    user = current_user()
    return _ok({"count": get_unread_count(user["id"])})


@api_v1_bp.route("/trainer/dashboard", methods=["GET"])
@api_role_required("trainer")
def api_trainer_dashboard():
    from routes.trainer import _trainer_assigned_unit_ids
    from stats_utils import count_in, count_table, exact_count

    db = get_service_client()
    user = current_user()
    stats = {
        "total": 0, "pending": 0, "approved": 0, "rejected": 0,
        "trips_uploaded": 0, "clearance_pending": 0, "summative_nyc": 0,
    }
    pending_assessments = []
    units_list = []
    att_unit_labels = att_unit_present = att_unit_absent = []
    assess_unit_labels = assess_unit_pending = assess_unit_approved = assess_unit_rejected = []
    trend_labels = trend_present = trend_absent = []

    try:
        assigned_unit_ids = _trainer_assigned_unit_ids(db)
        if assigned_unit_ids:
            stats["total"] = count_in(db, "assessments", "unit_id", assigned_unit_ids)
            stats["pending"] = count_in(db, "assessments", "unit_id", assigned_unit_ids, status="pending")
            stats["approved"] = count_in(db, "assessments", "unit_id", assigned_unit_ids, status="approved")
            stats["rejected"] = count_in(db, "assessments", "unit_id", assigned_unit_ids, status="rejected")

        try:
            stats["trips_uploaded"] = count_table(db, "academic_trips", uploaded_by=user["id"])
        except Exception:
            stats["trips_uploaded"] = 0
        try:
            stats["clearance_pending"] = exact_count(
                db.table("clearance_approvals").select("id", count="exact")
                .eq("approver_id", user["id"]).eq("status", "pending")
            )
        except Exception:
            stats["clearance_pending"] = 0

        if assigned_unit_ids:
            pending_assessments = (db.table("assessments")
                .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name), classes(name)")
                .eq("status", "pending")
                .in_("unit_id", assigned_unit_ids)
                .order("uploaded_at", desc=True)
                .limit(15).execute().data or [])
            units_list = (db.table("units").select("id, code, name")
                          .in_("id", assigned_unit_ids).order("name").execute().data or [])

            att_rows = (db.table("attendance")
                        .select("status, units!inner(name)")
                        .in_("unit_id", assigned_unit_ids)
                        .execute().data or [])
            att_map = {}
            for row in att_rows:
                uname = (row.get("units") or {}).get("name", "Unknown")
                b = att_map.setdefault(uname, {"present": 0, "absent": 0})
                if row.get("status") == "present":
                    b["present"] += 1
                else:
                    b["absent"] += 1
            att_unit_labels = list(att_map.keys())
            att_unit_present = [att_map[u]["present"] for u in att_unit_labels]
            att_unit_absent = [att_map[u]["absent"] for u in att_unit_labels]

            for i in range(6, -1, -1):
                day = (date.today() - timedelta(days=i)).isoformat()
                trend_labels.append(day[5:])
                present_n = total_n = 0
                for ci in range(0, len(assigned_unit_ids), 100):
                    chunk = assigned_unit_ids[ci:ci + 100]
                    present_n += exact_count(
                        db.table("attendance").select("id", count="exact")
                        .in_("unit_id", chunk).eq("attendance_date", day).eq("status", "present")
                    )
                    total_n += exact_count(
                        db.table("attendance").select("id", count="exact")
                        .in_("unit_id", chunk).eq("attendance_date", day)
                    )
                trend_present.append(present_n)
                trend_absent.append(max(0, total_n - present_n))

            a_rows = (db.table("assessments")
                      .select("status, units!inner(name)")
                      .in_("unit_id", assigned_unit_ids)
                      .execute().data or [])
            a_map = {}
            for row in a_rows:
                uname = (row.get("units") or {}).get("name", "Unknown")
                b = a_map.setdefault(uname, {"pending": 0, "approved": 0, "rejected": 0})
                s = row.get("status", "pending")
                b[s] = b.get(s, 0) + 1
            assess_unit_labels = list(a_map.keys())
            assess_unit_pending = [a_map[u]["pending"] for u in assess_unit_labels]
            assess_unit_approved = [a_map[u]["approved"] for u in assess_unit_labels]
            assess_unit_rejected = [a_map[u]["rejected"] for u in assess_unit_labels]
        else:
            for i in range(6, -1, -1):
                day = (date.today() - timedelta(days=i)).isoformat()
                trend_labels.append(day[5:])
                trend_present.append(0)
                trend_absent.append(0)
    except Exception as exc:
        print(f"[api_v1] trainer dashboard error: {exc}")
        return _err("Could not load trainer dashboard.", 500)

    month_label = date.today().strftime("%B %Y")
    return _ok({
        "current_month": month_label,
        "stats": stats,
        "pending_assessments": pending_assessments,
        "units_list": units_list,
        "analytics": {
            "att_unit_labels": att_unit_labels,
            "att_unit_present": att_unit_present,
            "att_unit_absent": att_unit_absent,
            "assess_unit_labels": assess_unit_labels,
            "assess_unit_pending": assess_unit_pending,
            "assess_unit_approved": assess_unit_approved,
            "assess_unit_rejected": assess_unit_rejected,
            "trend_labels": trend_labels,
            "trend_present": trend_present,
            "trend_absent": trend_absent,
        },
    })
