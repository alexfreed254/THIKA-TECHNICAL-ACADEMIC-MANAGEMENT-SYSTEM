"""
routes/trainer_merged.py — Trainer blueprint (merged system).

Combines features from both:
- Attendance capture (from original)
- Assessment review (from copy)

Trainers can only access classes and units assigned to them.
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, abort, jsonify, make_response)
from auth_utils import (trainer_required, write_audit_log, current_user)
from db import get_service_client
from datetime import datetime
import re
import os

trainer_bp = Blueprint("trainer", __name__)


def _trainer_assigned_unit_ids(db) -> list:
    """Return list of unit_ids this trainer is assigned to."""
    user = current_user()
    if user.get("role") != "trainer":
        return []  # dept_admin / super_admin see everything
    rows = (db.table("trainer_units").select("unit_id")
            .eq("trainer_id", user["id"]).execute().data or [])
    return [r["unit_id"] for r in rows]


def _check_unit_access(db, unit_id: str) -> bool:
    """Return True if current trainer is allowed to act on this unit."""
    user = current_user()
    if user.get("role") != "trainer":
        return True
    assigned = _trainer_assigned_unit_ids(db)
    return bool(assigned) and unit_id in assigned


def _rename_script_file(db, assessment_id: str, action: str, trainer_name: str):
    """
    Append '— approved by <Trainer> — <TraineeName>' or
           '— rejected by <Trainer> — <TraineeName>'
    to the script_file_name stored in the DB (cosmetic label only).
    """
    try:
        a = (db.table("assessments")
             .select("script_file_name, student_id")
             .eq("id", assessment_id).single().execute().data)
        if not a:
            return
        trainee = (db.table("user_profiles").select("full_name")
                   .eq("id", a["student_id"]).single().execute().data)
        trainee_name = trainee["full_name"] if trainee else "Trainee"

        original = a.get("script_file_name", "")
        # Strip any previous approval/rejection suffix
        original = re.sub(r'\s*[—–-]+\s*(approved|rejected) by .+$', '', original, flags=re.IGNORECASE)
        # Remove .pdf extension, append suffix, re-add extension
        if original.lower().endswith('.pdf'):
            base = original[:-4]
        else:
            base = original
        suffix = f" — {action} by {trainer_name} — {trainee_name}.pdf"
        new_name = base + suffix
        db.table("assessments").update({"script_file_name": new_name}).eq("id", assessment_id).execute()
    except Exception:
        pass


# ── Dashboard ─────────────────────────────────────────────────────────────────

@trainer_bp.route("/")
@trainer_bp.route("/dashboard")
@trainer_required
def dashboard():
    db = get_service_client()
    user = current_user()
    stats = {}
    
    try:
        assigned_unit_ids = _trainer_assigned_unit_ids(db)

        # Assessment stats
        q = db.table("assessments").select("status")
        if assigned_unit_ids:
            q = q.in_("unit_id", assigned_unit_ids)
        elif user.get("role") == "trainer":
            # Trainer with no units assigned — show nothing
            q = q.eq("unit_id", "none")

        all_a = q.execute().data or []
        stats["total"] = len(all_a)
        stats["pending"] = sum(1 for a in all_a if a["status"] == "pending")
        stats["approved"] = sum(1 for a in all_a if a["status"] == "approved")
        stats["rejected"] = sum(1 for a in all_a if a["status"] == "rejected")

        # Pending assessments
        q2 = (db.table("assessments")
              .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no, mobile_number), units(name), classes(name)")
              .eq("status", "pending")
              .order("uploaded_at", desc=True)
              .limit(15))
        if assigned_unit_ids:
            q2 = q2.in_("unit_id", assigned_unit_ids)
        pending_assessments = q2.execute().data or []

        # Get assigned units
        units_list = []
        if assigned_unit_ids:
            units_list = db.table("units").select("*").in_("id", assigned_unit_ids).order("name").execute().data or []

    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")
        pending_assessments = []
        units_list = []

    return render_template("trainer/dashboard_enhanced.html",
                          stats=stats,
                          pending_assessments=pending_assessments,
                          units_list=units_list)


# ── Attendance Capture ─────────────────────────────────────────────────────────

@trainer_bp.route("/attendance", methods=["GET", "POST"])
@trainer_required
def attendance():
    db = get_service_client()
    user = current_user()
    dept_id = user.get("department_id")
    dept_name = "Department"
    if dept_id:
        dept = db.table("departments").select("name").eq("id", dept_id).single().execute().data
        if dept:
            dept_name = dept["name"]

    # Classes assigned to this trainer
    cu_rows = (db.table("class_units")
                 .select("class_id")
                 .eq("trainer_id", user["id"])
                 .execute().data or [])
    class_ids = list({r["class_id"] for r in cu_rows})

    class_list = []
    if class_ids:
        class_list = (db.table("classes")
                        .select("*")
                        .in_("id", class_ids)
                        .eq("department_id", dept_id)
                        .order("name")
                        .execute().data or [])

    class_id = request.args.get("class_id", "")
    unit_id = request.args.get("unit_id", "")
    week = request.args.get("week", 1, type=int)
    lesson = request.args.get("lesson", "L1")
    year = request.args.get("year", datetime.now().year, type=int)
    term = request.args.get("term", 1, type=int)

    units_list = []
    students_list = []
    attendance_submitted = False
    active_event = None

    if class_id:
        units_list = (db.table("class_units")
                        .select("*, units(id, code, name)")
                        .eq("class_id", class_id)
                        .eq("trainer_id", user["id"])
                        .execute().data or [])

        students_list = (db.table("enrollments")
                           .select("*, user_profiles(full_name, admission_no)")
                           .eq("class_id", class_id)
                           .execute().data or [])

        if unit_id and week and lesson:
            existing = (db.table("attendance")
                          .select("id", count="exact")
                          .eq("unit_id", unit_id)
                          .eq("trainer_id", user["id"])
                          .eq("week", week)
                          .eq("lesson", lesson)
                          .eq("year", year)
                          .eq("term", term)
                          .execute())
            attendance_submitted = (existing.count or 0) > 0

            event_row = (db.table("class_events")
                           .select("*")
                           .eq("class_id", class_id)
                           .eq("trainer_id", user["id"])
                           .eq("week", week)
                           .eq("lesson", lesson)
                           .eq("year", year)
                           .eq("term", term)
                           .execute().data or [])
            if event_row:
                active_event = event_row[0]

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "submit_attendance":
            if not class_id or not unit_id:
                flash("Class and unit are required.", "error")
            else:
                try:
                    for student in students_list:
                        status = request.form.get(f"status_{student['student_id']}", "absent")
                        db.table("attendance").insert({
                            "student_id": student["student_id"],
                            "unit_id": unit_id,
                            "unit_code": request.form.get("unit_code", ""),
                            "trainer_id": user["id"],
                            "lesson": lesson,
                            "week": week,
                            "year": year,
                            "term": term,
                            "status": status
                        }).execute()
                    
                    write_audit_log("submit_attendance", target=f"class:{class_id},unit:{unit_id}")
                    flash("Attendance submitted successfully.", "success")
                    return redirect(url_for("trainer.attendance", class_id=class_id, unit_id=unit_id, week=week, lesson=lesson, year=year, term=term))
                except Exception as e:
                    flash(f"Error submitting attendance: {e}", "error")
        
        elif action in ("mark_holiday", "mark_academic_trip"):
            if not class_id or not unit_id:
                flash("Class and unit are required.", "error")
            else:
                try:
                    # Create class_event
                    event_type = "holiday" if action == "mark_holiday" else "academic_trip"
                    label = "Holiday" if action == "mark_holiday" else "Academic Trip"
                    db.table("class_events").insert({
                        "class_id": class_id,
                        "unit_id": unit_id,
                        "trainer_id": user["id"],
                        "event_type": event_type,
                        "week": week,
                        "lesson": lesson,
                        "year": year,
                        "term": term,
                        "note": request.form.get("note", f"Marked as {label}")
                    }).execute()
                    # Mark all students with absent status (event record explains why)
                    for student in students_list:
                        existing = db.table("attendance").select("id").eq("student_id", student["student_id"]).eq("unit_id", unit_id).eq("week", week).eq("lesson", lesson).eq("year", year).eq("term", term).execute().data
                        if not existing:
                            db.table("attendance").insert({
                                "student_id": student["student_id"],
                                "unit_id": unit_id,
                                "unit_code": request.form.get("unit_code", ""),
                                "trainer_id": user["id"],
                                "lesson": lesson,
                                "week": week,
                                "year": year,
                                "term": term,
                                "status": "absent"
                            }).execute()
                    write_audit_log(action, target=f"class:{class_id},unit:{unit_id}")
                    flash(f"Marked as {label} successfully.", "success")
                    return redirect(url_for("trainer.attendance", class_id=class_id, unit_id=unit_id, week=week, lesson=lesson, year=year, term=term))
                except Exception as e:
                    flash(f"Error marking {label}: {e}", "error")

        elif action == "add_event":
            event_type = request.form.get("event_type")
            note = request.form.get("note", "")
            try:
                db.table("class_events").insert({
                    "class_id": class_id,
                    "unit_id": unit_id if unit_id else None,
                    "trainer_id": user["id"],
                    "event_type": event_type,
                    "week": week,
                    "lesson": lesson,
                    "year": year,
                    "term": term,
                    "note": note
                }).execute()
                write_audit_log("add_class_event", target=f"class:{class_id}")
                flash("Event added successfully.", "success")
                return redirect(url_for("trainer.attendance", class_id=class_id, unit_id=unit_id, week=week, lesson=lesson, year=year, term=term))
            except Exception as e:
                flash(f"Error adding event: {e}", "error")

    return render_template("trainer/attendance.html",
                          class_list=class_list,
                          class_id=class_id,
                          units_list=units_list,
                          unit_id=unit_id,
                          students_list=students_list,
                          week=week,
                          lesson=lesson,
                          year=year,
                          term=term,
                          attendance_submitted=attendance_submitted,
                          active_event=active_event,
                          dept_name=dept_name)


# ── Assessment Review ─────────────────────────────────────────────────────────

@trainer_bp.route("/assessments")
@trainer_required
def assessments():
    db = get_service_client()
    user = current_user()
    assigned_unit_ids = _trainer_assigned_unit_ids(db)

    # Get all assessments — include reviewer info via FK alias
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

    # Build class/unit hierarchy for drill-down
    classes_map = {}
    units_map = {}
    status_counts = {"total": 0, "pending": 0, "approved": 0, "rejected": 0}
    for a in assessments_list:
        status_counts["total"] += 1
        s = a.get("status", "pending")
        if s in status_counts:
            status_counts[s] += 1

        cls = a.get("classes") or {}
        cid = cls.get("id")
        if cid:
            if cid not in classes_map:
                classes_map[cid] = {"id": cid, "name": cls.get("name", ""), "units": {}}
            u = a.get("units") or {}
            uid = a.get("unit_id")
            if uid:
                if uid not in classes_map[cid]["units"]:
                    classes_map[cid]["units"][uid] = {
                        "id": uid,
                        "name": u.get("name", ""),
                        "code": u.get("code", ""),
                        "total": 0, "pending": 0, "approved": 0, "rejected": 0
                    }
                classes_map[cid]["units"][uid]["total"] += 1
                classes_map[cid]["units"][uid][s] += 1
                classes_map[cid]["units"][uid]["assessments"] = classes_map[cid]["units"][uid].get("assessments", []) + [a]

    # Also get assigned units for the class list
    class_list = []
    for cid, cdata in classes_map.items():
        unit_list = list(cdata["units"].values())
        unit_pending = sum(u["pending"] for u in unit_list)
        class_list.append({
            "id": cid,
            "name": cdata["name"],
            "units": sorted(unit_list, key=lambda u: u["name"]),
            "unit_count": len(unit_list),
            "pending": unit_pending
        })
    class_list.sort(key=lambda c: c["name"])

    return render_template("trainer/assessments.html",
                          classes=class_list,
                          status_counts=status_counts)


@trainer_bp.route("/assessment/<assessment_id>/review", methods=["GET", "POST"])
@trainer_required
def review_assessment(assessment_id):
    db = get_service_client()
    user = current_user()
    
    # Fetch assessment first so we can check unit access with the correct unit_id
    assessment = (db.table("assessments")
                  .select("*, user_profiles!assessments_student_id_fkey(full_name, admission_no, mobile_number), units(name, code), classes(name)")
                  .eq("id", assessment_id)
                  .limit(1)
                  .execute().data or [None])[0]
    
    if not assessment:
        abort(404)
    
    if not _check_unit_access(db, assessment["unit_id"]):
        abort(403)
    
    # Get evidence
    evidence = db.table("evidence").select("*").eq("assessment_id", assessment_id).execute().data or []
    
    if request.method == "POST":
        action = request.form.get("action")
        review_note = request.form.get("review_note", "").strip()

        if action in ["approve", "reject"]:
            new_status = "approved" if action == "approve" else "rejected"
            trainer_name = user.get("full_name", "Trainer")

            # ── Critical DB update (always attempt redirect after) ──────────
            try:
                db.table("assessments").update({
                    "status":      new_status,
                    "reviewed_by": user["id"],
                    "reviewed_at": datetime.now().isoformat(),
                    "review_note": review_note,
                }).eq("id", assessment_id).execute()
                flash(f"Assessment {new_status} by {trainer_name}.", "success")
            except Exception as e:
                flash(f"Error updating assessment: {e}", "error")

            # ── Non-critical: cosmetic file rename & audit (never block redirect)
            try:
                _rename_script_file(db, assessment_id, new_status, trainer_name)
            except Exception:
                pass
            try:
                write_audit_log(f"review_assessment_{action}", target=f"assessment:{assessment_id}")
            except Exception:
                pass

            # Always redirect — even if something failed
            return redirect(url_for("trainer.assessments"))

    # ── Fetch reviewer profile for display ────────────────────────────────────
    reviewer = None
    if assessment.get("reviewed_by"):
        try:
            reviewer_rows = (db.table("user_profiles")
                             .select("full_name")
                             .eq("id", assessment["reviewed_by"])
                             .limit(1)
                             .execute().data or [])
            reviewer = reviewer_rows[0] if reviewer_rows else None
        except Exception:
            pass

    return render_template("trainer/review_assessment.html",
                          assessment=assessment,
                          evidence=evidence,
                          reviewer=reviewer)


@trainer_bp.route("/assessment/<assessment_id>/delete", methods=["POST"])
@trainer_required
def delete_assessment(assessment_id):
    """Delete an assessment and its evidence."""
    db = get_service_client()
    user = current_user()

    assessment = db.table("assessments").select("*").eq("id", assessment_id).single().execute().data
    if not assessment:
        abort(404)
    if not _check_unit_access(db, assessment["unit_id"]):
        abort(403)

    try:
        evidence_list = db.table("evidence").select("*").eq("assessment_id", assessment_id).execute().data or []

        # Delete evidence files from storage
        svc = get_service_client()
        for e in evidence_list:
            try:
                path_parts = e["file_path"].split("/storage/v1/object/public/")
                if len(path_parts) > 1:
                    storage_path = path_parts[1].split("/", 1)[1] if "/" in path_parts[1] else path_parts[1]
                    bucket = path_parts[1].split("/")[0]
                    svc.storage.from_(bucket).remove([storage_path])
            except Exception:
                pass

        # Delete script file from storage
        try:
            sfp = assessment.get("script_file_path", "")
            if sfp:
                path_parts = sfp.split("/storage/v1/object/public/")
                if len(path_parts) > 1:
                    storage_path = path_parts[1].split("/", 1)[1] if "/" in path_parts[1] else path_parts[1]
                    bucket = path_parts[1].split("/")[0]
                    svc.storage.from_(bucket).remove([storage_path])
        except Exception:
            pass

        # Delete evidence records
        if evidence_list:
            eids = [e["id"] for e in evidence_list]
            db.table("evidence").delete().in_("id", eids).execute()

        # Delete assessment record
        db.table("assessments").delete().eq("id", assessment_id).execute()

        write_audit_log("delete_assessment", target=f"assessment:{assessment_id}")
        return jsonify({"success": True, "message": "Assessment deleted successfully."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ── Attendance History ───────────────────────────────────────────────────────

@trainer_bp.route("/attendance-history")
@trainer_required
def attendance_history():
    db = get_service_client()
    user = current_user()
    
    attendance_list = db.table("attendance").select("*, user_profiles:student_id(full_name, admission_no, enrollments(classes(name))), units(name, code)").eq("trainer_id", user["id"]).order("attendance_date", desc=True).limit(200).execute().data or []
    
    for att in attendance_list:
        student = att.get("user_profiles") or {}
        enrolls = student.get("enrollments") or []
        first_enroll = enrolls[0] if enrolls else {}
        cls = first_enroll.get("classes") or {}
        att["classes"] = cls
        
    return render_template("trainer/attendance_history.html",
                          attendance=attendance_list)


# ── Marks Entry ─────────────────────────────────────────────────────────────

@trainer_bp.route("/marks-entry")
@trainer_required
def marks_entry():
    """Marks entry page with class and unit selection."""
    db = get_service_client()
    user = current_user()
    
    # Get trainer's assigned units
    assigned_units = _trainer_assigned_unit_ids(db)
    
    # Get classes for these units
    units_with_classes = []
    for unit_id in assigned_units:
        unit_data = db.table("trainer_units").select("*, units(name, code), classes(name)").eq("unit_id", unit_id).execute().data or []
        units_with_classes.extend(unit_data)
    
    # Get filter parameters
    class_id = request.args.get("class_id", "").strip()
    unit_id = request.args.get("unit_id", "").strip()
    term = request.args.get("term", "").strip()
    cycle = request.args.get("cycle", "").strip()
    year = request.args.get("year", str(datetime.now().year))
    
    students_list = []
    existing_marks = []
    
    if class_id and unit_id:
        # Get students in the class
        students_list = (db.table("enrollments")
                        .select("*, user_profiles(full_name, admission_no)")
                        .eq("class_id", class_id)
                        .execute().data or [])
        
        # Get existing marks for this unit, term, cycle, year
        existing_marks = (db.table("marks")
                         .select("*")
                         .eq("unit_id", unit_id)
                         .eq("class_id", class_id)
                         .eq("term", term)
                         .eq("cycle", cycle)
                         .eq("year", year)
                         .execute().data or [])
    
    return render_template("trainer/marks_entry.html",
                          units_with_classes=units_with_classes,
                          class_id=class_id,
                          unit_id=unit_id,
                          term=term,
                          cycle=cycle,
                          year=year,
                          students_list=students_list,
                          existing_marks=existing_marks)


@trainer_bp.route("/marks-entry/submit", methods=["POST"])
@trainer_required
def submit_marks():
    """Submit marks for students."""
    db = get_service_client()
    user = current_user()
    
    class_id = request.form.get("class_id")
    unit_id = request.form.get("unit_id")
    term = request.form.get("term")
    cycle = request.form.get("cycle")
    year = request.form.get("year")
    assessment_type = request.form.get("assessment_type")
    assessment_name = request.form.get("assessment_name")
    
    if not all([class_id, unit_id, term, year, assessment_type, assessment_name]):
        flash("Missing required fields.", "error")
        return redirect(url_for("trainer.marks_entry"))
    
    try:
        # Get students in the class
        students_list = (db.table("enrollments")
                        .select("student_id")
                        .eq("class_id", class_id)
                        .execute().data or [])
        
        for student in students_list:
            marks_obtained = request.form.get(f"marks_{student['student_id']}")
            remarks = request.form.get(f"remarks_{student['student_id']}", "")
            
            if marks_obtained is not None and marks_obtained.strip():
                # Check if marks already exist
                existing = (db.table("marks")
                           .select("id")
                           .eq("student_id", student["student_id"])
                           .eq("unit_id", unit_id)
                           .eq("assessment_name", assessment_name)
                           .eq("term", term)
                           .eq("cycle", cycle)
                           .eq("year", year)
                           .execute().data)
                
                mark_data = {
                    "student_id": student["student_id"],
                    "unit_id": unit_id,
                    "trainer_id": user["id"],
                    "class_id": class_id,
                    "assessment_type": assessment_type,
                    "assessment_name": assessment_name,
                    "term": term,
                    "cycle": cycle,
                    "year": int(year),
                    "marks_obtained": float(marks_obtained),
                    "max_marks": 100,
                    "remarks": remarks
                }
                
                if existing:
                    # Update existing marks
                    db.table("marks").update(mark_data).eq("id", existing[0]["id"]).execute()
                else:
                    # Insert new marks
                    db.table("marks").insert(mark_data).execute()
        
        write_audit_log("submit_marks", target=f"class:{class_id},unit:{unit_id}")
        flash("Marks submitted successfully.", "success")
    except Exception as e:
        flash(f"Error submitting marks: {e}", "error")
    
    return redirect(url_for("trainer.marks_entry", class_id=class_id, unit_id=unit_id, term=term, cycle=cycle, year=year))


@trainer_bp.route("/marks-import")
@trainer_required
def marks_import():
    """Excel import page for marks."""
    db = get_service_client()
    user = current_user()
    
    # Get trainer's assigned units
    assigned_units = _trainer_assigned_unit_ids(db)
    
    # Get classes for these units
    units_with_classes = []
    for unit_id in assigned_units:
        unit_data = db.table("trainer_units").select("*, units(name, code), classes(name)").eq("unit_id", unit_id).execute().data or []
        units_with_classes.extend(unit_data)
    
    return render_template("trainer/marks_import.html", units_with_classes=units_with_classes)


@trainer_bp.route("/marks-import/upload", methods=["POST"])
@trainer_required
def upload_marks():
    """Upload and process Excel file for marks."""
    db = get_service_client()
    user = current_user()
    
    class_id = request.form.get("class_id")
    unit_id = request.form.get("unit_id")
    term = request.form.get("term")
    cycle = request.form.get("cycle")
    year = request.form.get("year")
    assessment_type = request.form.get("assessment_type")
    assessment_name = request.form.get("assessment_name")
    
    if not all([class_id, unit_id, term, year, assessment_type, assessment_name]):
        flash("Missing required fields.", "error")
        return redirect(url_for("trainer.marks_import"))
    
    if 'marks_file' not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for("trainer.marks_import"))
    
    file = request.files['marks_file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for("trainer.marks_import"))
    
    try:
        import openpyxl
        
        # Read Excel file using openpyxl (no pandas needed)
        wb = openpyxl.load_workbook(file, read_only=True, data_only=True)
        ws = wb.active
        
        # Read header row to find column positions
        headers = [str(cell.value).strip().lower() if cell.value else "" for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        
        if "admission_no" not in headers:
            flash("Missing required column: admission_no", "error")
            return redirect(url_for("trainer.marks_import"))
        if "marks" not in headers:
            flash("Missing required column: marks", "error")
            return redirect(url_for("trainer.marks_import"))
        
        adm_idx   = headers.index("admission_no")
        marks_idx = headers.index("marks")
        rem_idx   = headers.index("remarks") if "remarks" in headers else None
        
        processed = 0
        # Process data rows (skip header row 1)
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or row[adm_idx] is None:
                continue
            
            admission_no   = str(row[adm_idx]).strip()
            marks_obtained = row[marks_idx]
            remarks        = str(row[rem_idx]).strip() if rem_idx is not None and row[rem_idx] else ""
            
            if not admission_no or marks_obtained is None:
                continue
            
            try:
                marks_obtained = float(marks_obtained)
            except (ValueError, TypeError):
                continue
            
            # Get student by admission number
            student = (db.table("user_profiles")
                      .select("id")
                      .eq("admission_no", admission_no)
                      .eq("role", "student")
                      .single()
                      .execute().data)
            
            if student:
                # Check if marks already exist
                existing = (db.table("marks")
                           .select("id")
                           .eq("student_id", student["id"])
                           .eq("unit_id", unit_id)
                           .eq("assessment_name", assessment_name)
                           .eq("term", term)
                           .eq("cycle", cycle)
                           .eq("year", year)
                           .execute().data)
                
                mark_data = {
                    "student_id": student["id"],
                    "unit_id": unit_id,
                    "trainer_id": user["id"],
                    "class_id": class_id,
                    "assessment_type": assessment_type,
                    "assessment_name": assessment_name,
                    "term": term,
                    "cycle": cycle,
                    "year": int(year),
                    "marks_obtained": marks_obtained,
                    "max_marks": 100,
                    "remarks": remarks
                }
                
                if existing:
                    db.table("marks").update(mark_data).eq("id", existing[0]["id"]).execute()
                else:
                    db.table("marks").insert(mark_data).execute()
                
                processed += 1
        
        wb.close()
        write_audit_log("import_marks", target=f"class:{class_id},unit:{unit_id}")
        flash(f"Marks imported successfully. Processed {processed} records.", "success")
    except Exception as e:
        flash(f"Error importing marks: {e}", "error")
    
    return redirect(url_for("trainer.marks_import"))


# ── Marks PDF Download ─────────────────────────────────────────────────────────

@trainer_bp.route("/marks-entry/download-pdf")
@trainer_required
def download_marks_pdf():
    """Download marks as PDF."""
    db = get_service_client()
    user = current_user()
    
    class_id = request.args.get("class_id")
    unit_id = request.args.get("unit_id")
    term = request.args.get("term")
    cycle = request.args.get("cycle")
    year = request.args.get("year")
    
    if not all([class_id, unit_id, year]):
        flash("Missing required parameters.", "error")
        return redirect(url_for("trainer.marks_entry"))
    
    # Get marks for this unit, class, term, cycle, year
    marks_list = (db.table("marks")
                 .select("*, units(name, code), user_profiles!marks_student_id_fkey(full_name, admission_no), classes(name)")
                 .eq("unit_id", unit_id)
                 .eq("class_id", class_id)
                 .eq("term", term)
                 .eq("cycle", cycle)
                 .eq("year", int(year))
                 .execute().data or [])
    
    # Get unit and class details
    unit = db.table("units").select("*").eq("id", unit_id).single().execute().data
    cls = db.table("classes").select("*").eq("id", class_id).single().execute().data
    
    return render_template("trainer/marks_pdf.html",
                          marks=marks_list,
                          unit=unit,
                          cls=cls,
                          term=term,
                          cycle=cycle,
                          year=year,
                          trainer=user)


# ── Portfolio / Documents ───────────────────────────────────────────────────

@trainer_bp.route("/portfolio")
@trainer_required
def portfolio():
    """Trainer portfolio document management."""
    db = get_service_client()
    user = current_user()
    
    # Get trainer's assigned units
    assigned_units = _trainer_assigned_unit_ids(db)
    
    # Get all documents uploaded by trainer
    documents = (db.table("trainer_documents")
                .select("*, units(name, code), classes(name)")
                .eq("trainer_id", user["id"])
                .order("created_at", desc=True)
                .execute().data or [])
    
    # Get filter parameters
    document_type = request.args.get("document_type", "").strip()
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    
    # Apply filters
    if document_type:
        documents = [d for d in documents if d["document_type"] == document_type]
    if year:
        documents = [d for d in documents if d.get("academic_year") == int(year)]
    if term:
        documents = [d for d in documents if d.get("term") == term]
    
    return render_template("trainer/portfolio.html",
                          documents=documents,
                          assigned_units=assigned_units,
                          document_type=document_type,
                          year=year,
                          term=term)


@trainer_bp.route("/portfolio/upload", methods=["POST"])
@trainer_required
def upload_document():
    """Upload a document to portfolio."""
    db = get_service_client()
    user = current_user()
    
    document_type = request.form.get("document_type")
    document_name = request.form.get("document_name")
    unit_id = request.form.get("unit_id")
    class_id = request.form.get("class_id")
    academic_year = request.form.get("academic_year")
    term = request.form.get("term")
    description = request.form.get("description", "")
    
    if not all([document_type, document_name, academic_year]):
        flash("Missing required fields.", "error")
        return redirect(url_for("trainer.portfolio"))
    
    if 'document_file' not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for("trainer.portfolio"))
    
    file = request.files['document_file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for("trainer.portfolio"))
    
    try:
        # Upload file to Supabase Storage
        import uuid
        file_extension = file.filename.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        storage_path = f"trainer_documents/{user['id']}/{unique_filename}"
        
        # Read file once — used for both upload and size calculation
        file_data = file.read()
        
        # Upload to storage bucket using the service client (already configured)
        svc = get_service_client()
        svc.storage.from_("documents").upload(
            path=storage_path,
            file=file_data,
            file_options={"content-type": file.content_type}
        )
        
        # Get public URL
        file_url = f"{os.getenv('SUPABASE_URL')}/storage/v1/object/public/documents/{storage_path}"
        
        # Save document record
        db.table("trainer_documents").insert({
            "trainer_id": user["id"],
            "unit_id": unit_id if unit_id else None,
            "class_id": class_id if class_id else None,
            "document_type": document_type,
            "document_name": document_name,
            "file_url": file_url,
            "file_name": file.filename,
            "file_size": len(file_data),
            "file_type": file.content_type,
            "description": description,
            "academic_year": int(academic_year),
            "term": term
        }).execute()
        
        write_audit_log("upload_trainer_document", target=f"type:{document_type}")
        flash("Document uploaded successfully.", "success")
    except Exception as e:
        flash(f"Error uploading document: {e}", "error")
    
    return redirect(url_for("trainer.portfolio"))


@trainer_bp.route("/portfolio/delete/<document_id>", methods=["POST"])
@trainer_required
def delete_document(document_id):
    """Delete a document from portfolio."""
    db = get_service_client()
    user = current_user()
    
    try:
        # Get document
        document = db.table("trainer_documents").select("*").eq("id", document_id).single().execute().data
        
        if not document or document["trainer_id"] != user["id"]:
            abort(403)
        
        # Delete from storage
        storage_path = document["file_url"].split("documents/")[-1]
        svc = get_service_client()
        svc.storage.from_("documents").remove([storage_path])
        
        # Delete record
        db.table("trainer_documents").delete().eq("id", document_id).execute()
        
        write_audit_log("delete_trainer_document", target=f"document:{document_id}")
        flash("Document deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting document: {e}", "error")
    
    return redirect(url_for("trainer.portfolio"))
