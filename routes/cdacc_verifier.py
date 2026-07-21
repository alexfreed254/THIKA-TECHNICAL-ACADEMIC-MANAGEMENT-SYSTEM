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
        write_audit_log("cdacc_verify_assessment",
                        target=f"Assessment {assessment_id} → {new_status}")
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
    """TVET CDACC competency scale: M 80-100 · P 65-79 · C 50-64 · NYC 0-49."""
    if obtained is None or not max_m:
        return None, "N/A"
    from grading_utils import compute_grade
    return compute_grade(obtained, max_m)


@cdacc_verifier_bp.route("/marks")
@login_required
@cdacc_verifier_required
def marks():
    db = get_service_client()
    dept_id      = request.args.get("dept_id", "")
    year         = request.args.get("year", str(datetime.now().year))
    term         = request.args.get("term", "")
    class_id     = request.args.get("class_id", "")
    unit_id      = request.args.get("unit_id", "")
    trainer_id   = request.args.get("trainer_id", "")
    admission_no = request.args.get("admission_no", "").strip()

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

                # Filter by admission number (case-insensitive substring)
                if admission_no:
                    marks_list = [
                        r for r in marks_list
                        if admission_no.lower() in (r["student"].get("admission_no") or "").lower()
                    ]

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
    pass_count = sum(1 for r in marks_list if r.get("grade") in ("M", "P", "C"))
    pass_rate  = round(pass_count / len(marks_list) * 100) if marks_list else 0

    return render_template("cdacc_verifier/marks.html",
                           marks=marks_list,
                           departments=departments, classes=classes,
                           units=units, trainers=trainers,
                           year=year, term=term, dept_id=dept_id,
                           class_id=class_id, unit_id=unit_id, trainer_id=trainer_id,
                           admission_no=admission_no,
                           distinct_students=distinct_students, pass_rate=pass_rate)


# ── Trainee POE — all departments ─────────────────────────────────────────────

