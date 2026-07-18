"""
Summative Competence Assessments
Enter competence per unit per trainee (proficient / competent /
not yet competent / exempt) and generate graduation lists.
"""

from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, abort,
)
from functools import wraps
from datetime import datetime
from db import get_service_client
from auth_utils import current_user, login_required

summative_bp = Blueprint("summative", __name__, url_prefix="/summative")

COMPETENCE_LEVELS = (
    ("proficient", "Proficient"),
    ("competent", "Competent"),
    ("not_yet_competent", "Not Yet Competent"),
    ("exempt", "Exempt"),
)
COMPETENCE_KEYS = {k for k, _ in COMPETENCE_LEVELS}
PASSING = frozenset({"proficient", "competent", "exempt"})

PORTAL_BASE = {
    "trainer":     "trainer/base.html",
    "dept_admin":  "dept_admin/base.html",
    "super_admin": "super_admin/base.html",
}


def _portal(role: str) -> str:
    return PORTAL_BASE.get(role, "trainer/base.html")


def staff_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or user.get("role") not in ("trainer", "dept_admin", "super_admin"):
            flash("Access denied.", "error")
            abort(403)
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or user.get("role") not in ("dept_admin", "super_admin"):
            flash("Access denied. Graduation lists are for admins.", "error")
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _trainer_class_units(db, user):
    return (db.table("class_units")
              .select("class_id, unit_id, units(id,code,name), classes(id,name)")
              .eq("trainer_id", user["id"])
              .execute().data or [])


def _dept_class_units(db, dept_id):
    classes = (db.table("classes")
                 .select("id, name")
                 .eq("department_id", dept_id)
                 .order("name")
                 .execute().data or [])
    class_ids = [c["id"] for c in classes]
    if not class_ids:
        return [], classes
    cu = (db.table("class_units")
            .select("class_id, unit_id, units(id,code,name), classes(id,name)")
            .in_("class_id", class_ids)
            .execute().data or [])
    return cu, classes


def _all_class_units(db):
    classes = (db.table("classes")
                 .select("id, name, department_id")
                 .order("name")
                 .execute().data or [])
    cu = (db.table("class_units")
            .select("class_id, unit_id, units(id,code,name), classes(id,name)")
            .execute().data or [])
    return cu, classes


def _scope_data(db, user):
    role = user.get("role")
    if role == "super_admin":
        return _all_class_units(db)
    if role == "dept_admin":
        dept_id = user.get("department_id")
        if not dept_id:
            return [], []
        return _dept_class_units(db, dept_id)
    cu = _trainer_class_units(db, user)
    class_map = {}
    for r in cu:
        c = r.get("classes") or {}
        if c.get("id"):
            class_map[c["id"]] = c["name"]
    classes = sorted([{"id": k, "name": v} for k, v in class_map.items()],
                     key=lambda x: x["name"])
    return cu, classes


def _units_for_class(cu_rows, class_id):
    seen = {}
    for r in cu_rows:
        if (r.get("classes") or {}).get("id") != class_id and r.get("class_id") != class_id:
            continue
        u = r.get("units") or {}
        uid = u.get("id") or r.get("unit_id")
        if uid and uid not in seen:
            seen[uid] = {
                "id": uid,
                "code": u.get("code", ""),
                "name": u.get("name", ""),
            }
    return sorted(seen.values(), key=lambda x: (x["code"] or x["name"]))


# ── Entry grid ────────────────────────────────────────────────────────────────

@summative_bp.route("/")
@staff_required
def index():
    db   = get_service_client()
    user = current_user()
    cu_rows, class_list = _scope_data(db, user)

    class_id = request.args.get("class_id", "")
    unit_id  = request.args.get("unit_id", "")
    year     = request.args.get("year", datetime.now().year, type=int)
    term     = request.args.get("term", type=int)

    units_list    = _units_for_class(cu_rows, class_id) if class_id else []
    students_list = []
    competence_map = {}

    if class_id:
        raw = (db.table("enrollments")
                 .select("student_id, user_profiles(id, full_name, admission_no)")
                 .eq("class_id", class_id)
                 .execute().data or [])
        students_list = sorted(
            raw,
            key=lambda s: (s.get("user_profiles") or {}).get("full_name", ""),
        )

    if class_id and unit_id:
        q = (db.table("summative_competences")
               .select("id, student_id, competence, remarks, assessment_date, year, term")
               .eq("class_id", class_id)
               .eq("unit_id", unit_id))
        if year:
            q = q.eq("year", year)
        rows = q.execute().data or []
        competence_map = {r["student_id"]: r for r in rows}

    # Summary counts for selected unit
    summary = {k: 0 for k, _ in COMPETENCE_LEVELS}
    for r in competence_map.values():
        c = r.get("competence")
        if c in summary:
            summary[c] += 1

    return render_template(
        "summative/entry.html",
        portal_base=_portal(user.get("role")),
        class_list=class_list,
        units_list=units_list,
        students_list=students_list,
        competence_map=competence_map,
        competence_levels=COMPETENCE_LEVELS,
        summary=summary,
        class_id=class_id,
        unit_id=unit_id,
        year=year,
        term=term or "",
        can_edit=True,
    )


