"""
routes/student_merged.py — Student blueprint (merged system).

Combines features from both:
- Attendance viewing (from original)
- Assessment uploads (from copy)
- Profile management (from copy)
"""

import re
import os
from typing import Optional
from flask import (Blueprint, render_template, request,
                   redirect, url_for, abort, flash, make_response, jsonify)
from auth_utils import (student_required, write_audit_log, current_user)
from db import get_service_client
from datetime import datetime
from notifications import get_user_notifications
import uuid

student_bp = Blueprint("student", __name__)

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')
ALLOWED_PASSPORT_IMAGES = {'jpg', 'jpeg', 'png', 'webp'}

# Template helper functions
def get_file_icon_class(url):
    """Get CSS class for file icon based on extension."""
    if not url:
        return ''
    ext = url.split('.').pop().lower()
    if ext == 'pdf':
        return 'pdf'
    if ext in ['mp4', 'mkv', 'avi', 'mov']:
        return 'video'
    if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
        return 'image'
    if ext in ['mp3', 'wav', 'ogg']:
        return 'audio'
    return ''

def get_filename_from_url(url):
    """Extract filename from URL."""
    if not url:
        return 'Unknown'
    return url.split('/').pop().split('?')[0]

# Template helpers are passed via app context_processor in app.py
# (Blueprint objects don't have jinja_env; registration happens on the app)


def _validate_password(pwd: str) -> Optional[str]:
    if len(pwd) < 8:
        return "Password must be at least 8 characters."
    if not re.search(r'\d', pwd):
        return "Password must contain at least one number."
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>/?]', pwd):
        return "Password must contain at least one symbol (e.g. @, #, !)."
    return None


def _student_row() -> dict:
    """Return the user_profiles row for the current student, or abort 403."""
    user = current_user()
    db = get_service_client()
    try:
        rows = (db.table("user_profiles")
                  .select("*, classes(name, department_id, departments(name))")
                  .eq("id", user["id"])
                  .limit(1)
                  .execute().data or [])
        if not rows:
            abort(403)
        return rows[0]
    except Exception:
        abort(403)


