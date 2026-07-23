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


# ── Trainer: Marks Entry ──────────────────────────────────────────────────────

@api_v1_bp.route("/trainer/marks-entry", methods=["GET"])
@api_role_required("trainer")
def api_trainer_marks_entry():
    from datetime import datetime
    from routes.trainer import _marks_class_unit_data, _load_assessments_and_marks

    db = get_service_client()
    user = current_user()
    cu_rows, class_list = _marks_class_unit_data(db, user)

    class_id = request.args.get("class_id", "")
    unit_id = request.args.get("unit_id", "")
    year = request.args.get("year", datetime.now().year, type=int)
    term = request.args.get("term", 1, type=int)

    units_list = []
    students_list = []
    assessments = []
    marks_map = {}

    if class_id:
        for r in cu_rows:
            if (r.get("classes") or {}).get("id") == class_id:
                u = r.get("units") or {}
                if u.get("id"):
                    units_list.append({"id": u["id"], "code": u.get("code"), "name": u.get("name")})

    if class_id and unit_id:
        raw = (db.table("enrollments")
                 .select("student_id, user_profiles(full_name, admission_no)")
                 .eq("class_id", class_id).execute().data or [])
        students_list = sorted(raw, key=lambda s: (s.get("user_profiles") or {}).get("full_name", ""))
        assessments, marks_map = _load_assessments_and_marks(db, unit_id, class_id, user["id"], year, term)

    return _ok({
        "class_list": class_list,
        "units_list": units_list,
        "students_list": students_list,
        "assessments": assessments,
        "oral_list": [a for a in assessments if a.get("assessment_type") == "Oral"],
        "practical_list": [a for a in assessments if a.get("assessment_type") == "Practical"],
        "theory_list": [a for a in assessments if a.get("assessment_type") == "Theory"],
        "marks_map": marks_map,
        "class_id": class_id,
        "unit_id": unit_id,
        "year": year,
        "term": term,
    })


@api_v1_bp.route("/trainer/marks-entry/save-mark", methods=["POST"])
@api_role_required("trainer")
def api_trainer_save_mark():
    from datetime import datetime
    db = get_service_client()
    user = current_user()
    data = request.get_json(silent=True) or {}
    assessment_id = data.get("assessment_id", "")
    student_id = data.get("student_id", "")
    marks_str = data.get("marks", "")

    if not assessment_id or not student_id:
        return _err("Missing fields.", 400)

    rec = (db.table("formative_assessments")
             .select("trainer_id, max_marks")
             .eq("id", assessment_id).single().execute().data)
    if not rec or rec["trainer_id"] != user["id"]:
        return _err("Access denied.", 403, "forbidden")

    if marks_str == "" or marks_str is None:
        try:
            (db.table("formative_marks").delete()
               .eq("assessment_id", assessment_id)
               .eq("student_id", student_id).execute())
            return jsonify({"ok": True, "success": True, "cleared": True})
        except Exception as e:
            return _err(str(e), 500)

    try:
        marks_val = float(marks_str)
    except (ValueError, TypeError):
        return _err("Marks must be a number.", 400)

    max_m = float(rec.get("max_marks", 100))
    if marks_val < 0:
        return _err("Marks cannot be negative.", 400)
    if marks_val > max_m:
        return _err(f"Cannot exceed {int(max_m)}.", 400)

    try:
        existing = (db.table("formative_marks").select("id")
                      .eq("assessment_id", assessment_id)
                      .eq("student_id", student_id).execute().data or [])
        if existing:
            db.table("formative_marks").update({
                "marks_obtained": marks_val,
                "uploaded_by": user["id"],
                "updated_at": datetime.now().isoformat(),
            }).eq("id", existing[0]["id"]).execute()
        else:
            db.table("formative_marks").insert({
                "assessment_id": assessment_id,
                "student_id": student_id,
                "marks_obtained": marks_val,
                "uploaded_by": user["id"],
            }).execute()
        return jsonify({"ok": True, "success": True})
    except Exception as e:
        return _err(str(e), 500)