@cdacc_verifier_bp.route("/trainee-poe")
@login_required
@cdacc_verifier_required
def trainee_poe():
    import os
    from datetime import date as _date
    db = get_service_client()
    supabase_url  = os.environ.get("SUPABASE_URL", "").strip()

    dept_filter   = request.args.get("department", "")
    year_filter   = request.args.get("year", "")
    class_filter  = request.args.get("class_id", "")
    adm_filter    = request.args.get("admission_no", "").strip().upper()
    status_filter = request.args.get("status", "")

    def _fmt_size(b):
        if not b: return ""
        for u in ["B", "KB", "MB", "GB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} GB"

    records = []
    departments = []
    classes = []

    try:
        departments = db.table("departments").select("id, name").order("name").execute().data or []
        classes     = db.table("classes").select("id, name").order("name").limit(200).execute().data or []

        query = (db.table("assessments")
            .select("id, status, script_file_path, script_file_name, script_file_size, "
                    "uploaded_at, assessment_type, assessment_no, term, year, class_id, "
                    "student:user_profiles!assessments_student_id_fkey(full_name, admission_no), "
                    "units!inner(name, code, department_id, departments(name)), "
                    "classes(name)")
            .order("uploaded_at", desc=True)
            .limit(1000))

        if class_filter:
            query = query.eq("class_id", class_filter)
        if status_filter:
            query = query.eq("status", status_filter)
        if year_filter:
            try:
                query = query.eq("year", int(year_filter))
            except ValueError:
                pass

        records = query.execute().data or []

        # Filter by dept in Python (PostgREST dot-notation on joined tables not supported)
        if dept_filter:
            records = [r for r in records
                       if (r.get("units") or {}).get("department_id") == dept_filter]

        if adm_filter:
            records = [r for r in records
                       if adm_filter in (r.get("student") or {}).get("admission_no", "").upper()]

        # Batch-fetch evidence (chunked to stay within Supabase limits)
        evidence_map = {}
        if records:
            a_ids = [str(a["id"]) for a in records if a.get("id")]
            for i in range(0, len(a_ids), 400):
                chunk = a_ids[i:i + 400]
                ev_rows = (db.table("evidence")
                             .select("assessment_id, file_path, file_name, file_type")
                             .in_("assessment_id", chunk)
                             .execute().data or [])
                for ev in ev_rows:
                    aid  = str(ev.get("assessment_id", ""))
                    fp   = ev.get("file_path") or ""
                    name = ev.get("file_name") or (fp.rsplit("/", 1)[-1] if fp else "file")
                    ext  = name.rsplit(".", 1)[-1].lower() if "." in name else "bin"
                    ftype = ev.get("file_type") or ""
                    evidence_map.setdefault(aid, []).append({
                        "url":  f"{supabase_url}/storage/v1/object/public/assessment-evidence/{fp}" if fp else "",
                        "name": name,
                        "ext":  ext,
                        "type": ftype,
                    })

        # Attach script URL, size and evidence list to each record
        for r in records:
            fp = r.get("script_file_path") or ""
            r["_script_url"]  = (f"{supabase_url}/storage/v1/object/public/assessment-scripts/{fp}"
                                 if fp else "")
            r["_script_size"] = _fmt_size(r.get("script_file_size"))
            r["_evidence"]    = evidence_map.get(str(r.get("id", "")), [])

    except Exception as e:
        flash(f"Error loading trainee POE: {e}", "danger")

    cur_yr = _date.today().year
    years  = [str(y) for y in range(cur_yr, 2021, -1)]

    return render_template("cdacc_verifier/trainee_poe.html",
                           assessments=records,
                           departments=departments,
                           classes=classes,
                           years=years,
                           dept_filter=dept_filter,
                           year_filter=year_filter,
                           class_filter=class_filter,
                           adm_filter=adm_filter,
                           status_filter=status_filter)

# ── Trainee Profiles list ─────────────────────────────────────────────────────

@cdacc_verifier_bp.route("/trainees")
@login_required
@cdacc_verifier_required
def trainee_list():
    db      = get_service_client()
    dept_id = request.args.get("dept_id", "")
    q       = request.args.get("q", "").strip()
    try:
        query = (db.table("user_profiles")
                   .select("id, full_name, admission_no, department_id, departments(name), class_id, classes(name)")
                   .eq("role", "student")
                   .order("full_name"))
        if dept_id:
            query = query.eq("department_id", dept_id)
        trainees = query.limit(500).execute().data or []
        if q:
            ql = q.lower()
            trainees = [t for t in trainees
                        if ql in (t.get("full_name") or "").lower()
                        or ql in (t.get("admission_no") or "").lower()]
        departments = db.table("departments").select("id, name").order("name").execute().data or []
    except Exception as e:
        flash(f"Error loading trainees: {e}", "danger")
        trainees, departments = [], []

    return render_template("cdacc_verifier/trainee_list.html",
                           trainees=trainees, departments=departments,
                           dept_id=dept_id, q=q)


@cdacc_verifier_bp.route("/trainees/<student_id>")
@login_required
@cdacc_verifier_required
def trainee_detail(student_id):
    import os
    db = get_service_client()
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()

    try:
        stu_rows = (db.table("user_profiles")
                      .select("id, full_name, admission_no, department_id, departments(name), class_id, classes(name), phone, email")
                      .eq("id", student_id).limit(1).execute().data or [])
        if not stu_rows:
            flash("Trainee not found.", "warning")
            return redirect(url_for("cdacc_verifier.trainee_list"))
        student = stu_rows[0]

        # Formative marks
        all_fas = (db.table("formative_assessments")
                     .select("id, unit_id, class_id, trainer_id, assessment_type, assessment_name, "
                             "max_marks, year, term, "
                             "units(name, code), classes(name), "
                             "trainer:user_profiles!formative_assessments_trainer_id_fkey(full_name)")
                     .order("year", desc=True)
                     .limit(1000).execute().data or [])
        fa_map = {a["id"]: a for a in all_fas}

        fm_rows = (db.table("formative_marks")
                     .select("assessment_id, marks_obtained")
                     .eq("student_id", student_id)
                     .execute().data or [])

        marks_by_type = {}
        for m in fm_rows:
            fa = fa_map.get(m["assessment_id"])
            if not fa:
                continue
            atype = (fa.get("assessment_type") or "other").lower()
            mo    = m.get("marks_obtained")
            mm    = fa.get("max_marks") or 100
            pct   = round(mo / mm * 100, 1) if mo is not None and mm else None
            grade = ("M" if pct and pct >= 80 else "P" if pct and pct >= 65 else
                     "C" if pct and pct >= 50 else "NYC" if pct is not None else "N/A")
            marks_by_type.setdefault(atype, []).append({
                "name":           fa.get("assessment_name", ""),
                "unit":           (fa.get("units") or {}).get("name", ""),
                "code":           (fa.get("units") or {}).get("code", ""),
                "class_name":     (fa.get("classes") or {}).get("name", ""),
                "trainer":        (fa.get("trainer") or {}).get("full_name", ""),
                "year":           fa.get("year"),
                "term":           fa.get("term"),
                "marks_obtained": mo,
                "max_marks":      mm,
                "percentage":     pct,
                "grade":          grade,
            })
        for t in marks_by_type:
            marks_by_type[t].sort(key=lambda r: (r.get("year") or 0, r.get("term") or 0), reverse=True)

        # Attachment marks
        atts = (db.table("industrial_attachments")
                  .select("id, status, start_date, end_date, company_id, companies(name)")
                  .eq("student_id", student_id)
                  .order("created_at", desc=True).limit(5).execute().data or [])
        att_grades = []
        if atts:
            a_ids = [a["id"] for a in atts]
            grades_raw = (db.table("attachment_grades")
                            .select("*").in_("attachment_id", a_ids).execute().data or [])
            grades_map = {g["attachment_id"]: g for g in grades_raw}
            for a in atts:
                att_grades.append({"attachment": a, "grade": grades_map.get(a["id"])})

        # Mentoring tool uploads
        uploads = (db.table("mentoring_tool_uploads")
                     .select("*").eq("student_id", student_id)
                     .order("uploaded_at", desc=True).execute().data or [])

        # Digital logbook
        logbook = (db.table("digital_logbook")
                     .select("id, log_date, entry_time, tasks_performed, skills_applied, "
                             "hours_worked, challenges_encountered, achievements, "
                             "mentor_approval_status, mentor_comments, evidence_urls")
                     .eq("student_id", student_id)
                     .order("log_date", desc=True).limit(300).execute().data or [])
        for entry in logbook:
            urls = entry.get("evidence_urls") or []
            entry["_evidence"] = [
                f"{supabase_url}/storage/v1/object/public/assessment-evidence/{u}" for u in urls if u
            ]

    except Exception as e:
        flash(f"Error loading trainee data: {e}", "danger")
        student, marks_by_type, att_grades, uploads, logbook = {}, {}, [], [], []

    return render_template("cdacc_verifier/trainee_detail.html",
                           student=student,
                           marks_by_type=marks_by_type,
                           att_grades=att_grades,
                           uploads=uploads,
                           logbook=logbook)


# ── Attachment Marks ──────────────────────────────────────────────────────────

@cdacc_verifier_bp.route("/attachment-marks")
@login_required
@cdacc_verifier_required
def attachment_marks():
    db      = get_service_client()
    dept_id = request.args.get("dept_id", "")
    try:
        grades = (db.table("attachment_grades")
                    .select("*, attachment:industrial_attachments!attachment_id("
                            "id, student_id, status, start_date, end_date, company_id, "
                            "student:user_profiles!student_id(full_name, admission_no, department_id, departments(name)), "
                            "companies(name)"
                            ")")
                    .order("graded_at", desc=True).limit(500).execute().data or [])
        if dept_id:
            grades = [g for g in grades
                      if ((g.get("attachment") or {}).get("student") or {}).get("department_id") == dept_id]
        departments = db.table("departments").select("id, name").order("name").execute().data or []
    except Exception as e:
        flash(f"Error: {e}", "danger")
        grades, departments = [], []

    return render_template("cdacc_verifier/attachment_marks.html",
                           grades=grades, departments=departments, dept_id=dept_id)


# ── Mentoring Tool PDFs ───────────────────────────────────────────────────────

@cdacc_verifier_bp.route("/mentoring-tools")
@login_required
@cdacc_verifier_required
def mentoring_tools():
    db      = get_service_client()
    dept_id = request.args.get("dept_id", "")
    try:
        rows = (db.table("mentoring_tool_uploads")
                  .select("*, student:user_profiles!student_id(full_name, admission_no, department_id, departments(name))")
                  .order("uploaded_at", desc=True).limit(500).execute().data or [])
        if dept_id:
            rows = [r for r in rows
                    if ((r.get("student") or {}).get("department_id")) == dept_id]
        departments = db.table("departments").select("id, name").order("name").execute().data or []
    except Exception as e:
        flash(f"Error: {e}", "danger")
        rows, departments = [], []

    return render_template("cdacc_verifier/mentoring_tools.html",
                           uploads=rows, departments=departments, dept_id=dept_id)


# ── Digital Logbook ───────────────────────────────────────────────────────────

@cdacc_verifier_bp.route("/digital-logbook")
@login_required
@cdacc_verifier_required
def digital_logbook():
    db         = get_service_client()
    dept_id    = request.args.get("dept_id", "")
    adm_filter = request.args.get("admission_no", "").strip()
    status     = request.args.get("status", "")
    try:
        query = (db.table("digital_logbook")
                   .select("id, log_date, entry_time, tasks_performed, hours_worked, "
                           "mentor_approval_status, created_at, "
                           "student:user_profiles!student_id(full_name, admission_no, department_id, departments(name))")
                   .order("log_date", desc=True).limit(500))
        if status:
            query = query.eq("mentor_approval_status", status)
        rows = query.execute().data or []
        if dept_id:
            rows = [r for r in rows
                    if ((r.get("student") or {}).get("department_id")) == dept_id]
        if adm_filter:
            rows = [r for r in rows
                    if adm_filter.lower() in ((r.get("student") or {}).get("admission_no") or "").lower()]
        departments = db.table("departments").select("id, name").order("name").execute().data or []
    except Exception as e:
        flash(f"Error: {e}", "danger")
        rows, departments = [], []

    return render_template("cdacc_verifier/digital_logbook.html",
                           entries=rows, departments=departments,
                           dept_id=dept_id, adm_filter=adm_filter, status=status)

