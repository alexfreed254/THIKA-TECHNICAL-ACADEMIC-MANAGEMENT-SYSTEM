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
        base = original[:-4] if original.lower().endswith('.pdf') else original
        suffix = f" — {action} by {trainer_name} — {trainee_name}"
        new_name = base + suffix + ".pdf"
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

    return render_template("trainer/dashboard.html",
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
                          active_event=active_event)


# ── Assessment Review ─────────────────────────────────────────────────────────

@trainer_bp.route("/assessments")
@trainer_required
def assessments():
    db = get_service_client()
    user = current_user()
    
    assigned_unit_ids = _trainer_assigned_unit_ids(db)
    
    q = db.table("assessments").select("*, user_profiles(full_name, admission_no), units(name, code), classes(name)").order("uploaded_at", desc=True)
    if assigned_unit_ids:
        q = q.in_("unit_id", assigned_unit_ids)
    
    assessments_list = q.execute().data or []

    return render_template("trainer/assessments.html",
                          assessments=assessments_list)


@trainer_bp.route("/assessment/<assessment_id>/review", methods=["GET", "POST"])
@trainer_required
def review_assessment(assessment_id):
    db = get_service_client()
    user = current_user()
    
    if not _check_unit_access(db, assessment_id):
        abort(403)
    
    assessment = db.table("assessments").select("*, user_profiles(full_name, admission_no, mobile_number), units(name, code), classes(name)").eq("id", assessment_id).single().execute().data
    
    if not assessment:
        abort(404)
    
    # Get evidence
    evidence = db.table("evidence").select("*").eq("assessment_id", assessment_id).execute().data or []
    
    if request.method == "POST":
        action = request.form.get("action")
        review_note = request.form.get("review_note", "")
        
        if action in ["approve", "reject"]:
            try:
                update_data = {
                    "status": action + "d" if action == "approve" else "rejected",
                    "reviewed_by": user["id"],
                    "reviewed_at": datetime.now().isoformat(),
                    "review_note": review_note
                }
                db.table("assessments").update(update_data).eq("id", assessment_id).execute()
                
                # Rename file
                _rename_script_file(db, assessment_id, action + "d" if action == "approve" else "rejected", user["full_name"])
                
                write_audit_log(f"review_assessment_{action}", target=f"assessment:{assessment_id}")
                flash(f"Assessment {action}d successfully.", "success")
                return redirect(url_for("trainer.assessments"))
            except Exception as e:
                flash(f"Error reviewing assessment: {e}", "error")
    
    return render_template("trainer/review_assessment.html",
                          assessment=assessment,
                          evidence=evidence)


# ── Attendance History ───────────────────────────────────────────────────────

@trainer_bp.route("/attendance-history")
@trainer_required
def attendance_history():
    db = get_service_client()
    user = current_user()
    
    attendance_list = db.table("attendance").select("*, user_profiles(full_name, admission_no), units(name, code), classes(name)").eq("trainer_id", user["id"]).order("attendance_date", desc=True).limit(200).execute().data or []

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
        import pandas as pd
        
        # Read Excel file
        df = pd.read_excel(file)
        
        # Expected columns: admission_no, marks, remarks
        required_columns = ['admission_no', 'marks']
        for col in required_columns:
            if col not in df.columns:
                flash(f"Missing required column: {col}", "error")
                return redirect(url_for("trainer.marks_import"))
        
        # Process each row
        for _, row in df.iterrows():
            admission_no = str(row['admission_no']).strip()
            marks_obtained = float(row['marks'])
            remarks = str(row.get('remarks', '')) if 'remarks' in row else ""
            
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
                    # Update existing marks
                    db.table("marks").update(mark_data).eq("id", existing[0]["id"]).execute()
                else:
                    # Insert new marks
                    db.table("marks").insert(mark_data).execute()
        
        write_audit_log("import_marks", target=f"class:{class_id},unit:{unit_id}")
        flash(f"Marks imported successfully. Processed {len(df)} records.", "success")
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
        
        # Upload to storage bucket
        from supabase import create_client, Client
        storage: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
        
        storage.storage.from_("documents").upload(
            path=storage_path,
            file=file.read(),
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
            "file_size": len(file.read()) if file else 0,
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
        from supabase import create_client
        storage = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
        storage.storage.from_("documents").remove([storage_path])
        
        # Delete record
        db.table("trainer_documents").delete().eq("id", document_id).execute()
        
        write_audit_log("delete_trainer_document", target=f"document:{document_id}")
        flash("Document deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting document: {e}", "error")
    
    return redirect(url_for("trainer.portfolio"))