def _allowed_passport_image(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_PASSPORT_IMAGES


def _clean_mobile_number(value: str) -> str:
    value = (value or '').strip()
    if value.startswith('+'):
        return '+' + re.sub(r'\D', '', value[1:])
    return re.sub(r'\D', '', value)


def _format_bytes(size: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ── Dashboard ─────────────────────────────────────────────────────────────────

@student_bp.route("/")
@student_bp.route("/dashboard")
@student_required
def dashboard():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    student = _student_row()
    stats = {}
    unread_notifications = []
    recent_assessments = []
    recent_attendance = []
    attendance_data = []
    overall_pct = 0
    total_attended = 0
    current_month = datetime.now().strftime("%B %Y")
    
    try:
        # Stats via count queries (Efficient DB level processing)
        stats['total']    = db.table("assessments").select("id", count="exact").eq("student_id", student_id).execute().count or 0
        stats['pending']  = db.table("assessments").select("id", count="exact").eq("student_id", student_id).eq("status", "pending").execute().count or 0
        stats['approved'] = db.table("assessments").select("id", count="exact").eq("student_id", student_id).eq("status", "approved").execute().count or 0
        stats['rejected'] = db.table("assessments").select("id", count="exact").eq("student_id", student_id).eq("status", "rejected").execute().count or 0
        
        # Fetch unread notifications for inline display
        unread_notifications = get_user_notifications(student_id, unread_only=True, limit=3)

        # Attendance data by unit (for dashboard table)
        raw_attendance = (db.table("attendance")
                         .select("status, attendance_date, units(id, name, code)")
                         .eq("student_id", student_id)
                         .execute().data or [])
        # Group by unit in Python
        unit_map = {}
        for r in raw_attendance:
            u = r.get("units") or {}
            uid = u.get("id")
            if not uid:
                continue
            if uid not in unit_map:
                unit_map[uid] = {
                    "id": uid,
                    "unit_code": u.get("code", ""),
                    "unit_name": u.get("name", ""),
                    "attended": 0,
                    "total_records": 0,
                    "last_update": None
                }
            unit_map[uid]["total_records"] += 1
            if r.get("status") == "present":
                unit_map[uid]["attended"] += 1
            # Track latest date
            dt = r.get("attendance_date")
            if dt and (not unit_map[uid]["last_update"] or dt > unit_map[uid]["last_update"]):
                unit_map[uid]["last_update"] = dt
        attendance_data = list(unit_map.values())
        
        # Calculate attendance stats
        all_attendance = (db.table("attendance")
                         .select("status")
                         .eq("student_id", student_id)
                         .execute().data or [])
        total_attended = sum(1 for a in all_attendance if a.get('status') == 'present')
        total_records = len(all_attendance)
        overall_pct = round((total_attended / total_records * 100), 1) if total_records > 0 else 0
        
        stats['attendance_total'] = total_records
        stats['attendance_percent'] = overall_pct

        # Job Application count
        stats['job_apps'] = db.table("job_applications").select("id", count="exact").eq("student_id", student_id).execute().count or 0

        # Recent assessments
        recent_assessments = (db.table("assessments")
                  .select("*, units(name), classes(name)")
                  .eq("student_id", student_id)
                  .order("uploaded_at", desc=True)
                  .limit(10)
                  .execute().data or [])
        
        # Batch fetch evidence counts to avoid N+1 queries
        evidence_map = {}
        if recent_assessments:
            a_ids = [r['id'] for r in recent_assessments]
            evidence_rows = db.table("evidence").select("assessment_id").in_("assessment_id", a_ids).execute().data or []
            for ev in evidence_rows:
                evidence_map[ev['assessment_id']] = evidence_map.get(ev['assessment_id'], 0) + 1

        for r in recent_assessments:
            r['script_file_size_fmt'] = _format_bytes(r.get('script_file_size', 0))
            r['evidence_count'] = evidence_map.get(r['id'], 0)

        # Recent attendance
        recent_attendance = (db.table("attendance")
                  .select("*, units(name, code), user_profiles:student_id(enrollments(classes(name)))")
                  .eq("student_id", student_id)
                  .order("attendance_date", desc=True)
                  .limit(10)
                  .execute().data or [])
                  
        for att in recent_attendance:
            att_user = att.get("user_profiles") or {}
            enrolls = att_user.get("enrollments") or []
            first_enroll = enrolls[0] if enrolls else {}
            cls = first_enroll.get("classes") or {}
            att["classes"] = cls

    except Exception as e:
        flash(f'Error loading dashboard: {str(e)}', 'danger')

    # Check clearance eligibility (has completed course requirements)
    clearance_eligible = False
    try:
        # Check if student has completed all units (simplified check)
        enrollments = (db.table("enrollments")
                      .select("*, courses(id)")
                      .eq("student_id", student_id)
                      .execute().data or [])
        
        # For now, consider eligible if enrolled in at least one course
        # In production, this should check actual completion status
        clearance_eligible = len(enrollments) > 0
    except Exception:
        clearance_eligible = False

    # ── ATTACHMENT / INTERNSHIP DATA ──────────────────────────────────────────
    current_attachment = None
    attachment_stats = {
        'total': 0,
        'active': 0,
        'completed': 0,
        'pending': 0
    }
    recent_logbook_entries = []
    pending_competencies = 0
    
    try:
        # Get current active attachment
        attachments = (db.table("industrial_attachments")
                      .select("*, companies(name, address, latitude, longitude), units(name, code), mentors(user_profiles(full_name))")
                      .eq("student_id", student_id)
                      .order("created_at", desc=True)
                      .execute().data or [])
        
        # Count attachment stats
        attachment_stats['total'] = len(attachments)
        for att in attachments:
            status = att.get('status', '')
            if status == 'active':
                attachment_stats['active'] += 1
                if not current_attachment:
                    current_attachment = att
                    # Flatten mentor name
                    mentors_obj = current_attachment.get("mentors") or {}
                    user_profiles_obj = mentors_obj.get("user_profiles") or {}
                    current_attachment["mentor_name"] = user_profiles_obj.get("full_name", "Not Assigned")
            elif status == 'completed':
                attachment_stats['completed'] += 1
            elif status == 'pending':
                attachment_stats['pending'] += 1
        
        # Get recent logbook entries (last 5)
        if current_attachment:
            recent_logbook_entries = (db.table("digital_logbook")
                                     .select("*, units(name, code)")
                                     .eq("student_id", student_id)
                                     .eq("attachment_id", current_attachment["id"])
                                     .order("log_date", desc=True)
                                     .limit(5)
                                     .execute().data or [])
        
        # Get pending competencies count
        pending_competencies = (db.table("competency_tracking")
                               .select("id", count="exact")
                               .eq("student_id", student_id)
                               .eq("competency_status", "NYC")
                               .execute().count or 0)
        
        # Add attachment stats to main stats
        stats['attachment_active'] = attachment_stats['active']
        stats['attachment_total'] = attachment_stats['total']
        stats['logbook_entries'] = len(recent_logbook_entries)
        stats['pending_competencies'] = pending_competencies
        
    except Exception as e:
        print(f"Error loading attachment data: {e}")
        # Continue without attachment data

    return render_template("student/dashboard_enhanced.html",
                          student=student,
                          stats=stats,
                          recent_assessments=recent_assessments,
                          recent_attendance=recent_attendance,
                          clearance_eligible=clearance_eligible,
                          unread_notifications=unread_notifications,
                          attendance_data=attendance_data,
                          overall_pct=overall_pct,
                          total_attended=total_attended,
                          current_month=current_month,
                          current_attachment=current_attachment,
                          attachment_stats=attachment_stats,
                          recent_logbook_entries=recent_logbook_entries,
                          pending_competencies=pending_competencies)


# ── Profile Management ───────────────────────────────────────────────────────

@student_bp.route("/profile", methods=["GET", "POST"])
@student_required
def profile():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    if request.method == "POST":
        form_action = request.form.get("form_action", "details")
        
        if form_action == "details":
            mobile_number = _clean_mobile_number(request.form.get("mobile_number", ""))
            if not mobile_number or len(re.sub(r'\D', '', mobile_number)) < 10:
                flash('Enter a valid WhatsApp number.', 'danger')
                return redirect(url_for("student.profile"))
            try:
                db.table("user_profiles").update({
                    "mobile_number": mobile_number
                }).eq("id", student_id).execute()
                write_audit_log("update_profile", target=f"user:{student_id}")
                flash('Profile updated successfully.', 'success')
                return redirect(url_for("student.profile"))
            except Exception as e:
                flash(f'Error updating profile: {e}', 'danger')
        
        elif form_action == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            
            if not all([current_password, new_password, confirm_password]):
                flash('All password fields are required.', 'danger')
                return redirect(url_for("student.profile"))
            
            if new_password != confirm_password:
                flash('New passwords do not match.', 'danger')
                return redirect(url_for("student.profile"))
            
            pwd_err = _validate_password(new_password)
            if pwd_err:
                flash(pwd_err, 'danger')
                return redirect(url_for("student.profile"))
            
            # Verify current password
            from werkzeug.security import check_password_hash, generate_password_hash
            if not check_password_hash(user.get("password_hash", ""), current_password):
                flash('Current password is incorrect.', 'danger')
                return redirect(url_for("student.profile"))
            
            try:
                db.table("user_profiles").update({
                    "password_hash": generate_password_hash(new_password),
                    "must_change_password": False
                }).eq("id", student_id).execute()
                write_audit_log("password_change", target=f"user:{student_id}")
                flash('Password changed successfully.', 'success')
                return redirect(url_for("student.profile"))
            except Exception as e:
                flash(f'Error changing password: {e}', 'danger')
        
        elif form_action == "passport":
            if 'passport' not in request.files:
                flash('No file selected.', 'danger')
                return redirect(url_for("student.profile"))
            
            file = request.files['passport']
            if file.filename == '':
                flash('No file selected.', 'danger')
                return redirect(url_for("student.profile"))
            
            if not _allowed_passport_image(file.filename):
                flash('Invalid file type. Use JPG, JPEG, PNG, or WEBP.', 'danger')
                return redirect(url_for("student.profile"))
            
            try:
                # Upload to Supabase Storage using service client
                ext = file.filename.rsplit('.', 1)[1].lower()
                filename = f"passports/{student_id}_{uuid.uuid4().hex}.{ext}"
                
                storage_client = get_service_client().storage
                storage_client.from_("assessment-evidence").upload(
                    filename,
                    file.read(),
                    {"content-type": f"image/{ext}" if ext != 'jpg' else 'image/jpeg'}
                )
                
                # Get public URL
                public_url = storage_client.from_("assessment-evidence").get_public_url(filename)
                
                # Update user profile
                db.table("user_profiles").update({
                    "passport_file_path": filename,
                    "passport_file_name": file.filename
                }).eq("id", student_id).execute()
                
                write_audit_log("upload_passport", target=f"user:{student_id}")
                flash('Passport photo uploaded successfully.', 'success')
                return redirect(url_for("student.profile"))
            except Exception as e:
                flash(f'Error uploading passport: {e}', 'danger')

    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data
    
    return render_template("student/profile.html", student=student)


# ── My Documents ───────────────────────────────────────────────────────────────

@student_bp.route("/documents", methods=["GET", "POST"])
@student_required
def my_documents():
    """Manage student personal documents with individual file uploads."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    if request.method == "POST":
        # Handle document uploads
        document_types = [
            'passport_photo', 'admission_letter', 'medical_form', 'personal_data_form',
            'declaration_form', 'kcse_result_slip', 'kcse_certificate', 'kcpe_result_slip',
            'birth_certificate', 'national_id', 'guardian_id', 'consent_form'
        ]
        
        uploaded_count = 0
        for doc_type in document_types:
            if doc_type in request.files:
                file = request.files[doc_type]
                if file and file.filename:
                    try:
                        # Upload to Supabase Storage
                        ext = file.filename.rsplit('.', 1)[1].lower()
                        filename = f"student_documents/{student_id}_{doc_type}_{uuid.uuid4().hex}.{ext}"
                        
                        storage_client = get_service_client().storage
                        storage_client.from_("student-documents").upload(
                            filename,
                            file.read(),
                            {"content-type": f"application/{ext}" if ext == 'pdf' else f"image/{ext}"}
                        )
                        
                        # Get public URL
                        public_url = storage_client.from_("student-documents").get_public_url(filename)
                        
                        # Check if document already exists
                        existing = db.table("student_documents").select("*").eq("student_id", student_id).eq("document_type", doc_type).execute().data
                        
                        if existing:
                            # Update existing document
                            db.table("student_documents").update({
                                "file_path": filename,
                                "file_name": file.filename,
                                "file_size": len(file.read()) if file else 0,
                                "uploaded_at": "now()"
                            }).eq("id", existing[0]["id"]).execute()
                        else:
                            # Insert new document
                            db.table("student_documents").insert({
                                "student_id": student_id,
                                "document_type": doc_type,
                                "file_path": filename,
                                "file_name": file.filename,
                                "file_size": len(file.read()) if file else 0,
                                "status": "pending"
                            }).execute()
                        
                        uploaded_count += 1
                    except Exception as e:
                        flash(f'Error uploading {doc_type.replace("_", " ").title()}: {e}', 'danger')
        
        if uploaded_count > 0:
            write_audit_log("upload_documents", target=f"user:{student_id}", detail={"count": uploaded_count})
            flash(f'{uploaded_count} document(s) uploaded successfully.', 'success')
        
        return redirect(url_for("student.my_documents"))

    # GET request - fetch student data and documents
    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data
    
    # Get course and department info
    enrollment = db.table("enrollments").select("*, classes(name, course_id)").eq("student_id", student_id).execute().data or []
    course_name = ""
    department_name = ""
    
    if enrollment:
        class_data = enrollment[0].get("classes", {})
        course_id = class_data.get("course_id")
        if course_id:
            course = db.table("courses").select("*, departments(name)").eq("id", course_id).single().execute().data or {}
            course_name = course.get("name", "")
            department_name = course.get("departments", {}).get("name", "")
    
    # Get uploaded documents
    documents_data = db.table("student_documents").select("*").eq("student_id", student_id).execute().data or []
    documents = {doc["document_type"]: doc for doc in documents_data}
    
    return render_template("student/my_documents.html", 
                          student=student, 
                          course_name=course_name,
                          department_name=department_name,
                          documents=documents)


# ── Assessment Upload ─────────────────────────────────────────────────────────

@student_bp.route("/assessments")
@student_required
def assessments():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    student = _student_row()
    
    # Get student's class
    enrollment = db.table("enrollments").select("*, classes(name, course_id)").eq("student_id", student_id).execute().data or []
    
    if not enrollment:
        flash('You are not enrolled in any class.', 'warning')
        return redirect(url_for("student.dashboard"))
    
    class_id = enrollment[0]["class_id"]
    course_id = enrollment[0].get("classes", {}).get("course_id")
    
    # Get units for this class
    class_units = db.table("class_units").select("*, units(name, code)").eq("class_id", class_id).execute().data or []
    
    # Get all assessments
    assessments_list = (db.table("assessments")
                       .select("*, units(name, code), classes(name)")
                       .eq("student_id", student_id)
                       .order("uploaded_at", desc=True)
                       .execute().data or [])
    
    for a in assessments_list:
        a['script_file_size_fmt'] = _format_bytes(a.get('script_file_size', 0))
        ev = db.table("evidence").select("id").eq("assessment_id", a['id']).execute().data or []
        a['evidence_count'] = len(ev)
    
    return render_template("student/assessments.html",
                          student=student,
                          class_units=class_units,
                          assessments=assessments_list)


@student_bp.route("/assessments/upload", methods=["GET", "POST"])
@student_required
def upload_assessment():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get student's class
    enrollment = db.table("enrollments").select("*, classes(name)").eq("student_id", student_id).execute().data or []
    
    if not enrollment:
        flash('You are not enrolled in any class.', 'warning')
        return redirect(url_for("student.dashboard"))
    
    class_id = enrollment[0]["class_id"]
    
    # Get units for this class
    class_units = db.table("class_units").select("*, units(name, code)").eq("class_id", class_id).execute().data or []
    
    if request.method == "POST":
        unit_id = request.form.get("unit_id")
        assessment_type = request.form.get("assessment_type")
        assessment_no = request.form.get("assessment_no", type=int)
        term = request.form.get("term", type=int)
        cycle = request.form.get("cycle", type=int)
        year = request.form.get("year", type=int)
        
        if not all([unit_id, assessment_type, assessment_no, term, cycle, year]):
            flash('All fields are required.', 'danger')
            return redirect(url_for("student.upload_assessment"))
        
        files = request.files.getlist("scripts")
        files = [f for f in files if f and f.filename]
        if not files:
            flash('At least one PDF file is required.', 'danger')
            return redirect(url_for("student.upload_assessment"))
        
        uploaded = 0
        errors = []
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                errors.append(f"'{file.filename}' is not a PDF — skipped.")
                continue
            try:
                filename = f"scripts/{student_id}_{unit_id}_{assessment_type}_{assessment_no}_{uuid.uuid4().hex}.pdf"
                file_data = file.read()
                get_service_client().storage.from_("assessment-scripts").upload(
                    filename, file_data, {"content-type": "application/pdf"}
                )
                result = db.table("assessments").insert({
                    "student_id": student_id,
                    "class_id": class_id,
                    "unit_id": unit_id,
                    "assessment_type": assessment_type,
                    "assessment_no": assessment_no,
                    "term": term,
                    "cycle": cycle,
                    "year": year,
                    "script_file_path": filename,
                    "script_file_name": file.filename,
                    "script_file_size": len(file_data),
                    "status": "pending"
                }).execute()
                write_audit_log("upload_assessment", target=f"assessment:{result.data[0]['id']}")
                uploaded += 1
            except Exception as e:
                errors.append(f"Error uploading '{file.filename}': {e}")

        if uploaded:
            flash(f"{uploaded} assessment(s) uploaded successfully. You can now add evidence.", 'success')
        for err in errors:
            flash(err, 'danger')
        return redirect(url_for("student.portfolio"))
    
    return render_template("student/upload_assessment.html", class_units=class_units)


# ── Delete Assessment (own) ───────────────────────────────────────────────────

@student_bp.route("/assessments/<assessment_id>/delete", methods=["POST"])
@student_required
def delete_assessment(assessment_id):
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    assessment = (db.table("assessments")
                 .select("*")
                 .eq("id", assessment_id).eq("student_id", student_id)
                 .single().execute().data)
    if not assessment:
        abort(403)

    try:
        # Delete evidence records + storage files
        ev_list = db.table("evidence").select("*").eq("assessment_id", assessment_id).execute().data or []
        for ev in ev_list:
            if ev.get("file_path"):
                try:
                    get_service_client().storage.from_("assessment-evidence").remove([ev["file_path"]])
                except Exception:
                    pass
            db.table("evidence").delete().eq("id", ev["id"]).execute()

        # Delete script from storage
        if assessment.get("script_file_path"):
            try:
                get_service_client().storage.from_("assessment-scripts").remove([assessment["script_file_path"]])
            except Exception:
                pass

        # Delete assessment record
        db.table("assessments").delete().eq("id", assessment_id).execute()
        write_audit_log("delete_assessment", target=f"assessment:{assessment_id}")
        flash("Assessment deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting assessment: {e}", "danger")

    return redirect(url_for("student.portfolio"))


# ── My Files (Assessment & Evidence Browser) ──────────────────────────────────

@student_bp.route("/my-files")
@student_required
def my_files():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    assessments = (db.table("assessments")
                  .select("*, classes(name), units(name, code)")
                  .eq("student_id", student_id)
                  .order("uploaded_at", desc=True)
                  .execute().data or [])

    if assessments:
        a_ids = [a["id"] for a in assessments]
        ev_rows = (db.table("evidence")
                  .select("assessment_id, id, file_type, file_size")
                  .in_("assessment_id", a_ids)
                  .execute().data or [])
        ev_count = {}
        ev_size = {}
        for ev in ev_rows:
            aid = ev["assessment_id"]
            ev_count[aid] = ev_count.get(aid, 0) + 1
            ev_size[aid] = ev_size.get(aid, 0) + (ev.get("file_size") or 0)
    else:
        ev_count = {}
        ev_size = {}

    def fmt_size(b):
        if not b: return "0 B"
        for u in ["B","KB","MB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} GB"

    for a in assessments:
        a["_ev_count"] = ev_count.get(a["id"], 0)
        a["_ev_size"] = fmt_size(ev_size.get(a["id"], 0))

    return render_template("student/my_files.html", assessments=assessments)


# ── Upload / Manage Evidence for an Assessment ───────────────────────────────

@student_bp.route("/assessments/<assessment_id>/evidence", methods=["GET", "POST"])
@student_required
def add_evidence(assessment_id):
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    assessment = (db.table("assessments")
                 .select("*, classes(name), units(name, code)")
                 .eq("id", assessment_id).eq("student_id", student_id)
                 .single().execute().data)
    if not assessment:
        abort(403)
    
    evidence_list = (db.table("evidence")
                    .select("*")
                    .eq("assessment_id", assessment_id)
                    .order("uploaded_at", desc=True)
                    .execute().data or [])

    def fmt_size(b):
        if not b: return "0 B"
        b = int(b)
        for u in ["B","KB","MB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} GB"

    for ev in evidence_list:
        ev["file_size_fmt"] = fmt_size(ev.get("file_size"))

    if request.method == "POST":
        if 'evidence_file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(url_for("student.add_evidence", assessment_id=assessment_id))
        
        file = request.files['evidence_file']
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(url_for("student.add_evidence", assessment_id=assessment_id))
        
        ext = file.filename.rsplit('.', 1)[1].lower()
        if ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            file_type = 'photo'
            content_type = f"image/{ext if ext != 'jpg' else 'jpeg'}"
        elif ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']:
            file_type = 'video'
            content_type = f"video/{ext}"
        elif ext in ['mp3', 'wav', 'ogg', 'm4a', 'flac', 'aac']:
            file_type = 'audio'
            content_type = f"audio/{ext}"
        else:
            flash('Invalid file type. Use images, videos, or audio files.', 'danger')
            return redirect(url_for("student.add_evidence", assessment_id=assessment_id))
        
        caption = request.form.get("caption", "")
        
        try:
            filename = f"evidence/{student_id}_{assessment_id}_{uuid.uuid4().hex}.{ext}"
            file_data = file.read()
            get_service_client().storage.from_("assessment-evidence").upload(
                filename, file_data, {"content-type": content_type}
            )
            db.table("evidence").insert({
                "assessment_id": assessment_id,
                "student_id": student_id,
                "file_path": filename,
                "file_name": file.filename,
                "file_type": file_type,
                "file_size": len(file_data),
                "caption": caption
            }).execute()
            write_audit_log("add_evidence", target=f"assessment:{assessment_id}")
            flash('Evidence added successfully.', 'success')
        except Exception as e:
            flash(f'Error adding evidence: {e}', 'danger')
        return redirect(url_for("student.add_evidence", assessment_id=assessment_id))
    
    return render_template("student/add_evidence.html",
                          assessment=assessment,
                          evidence=evidence_list)


@student_bp.route("/assessments/<assessment_id>/evidence/<evidence_id>/delete", methods=["GET", "POST"])
@student_required
def delete_evidence(assessment_id, evidence_id):
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Verify assessment belongs to student
    assessment = db.table("assessments").select("*").eq("id", assessment_id).eq("student_id", student_id).single().execute().data
    
    if not assessment:
        abort(403)
    
    # Get evidence
    evidence = db.table("evidence").select("*").eq("id", evidence_id).eq("assessment_id", assessment_id).single().execute().data
    
    if not evidence:
        abort(404)
    
    try:
        # Delete from storage
        storage_client = get_service_client().storage
        storage_client.from_("assessment-evidence").remove([evidence["file_path"]])
        
        # Delete from database
        db.table("evidence").delete().eq("id", evidence_id).execute()
        
        write_audit_log("delete_evidence", target=f"evidence:{evidence_id}")
        flash('Evidence deleted successfully.', 'success')
    except Exception as e:
        flash(f'Error deleting evidence: {e}', 'danger')
    
    return redirect(url_for("student.add_evidence", assessment_id=assessment_id))


# ── Attendance History ───────────────────────────────────────────────────────

@student_bp.route("/attendance")
@student_required
def attendance():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    attendance_list = (db.table("attendance")
                      .select("*, units(name, code), user_profiles:student_id(enrollments(classes(name)))")
                      .eq("student_id", student_id)
                      .order("attendance_date", desc=True)
                      .execute().data or [])
                      
    for att in attendance_list:
        student = att.get("user_profiles") or {}
        enrolls = student.get("enrollments") or []
        first_enroll = enrolls[0] if enrolls else {}
        cls = first_enroll.get("classes") or {}
        att["classes"] = cls
    
    # Calculate attendance percentage
    total = len(attendance_list)
    present = sum(1 for a in attendance_list if a["status"] == "present")
    percentage = (present / total * 100) if total > 0 else 0
    
    return render_template("student/attendance.html",
                          attendance=attendance_list,
                          total=total,
                          present=present,
                          percentage=percentage)


# ── My Units ────────────────────────────────────────────────────────────────────

@student_bp.route("/units")
@student_required
def my_units():
    """Show units the student is enrolled in with attendance stats."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    # Get student's enrollments
    enrollments = (db.table("enrollments")
                  .select("*, classes(name)")
                  .eq("student_id", student_id)
                  .execute().data or [])

    # Get class_ids from enrollments
    class_ids = [e["class_id"] for e in enrollments]

    # Get class_units for those classes (this links classes to units)
    class_units_data = []
    if class_ids:
        class_units_data = (db.table("class_units")
                           .select("*, units(name, code, id)")
                           .in_("class_id", class_ids)
                           .execute().data or [])

    units_data = []
    for cu in class_units_data:
        unit = cu.get("units") or {}
        uid = unit.get("id")
        if not uid:
            continue
        att = (db.table("attendance")
              .select("status")
              .eq("student_id", student_id)
              .eq("unit_id", uid)
              .execute().data or [])
        total = len(att)
        present = sum(1 for a in att if a.get("status") == "present")
        pct = round(present / total * 100, 1) if total > 0 else 0
        
        # Get class name from enrollments
        class_id = cu.get("class_id")
        class_name = ""
        for enr in enrollments:
            if enr.get("class_id") == class_id:
                class_name = (enr.get("classes") or {}).get("name", "")
                break
        
        units_data.append({
            "id": uid,
            "code": unit.get("code", ""),
            "name": unit.get("name", ""),
            "class_name": class_name,
            "attended": present,
            "total": total,
            "pct": pct
        })

    return render_template("student/units.html",
                          units=units_data)


# ── Unit Detail (Attendance Drill-Down) ────────────────────────────────────────

@student_bp.route("/unit-detail")
@student_required
def unit_detail():
    """View attendance records for a specific unit."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    unit_id = request.args.get("unit_id")

    if not unit_id:
        flash("Unit ID is required.", "error")
        return redirect(url_for("student.dashboard"))

    unit = db.table("units").select("*").eq("id", unit_id).single().execute().data or {}

    records = (db.table("attendance")
              .select("*")
              .eq("student_id", student_id)
              .eq("unit_id", unit_id)
              .order("attendance_date", desc=True)
              .execute().data or [])

    total = len(records)
    present = sum(1 for r in records if r.get("status") == "present")
    pct = round(present / total * 100, 1) if total > 0 else 0

    absent = total - present
    info = {"class_name": "", "dept_name": ""}

    return render_template("student/unit_detail.html",
                          unit=unit,
                          records=records,
                          present=present,
                          absent=absent,
                          total=total,
                          pct=pct,
                          info=info)


@student_bp.route("/unit-report-pdf")
@student_required
def unit_report_pdf():
    """Generate a PDF attendance report for a unit."""
    from flask import make_response
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    import io

    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    unit_id = request.args.get("unit_id")

    if not unit_id:
        flash("Unit ID is required.", "error")
        return redirect(url_for("student.dashboard"))

    unit = db.table("units").select("*").eq("id", unit_id).single().execute().data or {}
    student = db.table("user_profiles").select("full_name, admission_no").eq("id", student_id).single().execute().data or {}

    records = (db.table("attendance")
              .select("*")
              .eq("student_id", student_id)
              .eq("unit_id", unit_id)
              .order("attendance_date", desc=True)
              .execute().data or [])

    total = len(records)
    present = sum(1 for r in records if r.get("status") == "present")
    pct = round(present / total * 100, 1) if total > 0 else 0

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4)
    styles = getSampleStyleSheet()
    elems = []

    elems.append(Paragraph("Attendance Report", styles["Title"]))
    elems.append(Spacer(1, 12))
    elems.append(Paragraph(f"Student: {student.get('full_name', 'N/A')} ({student.get('admission_no', '')})", styles["Normal"]))
    elems.append(Paragraph(f"Unit: {unit.get('name', 'N/A')} ({unit.get('code', '')})", styles["Normal"]))
    elems.append(Paragraph(f"Attendance: {present}/{total} ({pct}%)", styles["Normal"]))
    elems.append(Spacer(1, 20))

    data = [["Date", "Status"]]
    for r in records:
        data.append([r.get("attendance_date", ""), r.get("status", "").capitalize()])

    t = Table(data)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1565c0")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 12),
        ("GRID", (0, 0), (-1, -1), 1, colors.grey),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    elems.append(t)

    doc.build(elems)
    buf.seek(0)

    return make_response(buf.getvalue(),
                         200,
                         {"Content-Type": "application/pdf",
                          "Content-Disposition": f"attachment; filename=attendance_{unit.get('code', 'unit')}.pdf"})


# ── Portfolio of Evidence View ─────────────────────────────────────────────────

@student_bp.route("/portfolio-view")
@student_required
def portfolio_view():
    """View all POE submissions with filters."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get student's class
    enrollment = db.table("enrollments").select("class_id").eq("student_id", student_id).execute().data or []
    class_id = enrollment[0]["class_id"] if enrollment else None
    
    # Get units for the student's class
    units = []
    if class_id:
        cu_rows = db.table("class_units").select("*, units(name, code)").eq("class_id", class_id).execute().data or []
        units = cu_rows
    
    # Get all POE submissions (from assessments table)
    poe_submissions = (db.table("assessments")
                      .select("*, units(name, code)")
                      .eq("student_id", student_id)
                      .order("created_at", desc=True)
                      .execute().data or [])
    
    # Add unit name to each submission
    for poe in poe_submissions:
        if poe.get("units"):
            poe["unit_name"] = poe["units"].get("name", "")
        else:
            poe["unit_name"] = "N/A"
    
    # Calculate statistics
    stats = {
        "total": len(poe_submissions),
        "pending": len([p for p in poe_submissions if p.get("status") == "pending"]),
        "approved": len([p for p in poe_submissions if p.get("status") == "approved"]),
        "rejected": len([p for p in poe_submissions if p.get("status") == "rejected"])
    }
    
    return render_template("student/portfolio_view.html",
                          poe_submissions=poe_submissions,
                          units=units,
                          stats=stats)


# ── Portfolio of Evidence Upload (Premium Design) ─────────────────────────────

@student_bp.route("/upload-poe")
@student_required
def upload_poe():
    """Show premium POE upload interface with radio selectors and multi-file upload."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get student data
    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}
    
    # Get student's class
    enrollment = db.table("enrollments").select("class_id").eq("student_id", student_id).execute().data or []
    class_id = enrollment[0]["class_id"] if enrollment else None
    
    # Get classes available
    classes = []
    if class_id:
        classes = db.table("classes").select("*").eq("id", class_id).execute().data or []
    
    # Get units for the student's class
    units = []
    if class_id:
        cu_rows = db.table("class_units").select("*, units(name, code)").eq("class_id", class_id).execute().data or []
        units = cu_rows
    
    current_year = datetime.now().year
    
    return render_template("student/upload_poe.html",
                          student=student,
                          classes=classes,
                          units=units,
                          current_year=current_year)


@student_bp.route("/poe-upload", methods=["POST"])
@student_required
def poe_upload():
    """Handle POE file uploads with Supabase Storage."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    try:
        # Get form data
        admission_no = request.form.get('admissionNo', '')
        class_name = request.form.get('className', '')
        unit_name = request.form.get('unitName', '')
        cycle = request.form.get('cycle', '1')
        term = request.form.get('term', '1')
        year = request.form.get('year', str(datetime.now().year))
        assessment_type = request.form.get('assessmentType', 'Formative')
        assessment_no = request.form.get('assessmentNo', '01')
        upload_choice = request.form.get('uploadChoice', 'script')
        
        if not admission_no or not upload_choice:
            return jsonify({'success': False, 'error': 'Missing core validation fields.'}), 400
        
        # Get files
        files = request.files.getlist('files')
        saved_records = []
        
        storage_client = get_service_client().storage
        
        for file in files:
            if file.filename == '':
                continue
            
            # Get file extension
            orig_ext = os.path.splitext(file.filename)[1].lower()
            
            # Generate clean filename
            clean_filename = f"{admission_no}-{unit_name.replace(' ', '_')}-CYCLE{cycle}-TERM{term}-{year}-{assessment_type}-{assessment_no}_{upload_choice}{orig_ext}"
            
            # Create storage path: POE/CLASS/UNIT/ADMISSION_NO/
            storage_path = f"POE/{class_name.replace(' ', '_')}/{unit_name.replace(' ', '_')}/{admission_no}/{clean_filename}"
            
            # Read file data
            file_data = file.read()
            
            # Upload to Supabase Storage
            storage_client.from_("assessment-evidence").upload(storage_path, file_data, {
                "content-type": file.content_type,
                "upsert": "true"
            })
            
            # Get public URL
            public_url = storage_client.from_("assessment-evidence").get_public_url(storage_path)
            
            # Save to database (assessments table or create new table for POE)
            # For now, we'll use the existing assessments table
            assessment_data = {
                "student_id": student_id,
                "unit_id": None,  # Will need to map unit_name to unit_id
                "title": f"{assessment_type} Assessment {assessment_no} - {upload_choice}",
                "description": f"POE Upload: {upload_choice} for {unit_name}",
                "due_date": datetime.now().date(),
                "submission_type": upload_choice,
                "status": "pending",
                "evidence_urls": [public_url]
            }
            
            # Insert into assessments table
            db.table("assessments").insert(assessment_data).execute()
            
            saved_records.append(clean_filename)
        
        write_audit_log("poe_upload", target=f"student:{student_id}", detail={
            "files": len(saved_records),
            "type": upload_choice,
            "unit": unit_name
        })
        
        return jsonify({'success': True, 'uploaded': saved_records})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Exam Bookings ─────────────────────────────────────────────────────────────

@student_bp.route("/exam-bookings")
@student_required
def exam_bookings():
    """View all exam bookings for the student."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    bookings = (db.table("exam_bookings")
                .select("*, units(name, code), user_profiles!exam_bookings_approved_by_fkey(full_name)")
                .eq("student_id", student_id)
                .order("created_at", desc=True)
                .execute().data or [])
    
    return render_template("student/exam_bookings.html", bookings=bookings)


@student_bp.route("/exam-bookings/new", methods=["GET", "POST"])
@student_required
def new_exam_booking():
    """Redirect to new exam booking form."""
    return redirect(url_for("student.exam_booking_form"))


# ── New Exam Booking Workflow (Semi-Digital) ─────────────────────────────────────

@student_bp.route("/exam-booking-form")
@student_required
def exam_booking_form():
    """Show new exam booking form with document verification and unit selection."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    # Get student data
    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}
    
    # Get course and department info
    enrollment = db.table("enrollments").select("*, classes(name, course_id)").eq("student_id", student_id).execute().data or []
    course_name = ""
    department_name = ""
    class_id = None
    
    if enrollment:
        class_data = enrollment[0].get("classes", {})
        class_id = class_data.get("id")
        course_id = class_data.get("course_id")
        if course_id:
            course = db.table("courses").select("*, departments(name)").eq("id", course_id).single().execute().data or {}
            course_name = course.get("name", "")
            department_name = course.get("departments", {}).get("name", "")
    
    # Get units for the student's class
    units = []
    if class_id:
        cu_rows = (db.table("class_units")
                   .select("*, units(name, code)")
                   .eq("class_id", class_id)
                   .execute().data or [])
        units = cu_rows
    
    # Get uploaded documents
    documents_data = db.table("student_documents").select("*").eq("student_id", student_id).execute().data or []
    documents = {doc["document_type"]: doc for doc in documents_data}
    
    # Check required documents
    required_docs = ['national_id', 'birth_certificate', 'kcse_certificate', 'passport_photo']
    missing_documents = any(doc not in documents for doc in required_docs)
    
    # Check if can download (all docs present + at least one unit selected)
    can_download = not missing_documents and len(units) > 0
    
    return render_template("student/exam_booking_new.html",
                          student=student,
                          course_name=course_name,
                          department_name=department_name,
                          units=units,
                          documents=documents,
                          missing_documents=missing_documents,
                          can_download=can_download)


@student_bp.route("/exam-booking-submit", methods=["POST"])
@student_required
def exam_booking_submit():
    """Handle exam booking form submission and generate multi-page PDF."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    # Get selected units
    selected_units = request.form.getlist("selected_units")
    
    if not selected_units:
        flash('Please select at least one unit.', 'danger')
        return redirect(url_for("student.exam_booking_form"))
    
    # Get student data
    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}
    
    # Get course and department info
    enrollment = db.table("enrollments").select("*, classes(name, course_id)").eq("student_id", student_id).execute().data or []
    course_name = ""
    department_name = ""
    
    if enrollment:
        class_data = enrollment[0].get("classes", {})
        course_id = class_data.get("course_id")
        if course_id:
            course = db.table("courses").select("*, departments(name)").eq("id", course_id).single().execute().data or {}
            course_name = course.get("name", "")
            department_name = course.get("departments", {}).get("name", "")
    
    # Get units details
    units_data = []
    for unit_id in selected_units:
        unit = db.table("units").select("*").eq("id", unit_id).single().execute().data
        if unit:
            unit_type = request.form.get(f"unit_type_{unit_id}", "core")
            units_data.append({
                "unit": unit,
                "type": unit_type
            })
    
    # Get documents
    documents_data = db.table("student_documents").select("*").eq("student_id", student_id).execute().data or []
    documents = {doc["document_type"]: doc for doc in documents_data}
    
    # Generate serial number: EXAM/DEPT/COURSE/YEAR/SERIES/UNIQUE_SERIAL
    # Get department code
    dept_code = ""
    if enrollment:
        class_data = enrollment[0].get("classes", {})
        course_id = class_data.get("course_id")
        if course_id:
            course = db.table("courses").select("*, departments(code)").eq("id", course_id).single().execute().data or {}
            dept_code = course.get("departments", {}).get("code", "GEN")
    
    # Get course code
    course_code = ""
    if enrollment:
        class_data = enrollment[0].get("classes", {})
        course_id = class_data.get("course_id")
        if course_id:
            course = db.table("courses").select("code").eq("id", course_id).single().execute().data or {}
            course_code = course.get("code", "GEN")
    
    # Generate serial components
    year = datetime.now().year
    series = "1"  # Can be 1, 2, or 3 for different exam series in a year
    unique_serial = str(uuid.uuid4().int)[:8]
    
    serial_number = f"EXAM/{dept_code}/{course_code}/{year}/{series}/{unique_serial}"
    
    # Create exam booking record with serial number
    for unit_data in units_data:
        db.table("exam_bookings").insert({
            "student_id": student_id,
            "unit_id": unit_data["unit"]["id"],
            "exam_date": datetime.now().date(),
            "exam_session": "morning",
            "purpose": f"Exam booking for {unit_data['unit']['name']} ({unit_data['type']})",
            "status": "pending",
            "serial_number": serial_number
        }).execute()
    
    write_audit_log("create_exam_booking", target=f"booking:{serial_number}", detail={"units": len(units_data)})
    
    # Generate multi-page PDF with embedded documents
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        import io
        from PIL import Image as PILImage
        import os
        
        # Create PDF buffer
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=72, leftMargin=72, topMargin=72, bottomMargin=18)
        
        # Story (content) list
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.darkblue,
            alignment=TA_CENTER,
            spaceAfter=12
        )
        
        header_style = ParagraphStyle(
            'CustomHeader',
            parent=styles['Heading2'],
            fontSize=12,
            textColor=colors.black,
            alignment=TA_CENTER,
            spaceAfter=6
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.black,
            spaceAfter=6
        )
        
        # PAGE 1: COVER PAGE
        story.append(Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", title_style))
        story.append(Spacer(1, 12))
        story.append(Paragraph("EXAMINATION BOOKING FORM", header_style))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Serial Number: {serial_number}", normal_style))
        story.append(Paragraph(f"Academic Year: {year}", normal_style))
        story.append(Paragraph(f"Exam Series: {series}", normal_style))
        story.append(Spacer(1, 24))
        
        # PAGE 2: STUDENT DETAILS
        story.append(Paragraph("STUDENT DETAILS", header_style))
        story.append(Spacer(1, 12))
        
        student_data = [
            ["Full Name:", student.get("full_name", "")],
            ["Admission Number:", student.get("admission_no", "")],
            ["Course:", course_name],
            ["Department:", department_name],
            ["Phone:", student.get("mobile_number", "")],
            ["Email:", student.get("email", "")],
            ["PWD Status:", student.get("pwd_status", "N/A")]
        ]
        
        student_table = Table(student_data, colWidths=[2*inch, 4*inch])
        student_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(student_table)
        story.append(Spacer(1, 24))
        
        # PAGE 3: UNIT REGISTRATION
        story.append(Paragraph("UNIT REGISTRATION", header_style))
        story.append(Spacer(1, 12))
        
        unit_headers = ["S/N", "Unit Name", "Unit Code", "Type"]
        unit_rows = [[str(i+1), u["unit"]["name"], u["unit"]["code"], u["type"].title()] for i, u in enumerate(units_data)]
        unit_table_data = [unit_headers] + unit_rows
        
        unit_table = Table(unit_table_data, colWidths=[0.5*inch, 2.5*inch, 1.5*inch, 1*inch])
        unit_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(unit_table)
        story.append(Spacer(1, 24))
        
        # PAGE 4: DOCUMENT VERIFICATION SUMMARY
        story.append(Paragraph("DOCUMENT VERIFICATION SUMMARY", header_style))
        story.append(Spacer(1, 12))
        
        doc_headers = ["Document", "Status", "Reference ID"]
        doc_rows = []
        required_docs_list = [
            ("National ID", "national_id"),
            ("Birth Certificate", "birth_certificate"),
            ("KCSE Certificate", "kcse_certificate"),
            ("Passport Photo", "passport_photo")
        ]
        
        for doc_name, doc_type in required_docs_list:
            doc = documents.get(doc_type)
            status = "✓ Attached" if doc else "✗ Missing"
            ref_id = doc.get("id", "")[:8] if doc else "N/A"
            doc_rows.append([doc_name, status, ref_id])
        
        doc_table_data = [doc_headers] + doc_rows
        doc_table = Table(doc_table_data, colWidths=[2*inch, 1.5*inch, 2*inch])
        doc_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(doc_table)
        story.append(Spacer(1, 24))
        
        # PAGE 5-7: ATTACHED DOCUMENTS
        story.append(Paragraph("ATTACHED DOCUMENTS", header_style))
        story.append(Spacer(1, 12))
        
        storage_client = get_service_client().storage
        
        for doc_name, doc_type in required_docs_list:
            doc = documents.get(doc_type)
            if doc:
                story.append(Paragraph(f"{doc_name}:", normal_style))
                story.append(Spacer(1, 6))
                
                try:
                    # Download file from Supabase Storage
                    file_path = doc.get("file_path")
                    if file_path:
                        # Get file from storage
                        file_data = storage_client.from_("student-documents").download(file_path)
                        
                        # Create image from file data
                        img_buffer = io.BytesIO(file_data)
                        try:
                            img = PILImage.open(img_buffer)
                            
                            # Convert to RGB if necessary
                            if img.mode != 'RGB':
                                img = img.convert('RGB')
                            
                            # Resize to fit page (max width 5 inches, max height 6 inches)
                            img_width, img_height = img.size
                            max_width = 5 * inch
                            max_height = 6 * inch
                            
                            if img_width > max_width or img_height > max_height:
                                ratio = min(max_width / img_width, max_height / img_height)
                                new_width = int(img_width * ratio)
                                new_height = int(img_height * ratio)
                                img = img.resize((new_width, new_height), PILImage.LANCZOS)
                            
                            # Add image to story
                            img_buffer.seek(0)
                            rl_image = Image(img_buffer, width=img.width, height=img.height)
                            story.append(rl_image)
                            story.append(Spacer(1, 12))
                        except Exception as e:
                            story.append(Paragraph(f"[Error loading image: {str(e)}]", normal_style))
                            story.append(Spacer(1, 12))
                except Exception as e:
                    story.append(Paragraph(f"[Error downloading document: {str(e)}]", normal_style))
                    story.append(Spacer(1, 12))
            else:
                story.append(Paragraph(f"{doc_name}: NOT UPLOADED", normal_style))
                story.append(Spacer(1, 12))
        
        # PAGE 8: SYSTEM VERIFICATION
        story.append(Paragraph("SYSTEM VERIFICATION", header_style))
        story.append(Spacer(1, 12))
        
        verification_data = [
            ["Serial Number:", serial_number],
            ["Generated On:", datetime.now().strftime("%d %B %Y %H:%M:%S")],
            ["System Status:", "READY FOR HOD VERIFICATION" if not any(doc not in documents for doc_type in required_docs_list) else "INCOMPLETE"],
            ["Total Units:", str(len(units_data))]
        ]
        
        verification_table = Table(verification_data, colWidths=[2*inch, 4*inch])
        verification_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(verification_table)
        story.append(Spacer(1, 24))
        
        # PAGE 9: SIGNATURE PAGE (LEFT BLANK FOR PHYSICAL USE)
        story.append(Paragraph("OFFICIAL SIGNATURES", header_style))
        story.append(Spacer(1, 12))
        story.append(Paragraph("This form must be signed and stamped by:", normal_style))
        story.append(Spacer(1, 12))
        
        signature_data = [
            ["1. HOD (Head of Department)", "_________________________"],
            ["   Signature & Stamp", ""],
            ["   Date:", "_________________________"],
            ["", ""],
            ["2. Examinations Office", "_________________________"],
            ["   Signature & Stamp", ""],
            ["   Date:", "_________________________"],
            ["", ""],
            ["3. Student Signature", "_________________________"],
            ["   Date:", "_________________________"]
        ]
        
        signature_table = Table(signature_data, colWidths=[3*inch, 3*inch])
        signature_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        story.append(signature_table)
        
        # Build PDF
        doc.build(story)
        
        # Get PDF value
        pdf_value = buffer.getvalue()
        buffer.close()
        
        # Save PDF to Supabase Storage
        pdf_filename = f"exam_bookings/{student_id}_{serial_number}.pdf"
        storage_client.from_("exam-bookings").upload(pdf_filename, pdf_value, {"content-type": "application/pdf"})
        
        # Get public URL
        pdf_url = storage_client.from_("exam-bookings").get_public_url(pdf_filename)
        
        flash(f'Exam booking form generated successfully! Serial Number: {serial_number}', 'success')
        flash('Please download and print the form, then submit to HOD for verification.', 'info')
        
        # Return PDF for download
        response = make_response(pdf_value)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=Exam_Booking_{serial_number}.pdf'
        return response
        
    except ImportError:
        # If reportlab is not installed, fall back to simple message
        flash(f'Exam booking created successfully! Serial Number: {serial_number}', 'success')
        flash('PDF generation requires reportlab library. Please install it: pip install reportlab pillow', 'warning')
        flash('Please download and print the form, then submit to HOD for verification.', 'info')
        return redirect(url_for("student.exam_bookings"))
    except Exception as e:
        flash(f'Error generating PDF: {e}', 'danger')
        flash(f'Exam booking created successfully! Serial Number: {serial_number}', 'success')
        return redirect(url_for("student.exam_bookings"))


@student_bp.route("/exam-bookings/<booking_id>/download")
@student_required
def download_exam_booking(booking_id):
    """Download approved exam booking form."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    booking = (db.table("exam_bookings")
               .select("*, units(name, code), user_profiles!exam_bookings_approved_by_fkey(full_name), user_profiles!exam_bookings_student_id_fkey(full_name, admission_no, classes(name, departments(name)))")
               .eq("id", booking_id)
               .eq("student_id", student_id)
               .single()
               .execute().data)
    
    if not booking:
        abort(404)
    
    if booking["status"] != "approved":
        flash('Only approved bookings can be downloaded.', 'warning')
        return redirect(url_for("student.exam_bookings"))
    
    return render_template("student/exam_booking_form.html", booking=booking)


