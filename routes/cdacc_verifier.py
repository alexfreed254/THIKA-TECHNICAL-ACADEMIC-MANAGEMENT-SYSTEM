"""
routes/cdacc_verifier.py — CDACC External Verifier blueprint.
View assessment evidence, verify assessment records, review competency docs,
generate verification reports.
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from auth_utils import login_required, cdacc_verifier_required, current_user, write_audit_log
from db import get_service_client
from datetime import datetime

cdacc_verifier_bp = Blueprint("cdacc_verifier", __name__)


@cdacc_verifier_bp.route("/")
@cdacc_verifier_bp.route("/dashboard")
@login_required
@cdacc_verifier_required
def dashboard():
    db = get_service_client()
    user = current_user()
    stats = {}
    pending_assessments = []
    recent_verified = []

    try:
        stats["total"]    = db.table("assessments").select("id", count="exact").execute().count or 0
        stats["pending"]  = db.table("assessments").select("id", count="exact").eq("status", "pending").execute().count or 0
        stats["approved"] = db.table("assessments").select("id", count="exact").eq("status", "approved").execute().count or 0
        stats["rejected"] = db.table("assessments").select("id", count="exact").eq("status", "rejected").execute().count or 0

        pending_assessments = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no, departments(name)), units(name, code), classes(name)")
            .eq("status", "pending")
            .order("uploaded_at", desc=True)
            .limit(15)
            .execute().data or [])

        recent_verified = (db.table("assessments")
            .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no), units(name, code)")
            .in_("status", ["approved", "rejected"])
            .order("uploaded_at", desc=True)
            .limit(10)
            .execute().data or [])
    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")

    return render_template("cdacc_verifier/dashboard.html",
                           stats=stats,
                           pending_assessments=pending_assessments,
                           recent_verified=recent_verified,
                           current_month=datetime.now().strftime("%B %Y"))


@cdacc_verifier_bp.route("/assessments")
@login_required
@cdacc_verifier_required
def assessments():
    db = get_service_client()
    status_filter = request.args.get("status", "")
    dept_filter   = request.args.get("dept", "")
    query = (db.table("assessments")
               .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no, departments(name)), units(name, code), classes(name)")
               .order("uploaded_at", desc=True)
               .limit(300))
    if status_filter:
        query = query.eq("status", status_filter)
    records = query.execute().data or []
    departments = db.table("departments").select("id, name").order("name").execute().data or []
    return render_template("cdacc_verifier/assessments.html",
                           assessments=records, departments=departments,
                           status_filter=status_filter, dept_filter=dept_filter)


@cdacc_verifier_bp.route("/assessments/<assessment_id>/verify", methods=["POST"])
@login_required
@cdacc_verifier_required
def verify_assessment(assessment_id):
    db = get_service_client()
    user = current_user()
    new_status = request.form.get("status")
    feedback   = (request.form.get("feedback") or "").strip()
    if new_status not in ("approved", "rejected"):
        flash("Invalid status.", "warning")
        return redirect(url_for("cdacc_verifier.assessments"))
    try:
        update_data = {"status": new_status}
        if feedback:
            update_data["feedback"] = feedback
        db.table("assessments").update(update_data).eq("id", assessment_id).execute()
        write_audit_log(user["id"], "cdacc_verify_assessment",
                        f"Assessment {assessment_id} → {new_status}")
        flash(f"Assessment {new_status} successfully.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    return redirect(url_for("cdacc_verifier.assessments"))


# ── Trainer Documents (all departments) ───────────────────────────────────────

@cdacc_verifier_bp.route("/trainer-documents")
@login_required
@cdacc_verifier_required
def trainer_documents():
    db = get_service_client()
    dept_id    = request.args.get("dept_id", "")
    doc_type   = request.args.get("document_type", "")
    year       = request.args.get("year", str(datetime.now().year))
    term       = request.args.get("term", "")
    trainer_id = request.args.get("trainer_id", "")

    try:
        query = (db.table("trainer_documents")
            .select("*, units(name, code, department_id, departments(name)), "
                    "classes(name), "
                    "user_profiles!trainer_documents_trainer_id_fkey(full_name, staff_no, department_id, departments(name))")
            .eq("academic_year", int(year)))
        if term:       query = query.eq("term", term)
        if doc_type:   query = query.eq("document_type", doc_type)
        if trainer_id: query = query.eq("trainer_id", trainer_id)
        docs = query.order("created_at", desc=True).limit(500).execute().data or []

        # Apply department filter in Python (FK join makes direct filtering tricky)
        if dept_id:
            docs = [d for d in docs if
                    (d.get("units") or {}).get("department_id") == dept_id or
                    (d.get("user_profiles") or {}).get("department_id") == dept_id]

        departments = db.table("departments").select("id, name").order("name").execute().data or []
        trainers = (db.table("user_profiles").select("id, full_name, staff_no, department_id")
                    .eq("role", "trainer").order("full_name").execute().data or [])
        if dept_id:
            trainers = [t for t in trainers if t.get("department_id") == dept_id]
    except Exception as e:
        flash(f"Error loading documents: {e}", "danger")
        docs, departments, trainers = [], [], []

    return render_template("cdacc_verifier/trainer_documents.html",
                           documents=docs, departments=departments, trainers=trainers,
                           document_type=doc_type, year=year, term=term,
                           trainer_id=trainer_id, dept_id=dept_id)


# ── Filter cascade API ────────────────────────────────────────────────────────

@cdacc_verifier_bp.route("/filter-options")
@login_required
@cdacc_verifier_required
def filter_options():
    """Return classes, units, and trainers for a given department_id (JSON)."""
    db = get_service_client()
    dept_id = request.args.get("dept_id", "")
    try:
        if dept_id:
            classes  = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
            units    = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
            trainers = (db.table("user_profiles").select("id, full_name")
                        .eq("role", "trainer").eq("department_id", dept_id)
                        .order("full_name").execute().data or [])
        else:
            classes  = db.table("classes").select("id, name").order("name").limit(200).execute().data or []
            units    = db.table("units").select("id, name, code").order("name").limit(500).execute().data or []
            trainers = (db.table("user_profiles").select("id, full_name")
                        .eq("role", "trainer").order("full_name").limit(200).execute().data or [])
        return jsonify({"classes": classes, "units": units, "trainers": trainers})
    except Exception as e:
        return jsonify({"error": str(e), "classes": [], "units": [], "trainers": []}), 500


# ── Formative Marks (all departments) ────────────────────────────────────────

def _grade(obtained, max_m):
    if obtained is None or not max_m:
        return None, "N/A"
    pct = round(obtained / max_m * 100, 1)
    if pct >= 70:   return pct, "4"
    if pct >= 60:   return pct, "3"
    if pct >= 50:   return pct, "2"
    if pct >= 40:   return pct, "1"
    return pct, "U"


@cdacc_verifier_bp.route("/marks")
@login_required
@cdacc_verifier_required
def marks():
    db = get_service_client()
    dept_id    = request.args.get("dept_id", "")
    year       = request.args.get("year", str(datetime.now().year))
    term       = request.args.get("term", "")
    class_id   = request.args.get("class_id", "")
    unit_id    = request.args.get("unit_id", "")
    trainer_id = request.args.get("trainer_id", "")

    marks_list = []
    departments = []
    classes = []
    units = []
    trainers = []

    try:
        departments = db.table("departments").select("id, name").order("name").execute().data or []

        # Resolve which unit IDs to query
        if dept_id:
            dept_units = db.table("units").select("id").eq("department_id", dept_id).execute().data or []
            unit_ids = [u["id"] for u in dept_units]
        else:
            all_units = db.table("units").select("id").execute().data or []
            unit_ids = [u["id"] for u in all_units]

        if unit_ids:
            fa_q = (db.table("formative_assessments")
                    .select("id, unit_id, class_id, trainer_id, assessment_type, "
                            "assessment_name, max_marks, year, term, created_at, "
                            "units(name, code, departments(name)), classes(name), "
                            "trainer:user_profiles!formative_assessments_trainer_id_fkey(full_name)")
                    .in_("unit_id", unit_ids)
                    .eq("year", int(year)))
            if term:       fa_q = fa_q.eq("term",       int(term))
            if class_id:   fa_q = fa_q.eq("class_id",   class_id)
            if unit_id:    fa_q = fa_q.eq("unit_id",    unit_id)
            if trainer_id: fa_q = fa_q.eq("trainer_id", trainer_id)

            fa_list = fa_q.order("created_at", desc=True).execute().data or []
            fa_map  = {a["id"]: a for a in fa_list}

            if fa_map:
                fm_rows = (db.table("formative_marks")
                           .select("assessment_id, student_id, marks_obtained, "
                                   "student:user_profiles!formative_marks_student_id_fkey(full_name, admission_no)")
                           .in_("assessment_id", list(fa_map.keys()))
                           .execute().data or [])

                for m in fm_rows:
                    fa  = fa_map.get(m["assessment_id"], {})
                    pct, grade = _grade(m.get("marks_obtained"), fa.get("max_marks", 100))
                    marks_list.append({
                        "student":         m.get("student") or {},
                        "unit":            fa.get("units")   or {},
                        "class_":          fa.get("classes") or {},
                        "trainer":         fa.get("trainer") or {},
                        "dept":            (fa.get("units") or {}).get("departments") or {},
                        "assessment_name": fa.get("assessment_name", ""),
                        "assessment_type": fa.get("assessment_type", ""),
                        "max_marks":       fa.get("max_marks", 100),
                        "marks_obtained":  m.get("marks_obtained"),
                        "percentage":      pct,
                        "grade":           grade,
                        "year":            fa.get("year"),
                        "term":            fa.get("term"),
                    })

                marks_list.sort(key=lambda r: (
                    r["dept"].get("name", ""),
                    r["class_"].get("name", ""),
                    r["student"].get("full_name", ""),
                    r["unit"].get("name", ""),
                ))

        # Filter dropdowns
        if dept_id:
            classes  = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
            units    = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
            trainers = (db.table("user_profiles").select("id, full_name")
                        .eq("role", "trainer").eq("department_id", dept_id)
                        .order("full_name").execute().data or [])
        else:
            classes  = db.table("classes").select("id, name").order("name").limit(200).execute().data or []
            units    = db.table("units").select("id, name, code").order("name").limit(500).execute().data or []
            trainers = (db.table("user_profiles").select("id, full_name")
                        .eq("role", "trainer").order("full_name").limit(200).execute().data or [])

    except Exception as e:
        flash(f"Error loading marks: {e}", "danger")

    distinct_students = len({r["student"].get("admission_no") for r in marks_list if r["student"].get("admission_no")})
    pass_count = sum(1 for r in marks_list if r.get("grade") in ("4", "3", "2"))
    pass_rate  = round(pass_count / len(marks_list) * 100) if marks_list else 0

    return render_template("cdacc_verifier/marks.html",
                           marks=marks_list,
                           departments=departments, classes=classes,
                           units=units, trainers=trainers,
                           year=year, term=term, dept_id=dept_id,
                           class_id=class_id, unit_id=unit_id, trainer_id=trainer_id,
                           distinct_students=distinct_students, pass_rate=pass_rate)


# ── Trainee POE — all departments ─────────────────────────────────────────────

@cdacc_verifier_bp.route("/trainee-poe")
@login_required
@cdacc_verifier_required
def trainee_poe():
    import os
    db = get_service_client()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    dept_id    = request.args.get("dept_id", "")
    class_id   = request.args.get("class_id", "")
    unit_id    = request.args.get("unit_id", "")
    status_f   = request.args.get("status", "")

    def _fmt_size(b):
        if not b: return "0 B"
        for u in ["B", "KB", "MB", "GB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} GB"

    rows = []
    departments = []
    classes_opts = []
    units_opts = []

    try:
        departments = db.table("departments").select("id, name").order("name").execute().data or []

        query = (db.table("assessments")
            .select("id, status, script_file_path, script_file_name, script_file_size, "
                    "uploaded_at, assessment_type, assessment_no, term, year, "
                    "student:user_profiles!assessments_student_id_fkey(full_name, admission_no), "
                    "units(id, name, code, department_id, departments(name)), "
                    "classes(id, name)")
            .order("uploaded_at", desc=True)
            .limit(1000))

        if dept_id:
            query = query.eq("units.department_id", dept_id)
        if class_id:
            query = query.eq("class_id", class_id)
        if unit_id:
            query = query.eq("unit_id", unit_id)
        if status_f:
            query = query.eq("status", status_f)

        rows = query.execute().data or []

        # Batch-fetch all evidence for these assessments
        evidence_map = {}
        if rows:
            a_ids = [str(a["id"]) for a in rows if a.get("id")]
            # Fetch in chunks of 400 to stay within Supabase limits
            for i in range(0, len(a_ids), 400):
                chunk = a_ids[i:i+400]
                ev_rows = (db.table("evidence")
                             .select("id, assessment_id, file_path, file_name, file_type, file_size, caption")
                             .in_("assessment_id", chunk)
                             .execute().data or [])
                for ev in ev_rows:
                    aid = str(ev.get("assessment_id", ""))
                    ext = (ev.get("file_name") or "").rsplit(".", 1)[-1].lower()
                    ftype = ev.get("file_type") or ""
                    # Determine media kind from file_type field or extension
                    if ftype == "photo" or ext in ("jpg","jpeg","png","gif","webp","bmp"):
                        kind = "photo"
                    elif ftype == "video" or ext in ("mp4","mov","avi","mkv","webm"):
                        kind = "video"
                    elif ext in ("mp3","wav","ogg","m4a","aac","flac"):
                        kind = "audio"
                    else:
                        kind = "file"
                    evidence_map.setdefault(aid, []).append({
                        "id":      str(ev.get("id", "")),
                        "name":    ev.get("file_name") or "Evidence",
                        "caption": ev.get("caption") or "",
                        "kind":    kind,
                        "size":    _fmt_size(ev.get("file_size") or 0),
                        "url":     f"{supabase_url}/storage/v1/object/public/assessment-evidence/{ev['file_path']}" if ev.get("file_path") else "",
                    })

        if dept_id:
            classes_opts = db.table("classes").select("id, name").eq("department_id", dept_id).order("name").execute().data or []
            units_opts   = db.table("units").select("id, name, code").eq("department_id", dept_id).order("name").execute().data or []
        else:
            classes_opts = db.table("classes").select("id, name").order("name").limit(200).execute().data or []
            units_opts   = db.table("units").select("id, name, code").order("name").limit(500).execute().data or []

    except Exception as e:
        flash(f"Error loading trainee POE: {e}", "danger")

    # Build dept → class → unit → files structure
    folder_map = {}
    for a in rows:
        unit_obj  = a.get("units") or {}
        dept_name = (unit_obj.get("departments") or {}).get("name") or "Unknown Dept"
        cls_name  = (a.get("classes") or {}).get("name") or "Uncategorised"
        unit_name = f"{unit_obj.get('code','?')} — {unit_obj.get('name','?')}" if unit_obj.get("name") else "Unknown Unit"
        student   = a.get("student") or {}
        fp        = a.get("script_file_path") or ""
        aid       = str(a.get("id", ""))

        file_obj = {
            "id":             aid,
            "name":           a.get("script_file_name") or f"{a.get('assessment_type','?')} #{a.get('assessment_no','?')}",
            "url":            f"{supabase_url}/storage/v1/object/public/assessment-scripts/{fp}" if fp else "",
            "status":         (a.get("status") or "pending").title(),
            "admissionNumber": student.get("admission_no") or "N/A",
            "studentName":    student.get("full_name") or "Unknown",
            "formattedSize":  _fmt_size(a.get("script_file_size") or 0),
            "assessmentType": a.get("assessment_type") or "",
            "term":           str(a.get("term") or ""),
            "year":           str(a.get("year") or ""),
            "uploadedAt":     (a.get("uploaded_at") or "")[:10],
            "className":      cls_name,
            "unitName":       unit_name,
            "evidence":       evidence_map.get(aid, []),
        }
        folder_map.setdefault(dept_name, {}).setdefault(cls_name, {}).setdefault(unit_name, []).append(file_obj)

    # Build sorted hierarchy
    depts_data = []
    for dept_name in sorted(folder_map):
        classes_data = []
        for cls_name in sorted(folder_map[dept_name]):
            units_list = []
            for unit_name in sorted(folder_map[dept_name][cls_name]):
                files = sorted(folder_map[dept_name][cls_name][unit_name],
                               key=lambda f: (f["admissionNumber"] == "N/A", f["admissionNumber"]))
                units_list.append({"name": unit_name, "files": files})
            classes_data.append({"name": cls_name, "units": units_list})
        depts_data.append({"name": dept_name, "classes": classes_data})

    total_size = _fmt_size(sum(a.get("script_file_size") or 0 for a in rows))

    return render_template("cdacc_verifier/trainee_poe.html",
                           depts_data=depts_data,
                           total_depts=len(folder_map),
                           total_files=len(rows),
                           total_size=total_size,
                           departments=departments,
                           classes_opts=classes_opts,
                           units_opts=units_opts,
                           dept_id=dept_id, class_id=class_id,
                           unit_id=unit_id, status_f=status_f)