@summative_bp.route("/save", methods=["POST"])
@staff_required
def save_competence():
    """AJAX — upsert one trainee competence for a unit."""
    db   = get_service_client()
    user = current_user()
    data = request.get_json() or {}

    student_id = (data.get("student_id") or "").strip()
    unit_id    = (data.get("unit_id") or "").strip()
    class_id   = (data.get("class_id") or "").strip()
    competence = (data.get("competence") or "").strip()
    remarks    = (data.get("remarks") or "").strip() or None
    year       = data.get("year") or datetime.now().year
    term       = data.get("term") or None

    if not all([student_id, unit_id, class_id, competence]):
        return jsonify({"success": False, "message": "Missing required fields"}), 400
    if competence not in COMPETENCE_KEYS:
        return jsonify({"success": False, "message": "Invalid competence level"}), 400

    # Scope check for trainers — must be assigned to this class/unit
    if user.get("role") == "trainer":
        assigned = (db.table("class_units")
                      .select("id")
                      .eq("trainer_id", user["id"])
                      .eq("class_id", class_id)
                      .eq("unit_id", unit_id)
                      .limit(1)
                      .execute().data or [])
        if not assigned:
            return jsonify({"success": False, "message": "Not assigned to this unit"}), 403

    try:
        year = int(year)
    except (TypeError, ValueError):
        year = datetime.now().year
    try:
        term = int(term) if term not in (None, "", "null") else None
    except (TypeError, ValueError):
        term = None

    # Resolve department from class
    cls = (db.table("classes")
             .select("department_id")
             .eq("id", class_id)
             .limit(1)
             .execute().data or [None])[0]
    department_id = (cls or {}).get("department_id")

    payload = {
        "student_id": student_id,
        "unit_id": unit_id,
        "class_id": class_id,
        "department_id": department_id,
        "competence": competence,
        "assessed_by": user["id"],
        "assessment_date": datetime.now().date().isoformat(),
        "year": year,
        "term": term,
        "remarks": remarks,
    }

    try:
        existing = (db.table("summative_competences")
                      .select("id")
                      .eq("student_id", student_id)
                      .eq("unit_id", unit_id)
                      .eq("class_id", class_id)
                      .limit(1)
                      .execute().data or [])
        if existing:
            db.table("summative_competences").update(payload).eq("id", existing[0]["id"]).execute()
        else:
            db.table("summative_competences").insert(payload).execute()
        return jsonify({"success": True, "competence": competence})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ── Graduation list ───────────────────────────────────────────────────────────

@summative_bp.route("/graduation-list")
@admin_required
def graduation_list():
    """
    Per-class graduation eligibility: all course units must be
    proficient / competent / exempt (not 'not_yet_competent' or missing).
    """
    db   = get_service_client()
    user = current_user()
    _, class_list = _scope_data(db, user)

    class_id = request.args.get("class_id", "")
    year     = request.args.get("year", datetime.now().year, type=int)

    units = []
    rows  = []
    class_name = ""
    stats = {"eligible": 0, "not_eligible": 0, "total": 0}

    if class_id:
        cls = (db.table("classes")
                 .select("id, name, course_id, department_id")
                 .eq("id", class_id)
                 .limit(1)
                 .execute().data or [None])[0]
        if not cls:
            flash("Class not found.", "error")
            return redirect(url_for("summative.graduation_list"))

        class_name = cls.get("name", "")
        course_id  = cls.get("course_id")

        # Units for this class (class_units), fall back to course units
        cu = (db.table("class_units")
                .select("unit_id, units(id, code, name)")
                .eq("class_id", class_id)
                .execute().data or [])
        unit_map = {}
        for r in cu:
            u = r.get("units") or {}
            uid = u.get("id") or r.get("unit_id")
            if uid:
                unit_map[uid] = {"id": uid, "code": u.get("code", ""), "name": u.get("name", "")}

        if not unit_map and course_id:
            course_units = (db.table("units")
                              .select("id, code, name")
                              .eq("course_id", course_id)
                              .order("code")
                              .execute().data or [])
            for u in course_units:
                unit_map[u["id"]] = u

        units = sorted(unit_map.values(), key=lambda x: (x.get("code") or x.get("name") or ""))

        enrollments = (db.table("enrollments")
                         .select("student_id, user_profiles(id, full_name, admission_no)")
                         .eq("class_id", class_id)
                         .execute().data or [])
        students = sorted(
            enrollments,
            key=lambda s: (s.get("user_profiles") or {}).get("full_name", ""),
        )

        competence_rows = (db.table("summative_competences")
                             .select("student_id, unit_id, competence")
                             .eq("class_id", class_id)
                             .execute().data or [])
        # student -> unit -> competence
        cmap = {}
        for r in competence_rows:
            cmap.setdefault(r["student_id"], {})[r["unit_id"]] = r["competence"]

        for enr in students:
            profile = enr.get("user_profiles") or {}
            sid = enr.get("student_id") or profile.get("id")
            unit_results = {}
            all_met = True
            missing = 0
            nyc = 0
            for u in units:
                comp = (cmap.get(sid) or {}).get(u["id"])
                unit_results[u["id"]] = comp
                if not comp:
                    all_met = False
                    missing += 1
                elif comp not in PASSING:
                    all_met = False
                    nyc += 1

            eligible = all_met and len(units) > 0
            if eligible:
                stats["eligible"] += 1
            else:
                stats["not_eligible"] += 1
            stats["total"] += 1

            rows.append({
                "student_id": sid,
                "full_name": profile.get("full_name", "—"),
                "admission_no": profile.get("admission_no", "—"),
                "unit_results": unit_results,
                "eligible": eligible,
                "missing": missing,
                "nyc": nyc,
            })

    return render_template(
        "summative/graduation_list.html",
        portal_base=_portal(user.get("role")),
        class_list=class_list,
        class_id=class_id,
        class_name=class_name,
        year=year,
        units=units,
        rows=rows,
        stats=stats,
        competence_levels=COMPETENCE_LEVELS,
    )


@summative_bp.route("/api/units/<class_id>")
@staff_required
def api_units(class_id):
    db   = get_service_client()
    user = current_user()
    cu_rows, _ = _scope_data(db, user)
    units = _units_for_class(cu_rows, class_id)
    return jsonify(units)