# ── Marks Viewing ─────────────────────────────────────────────────────────────

@student_bp.route("/marks")
@student_required
def marks():
    """View all marks for the student."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get filter parameters
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    
    # Build query
    query = (db.table("marks")
             .select("*, units(name, code), user_profiles!marks_trainer_id_fkey(full_name), classes(name)")
             .eq("student_id", student_id)
             .eq("year", int(year)))
    
    if term:
        query = query.eq("term", term)
    
    marks_list = query.order("created_at", desc=True).execute().data or []
    
    # Calculate average marks
    if marks_list:
        total_marks = sum(m["marks_obtained"] for m in marks_list)
        average = total_marks / len(marks_list)
    else:
        average = 0
    
    return render_template("student/marks.html",
                          marks=marks_list,
                          year=year,
                          term=term,
                          average=round(average, 2))


# ── Result Slip PDF Download ─────────────────────────────────────────────────────

@student_bp.route("/marks/download-result-slip")
@student_required
def download_result_slip():
    """Download termly academic result slip as PDF."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()
    
    # Get all marks for the student in the selected period
    query = (db.table("marks")
             .select("*, units(name, code), user_profiles!marks_trainer_id_fkey(full_name), classes(name, departments(name))")
             .eq("student_id", student_id)
             .eq("year", int(year)))
    
    if term:
        query = query.eq("term", term)
    
    marks_list = query.order("units(code)", desc=True).execute().data or []
    
    # Get student details
    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data
    
    # Calculate average
    if marks_list:
        total_marks = sum(m["marks_obtained"] for m in marks_list)
        average = total_marks / len(marks_list)
    else:
        average = 0
    
    return render_template("student/result_slip_pdf.html",
                          marks=marks_list,
                          student=student,
                          year=year,
                          term=term,
                          average=round(average, 2))