@api_v1_bp.route("/trainer/marks-entry/add-assessment", methods=["POST"])
@api_role_required("trainer")
def api_trainer_add_assessment():
    from datetime import datetime
    db = get_service_client()
    user = current_user()
    data = request.get_json(silent=True) or {}

    unit_id = (data.get("unit_id") or "").strip()
    class_id = (data.get("class_id") or "").strip()
    assessment_type = (data.get("assessment_type") or "").strip()
    assessment_name = (data.get("assessment_name") or "").strip()
    max_marks = data.get("max_marks", 100)
    year = int(data.get("year", datetime.now().year))
    term = int(data.get("term", 1))

    if not all([unit_id, class_id, assessment_type, assessment_name]):
        return _err("All fields are required.", 400)
    if assessment_type not in ("Oral", "Practical", "Theory"):
        return _err("Invalid type.", 400)

    dup = (db.table("formative_assessments").select("id")
             .eq("unit_id", unit_id).eq("class_id", class_id)
             .eq("trainer_id", user["id"])
             .eq("assessment_name", assessment_name)
             .eq("year", year).eq("term", term)
             .execute().data or [])
    if dup:
        return _err(f"'{assessment_name}' already exists.", 400)

    try:
        result = db.table("formative_assessments").insert({
            "unit_id": unit_id, "class_id": class_id,
            "trainer_id": user["id"],
            "assessment_type": assessment_type,
            "assessment_name": assessment_name,
            "max_marks": float(max_marks),
            "year": year, "term": term,
        }).execute()
        write_audit_log("add_formative_assessment",
                        target=f"unit:{unit_id},{assessment_type}:{assessment_name}")
        return _ok({"assessment": result.data[0] if result.data else {}})
    except Exception as e:
        return _err(str(e), 500)


# ── Trainer: POE assessments ──────────────────────────────────────────────────

@api_v1_bp.route("/trainer/assessments", methods=["GET"])
@api_role_required("trainer")
def api_trainer_assessments():
    from routes.trainer import _trainer_assigned_unit_ids, _bulk_formative_marks_for_poe

    db = get_service_client()
    assigned_unit_ids = _trainer_assigned_unit_ids(db)

    q = db.table("assessments").select(
        "*, "
        "user_profiles!assessments_student_id_fkey(full_name, admission_no), "
        "reviewer:user_profiles!assessments_reviewed_by_fkey(full_name), "
        "units(name, code), "
        "classes(id, name)"
    ).order("uploaded_at", desc=True)
    if assigned_unit_ids:
        q = q.in_("unit_id", assigned_unit_ids)
    assessments_list = q.execute().data or []
    _bulk_formative_marks_for_poe(db, assessments_list)

    classes_map = {}
    status_counts = {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
    for a in assessments_list:
        status_counts["total"] += 1
        s = a.get("status", "pending")
        if s in status_counts:
            status_counts[s] += 1
        cls = a.get("classes") or {}
        cid = cls.get("id")
        if not cid:
            continue
        if cid not in classes_map:
            classes_map[cid] = {"id": cid, "name": cls.get("name", ""), "units": {}}
        u = a.get("units") or {}
        uid = a.get("unit_id")
        if not uid:
            continue
        if uid not in classes_map[cid]["units"]:
            classes_map[cid]["units"][uid] = {
                "id": uid,
                "name": u.get("name", ""),
                "code": u.get("code", ""),
                "total": 0, "pending": 0, "approved": 0, "rejected": 0,
                "assessments": [],
            }
        bucket = classes_map[cid]["units"][uid]
        bucket["total"] += 1
        bucket[s] = bucket.get(s, 0) + 1
        bucket["assessments"].append(a)

    class_list = []
    for cid, cdata in classes_map.items():
        unit_list = list(cdata["units"].values())
        class_list.append({
            "id": cid,
            "name": cdata["name"],
            "units": sorted(unit_list, key=lambda u: u["name"]),
            "unit_count": len(unit_list),
            "pending": sum(u["pending"] for u in unit_list),
        })
    class_list.sort(key=lambda c: c["name"])
    return _ok({"classes": class_list, "status_counts": status_counts})


@api_v1_bp.route("/trainer/assessments/<assessment_id>/review", methods=["POST"])
@api_role_required("trainer")
def api_trainer_review_assessment(assessment_id):
    from datetime import datetime
    from routes.trainer import _check_unit_access, _rename_script_file

    db = get_service_client()
    user = current_user()
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    review_note = (body.get("review_note") or "").strip()

    if action not in ("approve", "reject"):
        return _err("action must be approve or reject.", 400)

    assessment = (db.table("assessments")
                  .select("id, unit_id, status")
                  .eq("id", assessment_id).limit(1).execute().data or [None])[0]
    if not assessment:
        return _err("Assessment not found.", 404)
    if not _check_unit_access(db, assessment["unit_id"]):
        return _err("Forbidden.", 403, "forbidden")

    new_status = "approved" if action == "approve" else "rejected"
    try:
        db.table("assessments").update({
            "status": new_status,
            "reviewed_by": user["id"],
            "reviewed_at": datetime.now().isoformat(),
            "review_note": review_note or None,
        }).eq("id", assessment_id).execute()
        try:
            _rename_script_file(db, assessment_id, new_status, user.get("full_name", ""))
        except Exception:
            pass
        write_audit_log(f"assessment_{new_status}", target=f"assessment:{assessment_id}")
        return _ok({"status": new_status})
    except Exception as e:
        return _err(str(e), 500)


# ── Trainer: Attendance ───────────────────────────────────────────────────────

@api_v1_bp.route("/trainer/attendance", methods=["GET"])
@api_role_required("trainer")
def api_trainer_attendance_get():
    from datetime import datetime
    db = get_service_client()
    user = current_user()
    dept_id = user.get("department_id")

    cu_rows = (db.table("class_units").select("class_id").eq("trainer_id", user["id"]).execute().data or [])
    class_ids = list({r["class_id"] for r in cu_rows})
    class_list = []
    if class_ids:
        q = db.table("classes").select("id, name").in_("id", class_ids).order("name")
        if dept_id:
            q = q.eq("department_id", dept_id)
        class_list = q.execute().data or []

    class_id = request.args.get("class_id", "")
    unit_id = request.args.get("unit_id", "")
    week = request.args.get("week", 0, type=int)
    lesson = request.args.get("lesson", "")
    year = request.args.get("year", datetime.now().year, type=int)
    term = request.args.get("term", 1, type=int)

    units_list = []
    students_list = []
    attendance_submitted = False
    active_event = None

    if class_id:
        units_list = (db.table("class_units")
                        .select("unit_id, units(id, code, name)")
                        .eq("class_id", class_id)
                        .eq("trainer_id", user["id"])
                        .execute().data or [])
        students_list = (db.table("enrollments")
                           .select("student_id, user_profiles(full_name, admission_no)")
                           .eq("class_id", class_id)
                           .execute().data or [])
        if unit_id and week and lesson:
            existing = (db.table("attendance").select("id", count="exact")
                          .eq("unit_id", unit_id).eq("trainer_id", user["id"])
                          .eq("week", week).eq("lesson", lesson)
                          .eq("year", year).eq("term", term).execute())
            attendance_submitted = (existing.count or 0) > 0
            event_row = (db.table("class_events").select("*")
                           .eq("class_id", class_id).eq("trainer_id", user["id"])
                           .eq("week", week).eq("lesson", lesson)
                           .eq("year", year).eq("term", term).execute().data or [])
            active_event = event_row[0] if event_row else None

    return _ok({
        "class_list": class_list,
        "units_list": [
            {"id": (u.get("units") or {}).get("id") or u.get("unit_id"),
             "code": (u.get("units") or {}).get("code"),
             "name": (u.get("units") or {}).get("name")}
            for u in units_list
        ],
        "students_list": students_list,
        "attendance_submitted": attendance_submitted,
        "active_event": active_event,
        "class_id": class_id,
        "unit_id": unit_id,
        "week": week,
        "lesson": lesson,
        "year": year,
        "term": term,
        "lessons": [
            {"id": "L1", "label": "08:00–10:00"},
            {"id": "L2", "label": "10:15–12:15"},
            {"id": "L3", "label": "12:45–02:45"},
            {"id": "L4", "label": "03:00–05:00"},
        ],
    })


@api_v1_bp.route("/trainer/attendance/submit", methods=["POST"])
@api_role_required("trainer")
def api_trainer_attendance_submit():
    db = get_service_client()
    user = current_user()
    body = request.get_json(silent=True) or {}

    class_id = body.get("class_id", "")
    unit_id = body.get("unit_id", "")
    unit_code = body.get("unit_code", "")
    week = int(body.get("week") or 0)
    lesson = body.get("lesson", "")
    year = int(body.get("year") or date.today().year)
    term = int(body.get("term") or 1)
    statuses = body.get("statuses") or {}

    if not class_id or not unit_id or not week or not lesson:
        return _err("Class, unit, week and lesson are required.", 400)
    if not statuses:
        return _err("No student statuses provided.", 400)

    existing = (db.table("attendance").select("id", count="exact")
                  .eq("unit_id", unit_id).eq("trainer_id", user["id"])
                  .eq("week", week).eq("lesson", lesson)
                  .eq("year", year).eq("term", term).execute())
    if (existing.count or 0) > 0:
        return _err("Attendance already submitted for this session.", 409, "already_submitted")

    try:
        for sid, status in statuses.items():
            st = "present" if status == "present" else "absent"
            db.table("attendance").insert({
                "student_id": sid,
                "unit_id": unit_id,
                "unit_code": unit_code,
                "trainer_id": user["id"],
                "lesson": lesson,
                "week": week,
                "year": year,
                "term": term,
                "status": st,
            }).execute()
        write_audit_log("submit_attendance", target=f"class:{class_id},unit:{unit_id}")
        return _ok({"submitted": True})
    except Exception as e:
        return _err(str(e), 500)


# ── Student dashboard ─────────────────────────────────────────────────────────

@api_v1_bp.route("/student/dashboard", methods=["GET"])
@api_role_required("student")
def api_student_dashboard():
    from datetime import datetime
    from notifications import get_user_notifications

    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    stats = {}
    attendance_data = []
    recent_assessments = []
    overall_pct = 0
    total_attended = 0

    try:
        stats["total"] = db.table("assessments").select("id", count="exact").eq("student_id", student_id).execute().count or 0
        stats["pending"] = db.table("assessments").select("id", count="exact").eq("student_id", student_id).eq("status", "pending").execute().count or 0
        stats["approved"] = db.table("assessments").select("id", count="exact").eq("student_id", student_id).eq("status", "approved").execute().count or 0
        stats["rejected"] = db.table("assessments").select("id", count="exact").eq("student_id", student_id).eq("status", "rejected").execute().count or 0

        raw_attendance = (db.table("attendance")
                         .select("status, attendance_date, units(id, name, code)")
                         .eq("student_id", student_id).execute().data or [])
        unit_map = {}
        for r in raw_attendance:
            u = r.get("units") or {}
            uid = u.get("id")
            if not uid:
                continue
            if uid not in unit_map:
                unit_map[uid] = {
                    "id": uid, "unit_code": u.get("code", ""), "unit_name": u.get("name", ""),
                    "attended": 0, "total_records": 0, "last_update": None,
                }
            unit_map[uid]["total_records"] += 1
            if r.get("status") == "present":
                unit_map[uid]["attended"] += 1
            dt = r.get("attendance_date")
            if dt and (not unit_map[uid]["last_update"] or dt > unit_map[uid]["last_update"]):
                unit_map[uid]["last_update"] = dt
        attendance_data = list(unit_map.values())

        total_records = db.table("attendance").select("id", count="exact").eq("student_id", student_id).execute().count or 0
        total_attended = db.table("attendance").select("id", count="exact").eq("student_id", student_id).eq("status", "present").execute().count or 0
        overall_pct = round((total_attended / total_records * 100), 1) if total_records > 0 else 0
        stats["attendance_total"] = total_records
        stats["attendance_percent"] = overall_pct

        recent_assessments = (db.table("assessments")
                  .select("id, status, assessment_type, uploaded_at, units(name), classes(name)")
                  .eq("student_id", student_id)
                  .order("uploaded_at", desc=True).limit(6).execute().data or [])

        cl = (db.table("clearance_requests").select("status, stage")
                .eq("student_id", student_id).order("created_at", desc=True).limit(1).execute().data or [])
        stats["clearance_status"] = cl[0].get("status", "") if cl else ""
        stats["clearance_stage"] = cl[0].get("stage", 0) if cl else 0

        attachments = (db.table("industrial_attachments")
                      .select("status").eq("student_id", student_id).execute().data or [])
        stats["attachment_active"] = sum(1 for a in attachments if a.get("status") == "active")
        stats["attachment_total"] = len(attachments)
        stats["logbook_entries"] = db.table("digital_logbook").select("id", count="exact").eq("student_id", student_id).execute().count or 0
        try:
            stats["pending_competencies"] = (db.table("competency_tracking")
                               .select("id", count="exact")
                               .eq("student_id", student_id)
                               .eq("competency_status", "NYC").execute().count or 0)
        except Exception:
            stats["pending_competencies"] = 0
    except Exception as e:
        print(f"[api_v1] student dashboard: {e}")
        return _err("Could not load student dashboard.", 500)

    return _ok({
        "current_month": datetime.now().strftime("%B %Y"),
        "student": {
            "full_name": user.get("full_name"),
            "admission_no": user.get("admission_no"),
        },
        "stats": stats,
        "overall_pct": overall_pct,
        "total_attended": total_attended,
        "attendance_data": attendance_data,
        "recent_assessments": recent_assessments,
        "unread_notifications": get_user_notifications(student_id, unread_only=True, limit=3),
    })

# ── Student: attendance / units / marks ───────────────────────────────────────

@api_v1_bp.route("/student/attendance", methods=["GET"])
@api_role_required("student")
def api_student_attendance():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    attendance_list = (db.table("attendance")
                      .select("id, status, attendance_date, week, lesson, term, year, units(name, code)")
                      .eq("student_id", student_id)
                      .order("attendance_date", desc=True)
                      .execute().data or [])
    total = len(attendance_list)
    present = sum(1 for a in attendance_list if a.get("status") == "present")
    percentage = round((present / total * 100), 1) if total else 0
    return _ok({
        "attendance": attendance_list,
        "total": total,
        "present": present,
        "absent": total - present,
        "percentage": percentage,
    })


@api_v1_bp.route("/student/units", methods=["GET"])
@api_role_required("student")
def api_student_units():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    enrollments = (db.table("enrollments")
                  .select("class_id, classes(name)")
                  .eq("student_id", student_id).execute().data or [])
    class_ids = [e["class_id"] for e in enrollments if e.get("class_id")]
    class_units_data = []
    if class_ids:
        class_units_data = (db.table("class_units")
                           .select("class_id, units(name, code, id)")
                           .in_("class_id", class_ids).execute().data or [])
    units_data = []
    seen = set()
    for cu in class_units_data:
        unit = cu.get("units") or {}
        uid = unit.get("id")
        if not uid or uid in seen:
            continue
        seen.add(uid)
        att = (db.table("attendance").select("status")
              .eq("student_id", student_id).eq("unit_id", uid).execute().data or [])
        total = len(att)
        present = sum(1 for a in att if a.get("status") == "present")
        pct = round(present / total * 100, 1) if total else 0
        class_name = ""
        for enr in enrollments:
            if enr.get("class_id") == cu.get("class_id"):
                class_name = (enr.get("classes") or {}).get("name", "")
                break
        units_data.append({
            "id": uid, "code": unit.get("code", ""), "name": unit.get("name", ""),
            "class_name": class_name, "attended": present, "total": total, "pct": pct,
        })
    return _ok({"units": units_data})


@api_v1_bp.route("/student/marks", methods=["GET"])
@api_role_required("student")
def api_student_marks():
    from datetime import datetime
    from collections import OrderedDict

    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    year = request.args.get("year", str(datetime.now().year))
    term = (request.args.get("term") or "").strip()

    profile = (db.table("user_profiles")
                 .select("full_name, admission_no, mobile_number")
                 .eq("id", student_id).limit(1).execute().data or [])
    profile = profile[0] if profile else {}

    enrollment = (db.table("enrollments")
                    .select("class_id, classes(name, departments(name))")
                    .eq("student_id", student_id).limit(1).execute().data or [])
    class_name = dept_name = ""
    class_id = None
    if enrollment:
        class_id = enrollment[0].get("class_id")
        cls = enrollment[0].get("classes") or {}
        dept = cls.get("departments") or {}
        class_name = cls.get("name", "")
        dept_name = dept.get("name", "")

    assessments = []
    if class_id:
        q = (db.table("formative_assessments")
               .select("id, unit_id, assessment_name, assessment_type, max_marks, year, term, "
                       "units(name, code), "
                       "trainer:user_profiles!formative_assessments_trainer_id_fkey(full_name)")
               .eq("class_id", class_id).eq("year", int(year)))
        if term:
            q = q.eq("term", int(term))
        assessments = (q.order("unit_id").order("assessment_type").order("created_at").execute().data or [])

    marks_map = {}
    if assessments:
        a_ids = [a["id"] for a in assessments]
        fm = (db.table("formative_marks").select("assessment_id, marks_obtained")
                .eq("student_id", student_id).in_("assessment_id", a_ids).execute().data or [])
        marks_map = {m["assessment_id"]: m["marks_obtained"] for m in fm}

    by_unit = OrderedDict()
    for a in assessments:
        uid = a["unit_id"]
        unit = a.get("units") or {}
        if uid not in by_unit:
            by_unit[uid] = {"unit": unit, "term": a.get("term"), "assessments": []}
        obt = marks_map.get(a["id"])
        mx = float(a.get("max_marks") or 100)
        if obt is not None:
            pct = round(float(obt) / mx * 100, 1) if mx else 0
            grade = ("M" if pct >= 80 else "P" if pct >= 65 else "C" if pct >= 50 else "NYC")
        else:
            pct = None
            grade = None
        by_unit[uid]["assessments"].append({
            "assessment_name": a.get("assessment_name", ""),
            "assessment_type": (a.get("assessment_type") or "OTHER").upper(),
            "term": a.get("term"),
            "marks_obtained": obt,
            "max_marks": mx,
            "grade": grade,
            "pct": pct,
            "trainer": a.get("trainer"),
        })

    units_data = []
    for uid, data in by_unit.items():
        entered = [a for a in data["assessments"] if a["marks_obtained"] is not None]
        total_obt = round(sum(float(a["marks_obtained"]) for a in entered), 1) if entered else 0
        total_max = round(sum(a["max_marks"] for a in entered), 1) if entered else 0
        pct = round(total_obt / total_max * 100, 1) if total_max else 0
        final = ("M" if pct >= 80 else "P" if pct >= 65 else "C" if pct >= 50 else "NYC") if entered else "—"
        data.update({"total_obt": total_obt, "total_max": total_max, "pct": pct,
                     "final_grade": final, "has_marks": bool(entered)})
        units_data.append(data)

    scored = [u for u in units_data if u["has_marks"]]
    overall = round(sum(u["pct"] for u in scored) / len(scored), 1) if scored else 0
    passed = sum(1 for u in scored if u["final_grade"] in ("M", "P", "C"))

    return _ok({
        "profile": profile,
        "class_name": class_name,
        "dept_name": dept_name,
        "year": year,
        "term": term,
        "units_data": units_data,
        "overall": overall,
        "passed": passed,
        "scored_units": len(scored),
    })