# ── Portfolio of Evidence (PoE) ───────────────────────────────────────────────

@student_bp.route("/portfolio")
@student_required
def portfolio():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    status_filter = request.args.get("status", "").strip()

    # Get all assessments with unit/class info
    query = (db.table("assessments")
            .select("*, units(name, code), classes(name)")
            .eq("student_id", student_id))
    if status_filter:
        query = query.eq("status", status_filter)
    assessments_list = query.order("uploaded_at", desc=True).execute().data or []

    # Compute counts per status
    all_rows = (db.table("assessments")
               .select("status")
               .eq("student_id", student_id)
               .execute().data or [])
    counts = {"total": len(all_rows), "pending": 0, "approved": 0, "rejected": 0}
    for r in all_rows:
        s = r.get("status")
        if s in counts:
            counts[s] += 1

    # Evidence count + file size formatting per assessment
    import math
    def fmt_size(b):
        if not b: return "0 B"
        b = int(b)
        for u in ["B","KB","MB"]:
            if b < 1024: return f"{b:.1f} {u}"
            b /= 1024
        return f"{b:.1f} GB"

    if assessments_list:
        a_ids = [a["id"] for a in assessments_list]
        ev_rows = (db.table("evidence")
                  .select("assessment_id, id")
                  .in_("assessment_id", a_ids)
                  .execute().data or [])
        ev_map = {}
        for ev in ev_rows:
            ev_map[ev["assessment_id"]] = ev_map.get(ev["assessment_id"], 0) + 1
    else:
        ev_map = {}

    for a in assessments_list:
        a["evidence_count"] = ev_map.get(a["id"], 0)
        a["script_file_size_fmt"] = fmt_size(a.get("script_file_size"))

    # Get enrolled units for upload form (fix: no broken join)
    enrollment = (db.table("enrollments")
                 .select("class_id")
                 .eq("student_id", student_id)
                 .limit(1)
                 .execute().data or [])
    enrolled_units = []
    if enrollment:
        class_id = enrollment[0]["class_id"]
        enrolled_units = (db.table("class_units")
                         .select("*, units(name, code)")
                         .eq("class_id", class_id)
                         .execute().data or [])

    return render_template("student/portfolio.html",
                          assessments=assessments_list,
                          enrolled_units=enrolled_units,
                          status_filter=status_filter,
                          counts=counts,
                          fmt_size=fmt_size)


@student_bp.route("/portfolio/upload", methods=["POST"])
@student_required
def upload_document():
    """Upload a document to portfolio of evidence."""
    db = get_service_client()
    user = current_user()
    
    document_type = request.form.get("document_type")
    document_name = request.form.get("document_name")
    unit_id = request.form.get("unit_id")
    academic_year = request.form.get("academic_year")
    term = request.form.get("term")
    description = request.form.get("description", "")
    
    if not all([document_type, document_name, academic_year]):
        flash("Missing required fields.", "error")
        return redirect(url_for("student.portfolio"))
    
    if 'document_file' not in request.files:
        flash("No file uploaded.", "error")
        return redirect(url_for("student.portfolio"))
    
    file = request.files['document_file']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for("student.portfolio"))
    
    try:
        # Upload file to Supabase Storage — use service client directly
        import uuid
        file_extension = file.filename.split('.')[-1]
        unique_filename = f"{uuid.uuid4()}.{file_extension}"
        storage_path = f"trainee_documents/{user['id']}/{unique_filename}"

        file_data = file.read()
        svc = get_service_client()
        svc.storage.from_("documents").upload(
            path=storage_path,
            file=file_data,
            file_options={"content-type": file.content_type}
        )

        # Get public URL
        import os
        file_url = f"{os.environ.get('SUPABASE_URL','').strip()}/storage/v1/object/public/documents/{storage_path}"

        # Save document record
        db.table("trainee_documents").insert({
            "student_id": user["id"],
            "unit_id": unit_id if unit_id else None,
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
        
        write_audit_log("upload_trainee_document", target=f"type:{document_type}")
        flash("Document uploaded successfully.", "success")
    except Exception as e:
        flash(f"Error uploading document: {e}", "error")
    
    return redirect(url_for("student.portfolio"))


@student_bp.route("/portfolio/delete/<document_id>", methods=["POST"])
@student_required
def delete_document(document_id):
    """Delete a document from portfolio of evidence."""
    db = get_service_client()
    user = current_user()
    
    try:
        # Get document
        document = db.table("trainee_documents").select("*").eq("id", document_id).single().execute().data
        
        if not document or document["student_id"] != user["id"]:
            abort(403)
        
        # Delete from storage — use service client directly
        storage_path = document["file_url"].split("documents/")[-1]
        svc = get_service_client()
        svc.storage.from_("documents").remove([storage_path])
        
        # Delete record
        db.table("trainee_documents").delete().eq("id", document_id).execute()
        
        write_audit_log("delete_trainee_document", target=f"document:{document_id}")
        flash("Document deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting document: {e}", "error")
    
    return redirect(url_for("student.portfolio"))


# ── Industrial Attachment (Dual Training) ───────────────────────────────────────

@student_bp.route("/industrial-attachment")
@student_required
def industrial_attachment():
    """View industrial attachment status and request new attachment."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Check if student is enrolled in any units (dual training eligibility)
    enrolled_units = (db.table("enrollments")
                     .select("*, units(name, code)")
                     .eq("student_id", student_id)
                     .execute().data or [])
    
    if not enrolled_units:
        flash("You must be enrolled in at least one unit to access dual training.", "error")
        return redirect(url_for("student.dashboard"))
    
    # Get student's current attachment
    attachments_res = (db.table("industrial_attachments")
                      .select("*, companies(name, address), units(name, code), mentors(user_profiles(full_name))")
                      .eq("student_id", student_id)
                      .in_("status", ["pending", "approved", "active"])
                      .order("created_at", desc=True)
                      .limit(1)
                      .execute().data)
    
    current_attachment = None
    if attachments_res:
        current_attachment = attachments_res[0]
        mentors_obj = current_attachment.get("mentors") or {}
        user_profiles_obj = mentors_obj.get("user_profiles") or {}
        current_attachment["mentor_name"] = user_profiles_obj.get("full_name")
    
    # Get available companies
    companies = (db.table("companies")
                 .select("*")
                 .eq("is_active", True)
                 .gt("available_slots", 0)
                 .execute().data or [])
    
    # Get today's check-in logs for active attachment
    today_logs = []
    if current_attachment and current_attachment.get("status") == "active":
        today_logs = (db.table("location_logs")
                     .select("*")
                     .eq("student_id", student_id)
                     .eq("attachment_id", current_attachment["id"])
                     .gte("check_in_time", datetime.now().strftime("%Y-%m-%d"))
                     .order("check_in_time", desc=True)
                     .execute().data or [])
    
    return render_template("student/industrial_attachment.html",
                          current_attachment=current_attachment,
                          enrolled_units=enrolled_units,
                          companies=companies,
                          today_logs=today_logs)


@student_bp.route("/industrial-attachment/request", methods=["POST"])
@student_required
def request_attachment():
    """Request a new industrial attachment placement."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    company_id = request.form.get("company_id")
    unit_id = request.form.get("unit_id")
    start_date = request.form.get("start_date")
    end_date = request.form.get("end_date")
    attachment_goals = request.form.get("attachment_goals", "")
    learning_objectives = request.form.get("learning_objectives", "")
    
    if not all([company_id, unit_id, start_date, end_date]):
        flash("Company, unit, start date, and end date are required.", "error")
        return redirect(url_for("student.industrial_attachment"))
    
    try:
        db.table("industrial_attachments").insert({
            "student_id": student_id,
            "company_id": company_id,
            "unit_id": unit_id,
            "start_date": start_date,
            "end_date": end_date,
            "status": "pending",
            "attachment_goals": attachment_goals,
            "learning_objectives": learning_objectives,
            "created_by": user["id"]
        }).execute()
        
        write_audit_log("request_attachment", target=f"company:{company_id}")
        flash("Attachment request submitted successfully.", "success")
    except Exception as e:
        flash(f"Error submitting attachment request: {e}", "error")
    
    return redirect(url_for("student.industrial_attachment"))


# ── GPS Check-in/Check-out (Dual Training) ─────────────────────────────────────

@student_bp.route("/check-in", methods=["POST"])
@student_required
def check_in():
    """Check-in at company location using GPS."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    attachment_id = request.form.get("attachment_id")
    latitude = request.form.get("latitude")
    longitude = request.form.get("longitude")
    accuracy_meters = request.form.get("accuracy_meters")
    location_method = request.form.get("location_method", "gps")
    device_info = request.form.get("device_info", "")
    
    if not all([attachment_id, latitude, longitude]):
        flash("Attachment ID and location coordinates are required.", "error")
        return redirect(url_for("student.industrial_attachment"))
    
    try:
        # Get attachment and verify it belongs to student
        attachment = (db.table("industrial_attachments")
                     .select("*, companies(latitude, longitude, geofence_radius_meters)")
                     .eq("id", attachment_id)
                     .eq("student_id", student_id)
                     .eq("status", "active")
                     .single()
                     .execute().data)
        
        if not attachment:
            flash("Active attachment not found or you don't have permission.", "error")
            return redirect(url_for("student.industrial_attachment"))
        
        company = attachment.get("companies", {})
        company_lat = company.get("latitude")
        company_lon = company.get("longitude")
        geofence_radius = company.get("geofence_radius_meters", 300)
        
        # Calculate distance (simplified Haversine formula)
        import math
        lat1, lon1 = float(latitude), float(longitude)
        lat2, lon2 = float(company_lat), float(company_lon)
        
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        distance_meters = 6371000 * c  # Earth's radius in meters
        
        is_within_geofence = distance_meters <= geofence_radius
        
        # Check if there's an active check-in without check-out
        active_log = (db.table("location_logs")
                     .select("*")
                     .eq("student_id", student_id)
                     .eq("attachment_id", attachment_id)
                     .is_("check_out_time", None)
                     .order("check_in_time", desc=True)
                     .limit(1)
                     .execute().data)
        
        if active_log:
            flash("You already have an active check-in. Please check-out first.", "warning")
            return redirect(url_for("student.industrial_attachment"))
        
        # Create location log
        db.table("location_logs").insert({
            "student_id": student_id,
            "attachment_id": attachment_id,
            "latitude": lat1,
            "longitude": lon1,
            "accuracy_meters": float(accuracy_meters) if accuracy_meters else None,
            "is_within_geofence": is_within_geofence,
            "location_method": location_method,
            "device_info": device_info
        }).execute()
        
        write_audit_log("check_in", target=f"attachment:{attachment_id}")
        
        if is_within_geofence:
            flash("Check-in successful. You are within the company geofence.", "success")
        else:
            flash(f"Check-in recorded but you are outside the geofence ({distance_meters:.0f}m from company).", "warning")
    except Exception as e:
        flash(f"Error during check-in: {e}", "error")
    
    return redirect(url_for("student.industrial_attachment"))


@student_bp.route("/check-out", methods=["POST"])
@student_required
def check_out():
    """Check-out from company location."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    attachment_id = request.form.get("attachment_id")
    
    if not attachment_id:
        flash("Attachment ID is required.", "error")
        return redirect(url_for("student.industrial_attachment"))
    
    try:
        # Verify attachment belongs to student and is active
        attachment = (db.table("industrial_attachments")
                     .select("*")
                     .eq("id", attachment_id)
                     .eq("student_id", student_id)
                     .eq("status", "active")
                     .single()
                     .execute().data)
        
        if not attachment:
            flash("Active attachment not found or you don't have permission.", "error")
            return redirect(url_for("student.industrial_attachment"))
        
        # Get active check-in
        active_log = (db.table("location_logs")
                     .select("*")
                     .eq("student_id", student_id)
                     .eq("attachment_id", attachment_id)
                     .is_("check_out_time", None)
                     .order("check_in_time", desc=True)
                     .limit(1)
                     .execute().data)
        
        if not active_log:
            flash("No active check-in found.", "warning")
            return redirect(url_for("student.industrial_attachment"))
        
        # Update with check-out time
        db.table("location_logs").update({
            "check_out_time": datetime.now().isoformat()
        }).eq("id", active_log[0]["id"]).execute()
        
        write_audit_log("check_out", target=f"attachment:{attachment_id}")
        flash("Check-out successful.", "success")
    except Exception as e:
        flash(f"Error during check-out: {e}", "error")
    
    return redirect(url_for("student.industrial_attachment"))


# ── Digital Logbook (Dual Training) ───────────────────────────────────────────

@student_bp.route("/logbook")
@student_required
def logbook():
    """View and manage digital logbook entries."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get student's active attachment
    active_attachment = (db.table("industrial_attachments")
                       .select("*, companies(name)")
                       .eq("student_id", student_id)
                       .eq("status", "active")
                       .single()
                       .execute().data)
    
    if not active_attachment:
        flash("You must have an active industrial attachment to access the digital logbook.", "error")
        return redirect(url_for("student.industrial_attachment"))
    
    # Get logbook entries for this attachment
    logbooks = (db.table("digital_logbook")
               .select("*")
               .eq("student_id", student_id)
               .eq("attachment_id", active_attachment["id"])
               .order("log_date", desc=True)
               .execute().data or [])
    
    return render_template("student/logbook.html",
                          attachment=active_attachment,
                          logbooks=logbooks)


@student_bp.route("/logbook/add", methods=["POST"])
@student_required
def add_logbook():
    """Add a new logbook entry."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    attachment_id = request.form.get("attachment_id")
    log_date = request.form.get("log_date")
    tasks_performed = request.form.get("tasks_performed")
    skills_applied = request.form.get("skills_applied", "")
    hours_worked = request.form.get("hours_worked")
    challenges_encountered = request.form.get("challenges_encountered", "")
    achievements = request.form.get("achievements", "")
    
    if not all([attachment_id, log_date, tasks_performed]):
        flash("Attachment, date, and tasks performed are required.", "error")
        return redirect(url_for("student.logbook"))

    evidence_paths = []
    files = request.files.getlist("evidence")
    for file in files:
        if file and file.filename:
            ext = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else ""
            if ext in {"jpg", "jpeg", "png", "webp", "pdf", "mp4", "mov", "avi", "webm", "mp3", "wav", "ogg", "m4a"}:
                filename = f"logbook/{student_id}_{uuid.uuid4().hex}.{ext}"
                file_data = file.read()
                get_service_client().storage.from_("assessment-evidence").upload(
                    filename, file_data, {"content-type": f"image/{ext}" if ext in ("jpg","jpeg","png","webp") else "application/pdf" if ext == "pdf" else f"video/{ext}" if ext in ("mp4","mov","avi","webm") else f"audio/{ext}"}
                )
                evidence_paths.append(filename)

    try:
        db.table("digital_logbook").insert({
            "student_id": student_id,
            "attachment_id": attachment_id,
            "log_date": log_date,
            "tasks_performed": tasks_performed,
            "skills_applied": skills_applied,
            "hours_worked": float(hours_worked) if hours_worked else None,
            "challenges_encountered": challenges_encountered,
            "achievements": achievements,
            "evidence_urls": evidence_paths if evidence_paths else None,
            "mentor_approval_status": "pending"
        }).execute()

        write_audit_log("add_logbook", target=f"attachment:{attachment_id}")
        flash("Logbook entry added successfully.", "success")
    except Exception as e:
        flash(f"Error adding logbook entry: {e}", "error")

    return redirect(url_for("student.logbook"))


# ── My Job Applications ──────────────────────────────────────────────────────

@student_bp.route("/jobs")
@student_required
def my_jobs():
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    apps = (db.table("job_applications")
            .select("*, job_postings(title, company, type, location)")
            .eq("student_id", student_id)
            .order("created_at", desc=True)
            .execute().data or [])
    return render_template("student/jobs.html", applications=apps)


# ── Post-Training Employment Tracking ─────────────────────────────────────────

@student_bp.route("/employment-status", methods=["GET", "POST"])
@student_required
def employment_status():
    """Update and view post-training employment status."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    if request.method == "POST":
        employment_status = request.form.get("employment_status")
        company_name = request.form.get("company_name", "").strip()
        job_title = request.form.get("job_title", "").strip()
        start_date = request.form.get("start_date")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        location_address = request.form.get("location_address", "").strip()

        if not employment_status:
            flash("Employment status is required.", "error")
            return redirect(url_for("student.employment_status"))

        try:
            # Check if employment record exists
            existing = (db.table("employment_tracking")
                       .select("*")
                       .eq("student_id", student_id)
                       .execute().data or [])

            update_data = {
                "employment_status": employment_status,
                "company_name": company_name if employment_status == "employed" else None,
                "job_title": job_title if employment_status == "employed" else None,
                "start_date": start_date if employment_status == "employed" else None,
                "latitude": float(latitude) if latitude else None,
                "longitude": float(longitude) if longitude else None,
                "location_address": location_address,
                "updated_at": datetime.now().isoformat()
            }

            if existing:
                db.table("employment_tracking").update(update_data).eq("id", existing[0]["id"]).execute()
            else:
                update_data["student_id"] = student_id
                db.table("employment_tracking").insert(update_data).execute()

            write_audit_log("update_employment_status", target=f"student:{student_id}")
            flash("Employment status updated successfully.", "success")
        except Exception as e:
            flash(f"Error updating employment status: {e}", "error")

        return redirect(url_for("student.employment_status"))

    # Get current employment status
    employment_record = (db.table("employment_tracking")
                        .select("*")
                        .eq("student_id", student_id)
                        .execute().data or [])

    current_status = employment_record[0] if employment_record else None

    # Get project uploads
    projects = (db.table("employment_projects")
               .select("*")
               .eq("student_id", student_id)
               .order("created_at", desc=True)
               .execute().data or [])

    return render_template("student/employment_status.html",
                          current_status=current_status,
                          projects=projects)


@student_bp.route("/employment-projects", methods=["GET", "POST"])
@student_required
def employment_projects():
    """Upload and manage post-training project evidence."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        description = request.form.get("description", "").strip()
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        location_address = request.form.get("location_address", "").strip()

        if not project_name:
            flash("Project name is required.", "error")
            return redirect(url_for("student.employment_projects"))

        try:
            # Handle file uploads
            evidence_paths = []
            files = request.files.getlist("project_files")
            for file in files:
                if file and file.filename:
                    ext = file.filename.rsplit(".", 1)[1].lower() if "." in file.filename else ""
                    if ext in {"jpg", "jpeg", "png", "webp", "pdf", "mp4", "mov", "avi", "webm", "mp3", "wav", "ogg", "m4a"}:
                        filename = f"employment_projects/{student_id}_{uuid.uuid4().hex}.{ext}"
                        file_data = file.read()
                        get_service_client().storage.from_("assessment-evidence").upload(
                            filename, file_data, {"content-type": f"image/{ext}" if ext in ("jpg","jpeg","png","webp") else "application/pdf" if ext == "pdf" else f"video/{ext}" if ext in ("mp4","mov","avi","webm") else f"audio/{ext}"}
                        )
                        evidence_paths.append(filename)

            db.table("employment_projects").insert({
                "student_id": student_id,
                "project_name": project_name,
                "description": description,
                "latitude": float(latitude) if latitude else None,
                "longitude": float(longitude) if longitude else None,
                "location_address": location_address,
                "evidence_urls": evidence_paths if evidence_paths else None,
                "created_at": datetime.now().isoformat()
            }).execute()

            write_audit_log("upload_employment_project", target=f"student:{student_id}")
            flash("Project uploaded successfully.", "success")
        except Exception as e:
            flash(f"Error uploading project: {e}", "error")

        return redirect(url_for("student.employment_projects"))

    projects = (db.table("employment_projects")
               .select("*")
               .eq("student_id", student_id)
               .order("created_at", desc=True)
               .execute().data or [])

    return render_template("student/employment_projects.html", projects=projects)


@student_bp.route("/employment-projects/<project_id>/delete", methods=["POST"])
@student_required
def delete_employment_project(project_id):
    """Delete an employment project."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    try:
        project = db.table("employment_projects").select("*").eq("id", project_id).eq("student_id", student_id).single().execute().data

        if not project:
            abort(403)

        # Delete evidence files from storage
        if project.get("evidence_urls"):
            for url in project["evidence_urls"]:
                try:
                    storage_path = url.split("assessment-evidence/")[-1]
                    get_service_client().storage.from_("assessment-evidence").remove([storage_path])
                except Exception:
                    pass

        # Delete project record
        db.table("employment_projects").delete().eq("id", project_id).execute()

        write_audit_log("delete_employment_project", target=f"project:{project_id}")
        flash("Project deleted successfully.", "success")
    except Exception as e:
        flash(f"Error deleting project: {e}", "error")

    return redirect(url_for("student.employment_projects"))
