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
ALLOWED_ATTACHMENT_LETTER_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}


def _file_slug(text: str) -> str:
    """Sanitize arbitrary text into a filename-safe slug (alphanumeric + underscore)."""
    text = str(text or "").strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s]+', '_', text)
    return text.strip('_-') or 'unknown'


def _upload_attachment_letter(file, student_id: str, company_name: str) -> tuple[str, str]:
    """Upload an official attachment acceptance letter and return its public URL + storage path."""
    if not file or not getattr(file, "filename", ""):
        raise ValueError("Please upload the official company acceptance letter.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_ATTACHMENT_LETTER_EXTENSIONS:
        raise ValueError("Acceptance letter must be a PDF, JPG, JPEG, or PNG file.")

    storage_path = (
        f"industrial_attachment_letters/{student_id}/"
        f"{uuid.uuid4()}_{_file_slug(company_name)}.{ext}"
    )
    raw = file.read()
    if not raw:
        raise ValueError("The acceptance letter file appears to be empty.")

    bucket = "assessment-scripts"
    get_service_client().storage.from_(bucket).upload(
        path=storage_path,
        file=raw,
        file_options={
            "content-type": file.content_type or "application/octet-stream",
            "content-disposition": "inline",
        },
    )
    base_url = os.environ.get("SUPABASE_URL", "").strip()
    return f"{base_url}/storage/v1/object/public/{bucket}/{storage_path}", storage_path

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

from routes.attachment_helpers import (
    student_can_submit_placement, get_open_period, upload_placement_document,
    notify_liaison_officers, placement_status_label, attachment_periods_exist,
)


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

_DOC_MIME = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'png': 'image/png',  'webp': 'image/webp',
    'gif': 'image/gif',  'pdf':  'application/pdf',
}

_ALL_DOC_TYPES = [
    'passport_photo', 'admission_letter', 'medical_form', 'personal_data_form',
    'declaration_form', 'kcse_result_slip', 'kcse_certificate', 'kcpe_result_slip',
    'birth_certificate', 'national_id', 'guardian_id', 'consent_form',
    'most_recent_result_slip',
]


@student_bp.route("/documents", methods=["GET", "POST"])
@student_required
def my_documents():
    db       = get_service_client()
    user     = current_user()
    student_id = user["id"]

    if request.method == "POST":
        form_action = request.form.get("form_action", "documents")

        # ── Personal info update ──────────────────────────────────────────────
        if form_action == "update_profile":
            mobile_raw = request.form.get("mobile_number", "").strip()
            mobile     = _clean_mobile_number(mobile_raw) if mobile_raw else ""
            updates = {
                "gender":         request.form.get("gender", "").strip() or None,
                "mobile_number":  mobile or None,
                "national_id_no": request.form.get("national_id_no", "").strip() or None,
                "date_of_birth":  request.form.get("date_of_birth", "").strip() or None,
                "county":         request.form.get("county", "").strip() or None,
                "sub_county":     request.form.get("sub_county", "").strip() or None,
                "village":        request.form.get("village", "").strip() or None,
            }
            updates = {k: v for k, v in updates.items() if v is not None}
            try:
                db.table("user_profiles").update(updates).eq("id", student_id).execute()
                write_audit_log("update_profile", target=f"user:{student_id}", detail=updates)
                flash("Personal information updated successfully.", "success")
            except Exception as e:
                err_msg = str(e)
                if "PGRST204" in err_msg or "schema cache" in err_msg:
                    bad = re.search(r"'(\w+)' column", err_msg)
                    safe = {k: v for k, v in updates.items()
                            if k in ("mobile_number","gender","date_of_birth",
                                     "national_id_no","county","sub_county","village")}
                    if bad:
                        safe.pop(bad.group(1), None)
                    try:
                        if safe:
                            db.table("user_profiles").update(safe).eq("id", student_id).execute()
                            flash("Profile updated (some fields need a DB migration).", "warning")
                        else:
                            flash("Profile could not be saved — DB migration required.", "warning")
                    except Exception as e2:
                        flash(f"Error updating profile: {e2}", "danger")
                else:
                    flash(f"Error updating profile: {e}", "danger")
            return redirect(url_for("student.my_documents"))

        # ── Document uploads ──────────────────────────────────────────────────
        uploaded_count = 0
        upload_errors  = []
        storage        = db.storage  # reuse same client

        for doc_type in _ALL_DOC_TYPES:
            file = request.files.get(doc_type)
            if not file or not file.filename:
                continue

            doc_label = doc_type.replace("_", " ").title()
            try:
                ext          = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "pdf"
                storage_path = f"trainee_documents/{student_id}_{doc_type}_{uuid.uuid4().hex}.{ext}"
                file_bytes   = file.read()
                content_type = _DOC_MIME.get(ext, "application/octet-stream")

                storage.from_("assessment-evidence").upload(
                    storage_path, file_bytes,
                    {"content-type": content_type, "x-upsert": "true"}
                )
                public_url = storage.from_("assessment-evidence").get_public_url(storage_path)

                existing = (db.table("student_personal_documents")
                              .select("id")
                              .eq("student_id", student_id)
                              .eq("document_type", doc_type)
                              .limit(1)
                              .execute().data or [])

                payload = {
                    "document_name": doc_label,
                    "file_url":      public_url,
                    "file_path":     storage_path,
                    "file_name":     file.filename,
                    "file_size":     len(file_bytes),
                    "status":        "pending",
                }
                if existing:
                    db.table("student_personal_documents").update(payload)\
                      .eq("id", existing[0]["id"]).execute()
                else:
                    db.table("student_personal_documents").insert(
                        {"student_id": student_id, "document_type": doc_type, **payload}
                    ).execute()

                uploaded_count += 1

            except Exception as e:
                upload_errors.append(f"{doc_label}: {e}")

        for err in upload_errors:
            flash(err, "danger")
        if uploaded_count:
            write_audit_log("upload_documents", target=f"user:{student_id}",
                            detail={"count": uploaded_count})
            flash(f"{uploaded_count} document(s) uploaded successfully.", "success")
        elif not upload_errors:
            flash("No files were selected.", "warning")

        return redirect(url_for("student.my_documents"))

    # ── GET ───────────────────────────────────────────────────────────────────
    student    = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}
    enrollment = db.table("enrollments").select("*, classes(name, course_id)")\
                   .eq("student_id", student_id).execute().data or []

    course_name = department_name = ""
    if enrollment:
        cls = enrollment[0].get("classes") or {}
        cid = cls.get("course_id")
        if cid:
            course = db.table("courses").select("*, departments(name)")\
                       .eq("id", cid).single().execute().data or {}
            course_name     = course.get("name", "")
            department_name = (course.get("departments") or {}).get("name", "")

    docs_raw  = db.table("student_personal_documents").select("*")\
                  .eq("student_id", student_id)\
                  .order("updated_at", desc=True)\
                  .execute().data or []
    documents      = {d["document_type"]: d for d in docs_raw}   # dict for upload-card lookups
    documents_list = docs_raw                                      # ordered list for gallery

    return render_template(
        "student/my_documents.html",
        student=student,
        course_name=course_name,
        department_name=department_name,
        documents=documents,
        documents_list=documents_list,
        total_doc_types=len(_ALL_DOC_TYPES),
    )


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
        assessment_type = (request.form.get("assessment_type") or "").upper()
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
        
        # Fetch admission_no and unit name once — used for structured filenames
        _profile = (db.table("user_profiles").select("admission_no")
                    .eq("id", student_id).single().execute().data or {})
        _unit_row = (db.table("units").select("name")
                     .eq("id", unit_id).single().execute().data or {})
        adm_slug  = _file_slug(_profile.get("admission_no") or student_id)
        unit_slug = _file_slug(_unit_row.get("name") or unit_id)
        # Format: admission_no-unitname-assessmenttype-assessmentno-cycle-term
        base_name = f"{adm_slug}-{unit_slug}-{assessment_type}-{assessment_no}-{cycle}-{term}"

        pdf_files = [f for f in files if f.filename.lower().endswith('.pdf')]
        multi_pdf = len(pdf_files) > 1

        uploaded = 0
        errors = []
        pdf_idx = 0
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                errors.append(f"'{file.filename}' is not a PDF — skipped.")
                continue
            pdf_idx += 1
            try:
                page_sfx     = f"-p{pdf_idx}" if multi_pdf else ""
                display_name = f"{base_name}{page_sfx}.pdf"
                storage_path = f"scripts/{student_id}/{display_name}"
                file_data = file.read()
                get_service_client().storage.from_("assessment-scripts").upload(
                    storage_path, file_data, {"content-type": "application/pdf"}
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
                    "script_file_path": storage_path,
                    "script_file_name": display_name,
                    "script_file_size": len(file_data),
                    "status": "pending"
                }).execute()
                write_audit_log("upload_assessment", target=f"assessment:{result.data[0]['id']}")
                # Notify the assigned trainer for this unit/class
                try:
                    cu = db.table("class_units").select("trainer_id").eq("class_id", class_id).eq("unit_id", unit_id).execute().data
                    if cu and cu[0].get("trainer_id"):
                        from notifications import notify_assessment_submitted
                        notify_assessment_submitted(student_id, f"{assessment_type} #{assessment_no}", cu[0]["trainer_id"])
                except Exception:
                    pass
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

        # Build structured evidence filename: adm-unit-type-no-cycle-term-ev{n}.ext
        _eprof = (db.table("user_profiles").select("admission_no")
                  .eq("id", student_id).single().execute().data or {})
        _adm_slug  = _file_slug(_eprof.get("admission_no") or student_id)
        _unit_slug = _file_slug((assessment.get("units") or {}).get("name") or "unit")
        _atype_s   = _file_slug(assessment.get("assessment_type") or "FA")
        _ano       = str(assessment.get("assessment_no") or "1")
        _cyc       = str(assessment.get("cycle") or "1")
        _trm       = str(assessment.get("term") or "1")
        _ev_num    = len(evidence_list) + 1
        _base_ev   = f"{_adm_slug}-{_unit_slug}-{_atype_s}-{_ano}-{_cyc}-{_trm}-ev{_ev_num}"

        try:
            display_ev_name = f"{_base_ev}.{ext}"
            filename = f"evidence/{student_id}/{display_ev_name}"
            file_data = file.read()
            get_service_client().storage.from_("assessment-evidence").upload(
                filename, file_data, {"content-type": content_type}
            )
            db.table("evidence").insert({
                "assessment_id": assessment_id,
                "student_id": student_id,
                "file_path": filename,
                "file_name": display_ev_name,
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
    """Render the printable HTML attendance report for a unit."""
    from datetime import date as _date

    db         = get_service_client()
    user       = current_user()
    student_id = user["id"]
    unit_id    = request.args.get("unit_id")

    if not unit_id:
        flash("Unit ID is required.", "error")
        return redirect(url_for("student.dashboard"))

    unit    = db.table("units").select("*").eq("id", unit_id).single().execute().data or {}
    student = (db.table("user_profiles")
               .select("full_name, admission_no")
               .eq("id", student_id).single().execute().data or {})

    records = (db.table("attendance")
               .select("*")
               .eq("student_id", student_id)
               .eq("unit_id", unit_id)
               .order("attendance_date", desc=False)
               .execute().data or [])

    total   = len(records)
    present = sum(1 for r in records if r.get("status") == "present")
    absent  = total - present
    pct     = round(present / total * 100, 1) if total > 0 else 0

    # Resolve class & department from the student's enrollment
    info = {"class_name": "", "dept_name": ""}
    try:
        enr = (db.table("enrollments")
               .select("classes(name, departments(name))")
               .eq("student_id", student_id)
               .limit(1).execute().data or [])
        if enr:
            cls  = (enr[0].get("classes") or {})
            dept = (cls.get("departments") or {})
            info["class_name"] = cls.get("name", "")
            info["dept_name"]  = dept.get("name", "")
    except Exception:
        pass

    term_label = {1: "Term 1", 2: "Term 2", 3: "Term 3"}
    date_gen   = _date.today().strftime("%d %B %Y")

    return render_template(
        "student/unit_report_pdf.html",
        unit=unit,
        student=student,
        records=records,
        attended=present,
        absent=absent,
        total=total,
        pct=pct,
        info=info,
        term_label=term_label,
        date_gen=date_gen,
    )


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
            
            # Generate clean filename: admission_no-unitname-type-no-cycle-term
            clean_filename = (
                f"{_file_slug(admission_no)}-{_file_slug(unit_name)}"
                f"-{_file_slug(assessment_type)}-{assessment_no}-{cycle}-{term}{orig_ext}"
            )

            # Create storage path: POE/CLASS/UNIT/ADMISSION_NO/
            storage_path = f"POE/{_file_slug(class_name)}/{_file_slug(unit_name)}/{_file_slug(admission_no)}/{clean_filename}"
            
            # Read file data
            file_data = file.read()
            
            # Upload to Supabase Storage
            storage_client.from_("assessment-evidence").upload(storage_path, file_data, {
                "content-type": file.content_type,
                "upsert": "true"
            })
            
            # Get public URL
            public_url = storage_client.from_("assessment-evidence").get_public_url(storage_path)
            
            # Save to database using the correct assessments schema
            assessment_data = {
                "student_id": student_id,
                "unit_id": None,
                "assessment_type": assessment_type,
                "assessment_no": assessment_no,
                "status": "pending",
                "script_file_path": storage_path,
                "script_file_name": clean_filename,
            }

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
    """View all exam bookings for the student, grouped by serial number (submission batch)."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    bookings = (db.table("exam_bookings")
                .select("*, units(name, code), user_profiles!exam_bookings_approved_by_fkey(full_name)")
                .eq("student_id", student_id)
                .order("created_at", desc=True)
                .execute().data or [])

    # Group by serial_number so all units submitted together show as one form
    from collections import OrderedDict
    groups = OrderedDict()
    for b in bookings:
        sn = b.get("serial_number") or b["id"]
        if sn not in groups:
            groups[sn] = {
                "serial_number": sn,
                "created_at":    b.get("created_at", ""),
                "exam_session":  b.get("exam_session", ""),
                "status":        b.get("status", "pending"),
                "approved_at":   b.get("approved_at", ""),
                "rejection_reason": b.get("rejection_reason", ""),
                "reviewer":      (b.get("user_profiles") or {}).get("full_name", ""),
                "bookings":      [],
            }
        groups[sn]["bookings"].append(b)

    return render_template("student/exam_bookings.html",
                           booking_groups=list(groups.values()))


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
    # Include id in the classes join so class_id is available
    enrollment = db.table("enrollments").select("*, classes(id, name, course_id)").eq("student_id", student_id).execute().data or []
    course_name = ""
    department_name = ""
    class_id = None

    if enrollment:
        class_data = enrollment[0].get("classes") or {}
        # Use FK directly from enrollment row — most reliable source
        class_id = enrollment[0].get("class_id") or class_data.get("id")
        course_id = class_data.get("course_id")
        if course_id:
            course = db.table("courses").select("*, departments(name)").eq("id", course_id).single().execute().data or {}
            course_name = course.get("name", "")
            department_name = (course.get("departments") or {}).get("name", "")

    # Get units for the student's class
    # Include id in the units join so unit IDs are available for marks lookup
    units = []
    if class_id:
        cu_rows = (db.table("class_units")
                   .select("*, units(id, name, code)")
                   .eq("class_id", class_id)
                   .execute().data or [])
        units = cu_rows

    # Fetch most recent marks per unit — used to pre-fill attempt type
    marks_by_unit = {}
    if units:
        unit_ids = [u["units"]["id"] for u in units if u.get("units") and u["units"].get("id")]
        if unit_ids:
            try:
                all_marks = (db.table("marks")
                               .select("id, unit_id, grade, marks_obtained, term, year")
                               .eq("student_id", student_id)
                               .in_("unit_id", unit_ids)
                               .order("year", desc=True)
                               .order("created_at", desc=True)
                               .execute().data or [])
                for m in all_marks:
                    uid = m["unit_id"]
                    if uid not in marks_by_unit:
                        marks_by_unit[uid] = m
            except Exception:
                pass

    # Get uploaded documents — source: student_personal_documents (My Documents menu)
    documents_data = db.table("student_personal_documents").select("*").eq("student_id", student_id).execute().data or []
    documents = {doc["document_type"]: doc for doc in documents_data}

    # Check required documents
    required_docs = ['national_id', 'birth_certificate', 'kcse_certificate', 'passport_photo']
    missing_documents = any(doc not in documents for doc in required_docs)

    # Check if can download (all docs present + at least one unit selected)
    can_download = not missing_documents and len(units) > 0

    # Fetch existing exam bookings so they appear on the same page
    existing_bookings = (db.table("exam_bookings")
                         .select("*, units(name, code), user_profiles!exam_bookings_approved_by_fkey(full_name)")
                         .eq("student_id", student_id)
                         .order("created_at", desc=True)
                         .limit(20)
                         .execute().data or [])

    return render_template("student/exam_booking_new.html",
                          student=student,
                          course_name=course_name,
                          department_name=department_name,
                          units=units,
                          documents=documents,
                          missing_documents=missing_documents,
                          can_download=can_download,
                          existing_bookings=existing_bookings,
                          marks_by_unit=marks_by_unit)


def _build_exam_booking_pdf(student: dict, course_name: str, course_code: str,
                             department_name: str, units_data: list,
                             serial_number: str, year: str, series: str, term: str,
                             form_data: dict = None,
                             documents: dict = None,
                             storage_client=None) -> bytes:
    """
    Generate the TTTI Regular Candidate Assessment Registration Form 1A PDF.
    Layout matches the physical printed form exactly.
    If documents + storage_client are provided, the uploaded supporting documents
    (National ID, Birth Certificate, KCSE Certificate / Result Slip) are appended
    as additional pages to produce one complete, self-contained PDF.
    Returns raw PDF bytes.
    """
    import io as _io, os as _os
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch, mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle, HRFlowable, Image as RLImage)
    from PIL import Image as PILImage

    fd = form_data or {}

    # ── Page geometry ────────────────────────────────────────────────────────
    buf = _io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=14*mm,  bottomMargin=14*mm,
    )
    W = A4[0] - 36*mm   # usable width

    # ── Styles ───────────────────────────────────────────────────────────────
    base   = getSampleStyleSheet()
    bold11 = ParagraphStyle('b11', parent=base['Normal'], fontSize=11,
                            fontName='Helvetica-Bold')
    bold10 = ParagraphStyle('b10', parent=base['Normal'], fontSize=10,
                            fontName='Helvetica-Bold')
    norm9  = ParagraphStyle('n9',  parent=base['Normal'], fontSize=9,
                            fontName='Helvetica')
    norm8  = ParagraphStyle('n8',  parent=base['Normal'], fontSize=8,
                            fontName='Helvetica')
    title  = ParagraphStyle('ttl', parent=base['Normal'], fontSize=13,
                            fontName='Helvetica-Bold', alignment=TA_CENTER,
                            spaceAfter=1)
    sub    = ParagraphStyle('sub', parent=base['Normal'], fontSize=11,
                            fontName='Helvetica-Bold', alignment=TA_CENTER,
                            spaceAfter=1)
    ref_s  = ParagraphStyle('ref', parent=base['Normal'], fontSize=9,
                            fontName='Helvetica', alignment=TA_CENTER,
                            spaceAfter=4)
    label_s = ParagraphStyle('lbl', parent=base['Normal'], fontSize=9,
                              fontName='Helvetica', leading=12)
    value_s = ParagraphStyle('val', parent=base['Normal'], fontSize=9,
                              fontName='Helvetica', leading=12)
    sect_s  = ParagraphStyle('sec', parent=base['Normal'], fontSize=9,
                              fontName='Helvetica-Bold', leading=12)

    story = []

    # ── HEADER ────────────────────────────────────────────────────────────────
    logo_path = _os.path.join(_os.path.dirname(__file__), '..', 'static', 'assets', 'THIKATTILOGO.jpg')
    logo_cell = ""
    if _os.path.exists(logo_path):
        try:
            logo_cell = RLImage(logo_path, width=0.85*inch, height=0.85*inch)
        except Exception:
            logo_cell = Paragraph("", norm9)
    else:
        logo_cell = Paragraph("", norm9)

    header_text = [
        Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", title),
        Paragraph("REGULAR CANDIDATE ASSESSMENT REGISTRATION FORM 1A", sub),
        Paragraph("TTTI/EXAMS/CDACC/REG/1A", ref_s),
    ]
    header_tbl = Table(
        [[logo_cell, header_text]],
        colWidths=[1.0*inch, W - 1.0*inch],
    )
    header_tbl.setStyle(TableStyle([
        ('VALIGN',  (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',   (1,0), (1,0),   'CENTER'),
        ('TOPPADDING',    (0,0),(-1,-1), 0),
        ('BOTTOMPADDING', (0,0),(-1,-1), 0),
    ]))
    story.append(header_tbl)
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.black, spaceAfter=4))

    # ── INSTRUCTIONS ─────────────────────────────────────────────────────────
    instructions = [
        "INSTRUCTIONS",
        "Ensure you have registered on the student portal before filling this form.",
        "Attach all required documents listed below.",
        "Submit the completed form to the departmental HOD before the deadline.",
    ]
    for i, line in enumerate(instructions):
        sty = sect_s if i == 0 else norm9
        story.append(Paragraph(line, sty))
    story.append(Spacer(1, 4))

    # ── REQUIRED ATTACHMENTS ─────────────────────────────────────────────────
    story.append(Paragraph("REQUIRED ATTACHMENTS", sect_s))
    for att in [
        "Copy of National ID / Passport",
        "Copy of Birth Certificate",
        "KCSE Certificate (for Module I) or Previous Module Result Slip (continuing students)",
        "Fee Statement showing exam fee payment",
    ]:
        story.append(Paragraph(att, norm9))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=4))

    # ── SECTION 1: CANDIDATE DETAILS ─────────────────────────────────────────
    story.append(Paragraph("SECTION 1: CANDIDATE DETAILS", sect_s))
    story.append(Spacer(1, 3))

    def _frow(lbl, val):
        """Single field row: label | underlined value."""
        return [Paragraph(lbl, label_s), Paragraph(str(val) if val else "", value_s)]

    dob = (fd.get("date_of_birth") or student.get("date_of_birth") or "")
    if dob and len(dob) == 10:  # YYYY-MM-DD → DD/MM/YYYY
        try:
            from datetime import datetime as _dt
            dob = _dt.strptime(dob, "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            pass

    field_rows = [
        _frow("Full Name (as per ID):",       fd.get("full_name")     or student.get("full_name","")),
        _frow("Admission Number:",             student.get("admission_no","")),
        _frow("Gender:",                       fd.get("gender")        or student.get("gender","")),
        _frow("Date of Birth:",                dob),
        _frow("Mobile Number:",                fd.get("mobile_number") or student.get("mobile_number","")),
        _frow("Email Address:",                student.get("email","")),
        _frow("National ID / Birth Cert No.:", fd.get("national_id_no") or student.get("national_id_no","")),
        _frow("Course Code:",                  course_code),
        _frow("Course Name (see overleaf):",   course_name),
        _frow("Module / Level / TEP:",         fd.get("module_level") or student.get("level","")),
        _frow("PWD Status:",                   fd.get("pwd_status")   or student.get("pwd_status","N/A")),
    ]
    lw = 2.2 * inch
    vw = W - lw
    ftbl = Table(field_rows, colWidths=[lw, vw])
    ftbl.setStyle(TableStyle([
        ('FONTNAME',      (0,0),(-1,-1), 'Helvetica'),
        ('FONTSIZE',      (0,0),(-1,-1), 9),
        ('TOPPADDING',    (0,0),(-1,-1), 2),
        ('BOTTOMPADDING', (0,0),(-1,-1), 2),
        ('LINEBELOW',     (1,0),(1,-1), 0.5, colors.black),  # underline value column
        ('VALIGN',        (0,0),(-1,-1), 'BOTTOM'),
    ]))
    story.append(ftbl)
    story.append(Spacer(1, 8))

    # ── SECTION 2: EXAM PERIOD (compact inline) ───────────────────────────────
    series_label = {"1": "MARCH", "2": "JULY", "3": "NOVEMBER"}.get(str(series), f"Series {series}")
    ep_rows = [[
        _frow("Exam Year:", year)[0],   _frow("Exam Year:", year)[1],
        _frow("Series:", series_label)[0], _frow("Series:", series_label)[1],
        _frow("Term:", f"Term {term}")[0], _frow("Term:", f"Term {term}")[1],
    ]]
    ep_tbl = Table(ep_rows, colWidths=[1.1*inch, 1.2*inch, 0.7*inch, 1.5*inch, 0.6*inch, 1.0*inch])
    ep_tbl.setStyle(TableStyle([
        ('FONTNAME',   (0,0),(-1,-1),'Helvetica'),
        ('FONTSIZE',   (0,0),(-1,-1), 9),
        ('TOPPADDING', (0,0),(-1,-1), 2),
        ('BOTTOMPADDING',(0,0),(-1,-1),2),
        ('LINEBELOW',  (1,0),(1,0), 0.5, colors.black),
        ('LINEBELOW',  (3,0),(3,0), 0.5, colors.black),
        ('LINEBELOW',  (5,0),(5,0), 0.5, colors.black),
        ('VALIGN',     (0,0),(-1,-1),'BOTTOM'),
    ]))
    story.append(ep_tbl)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=4))

    # ── SECTION 3: DEPARTMENTAL CLEARANCE ────────────────────────────────────
    story.append(Paragraph("SECTION 3: DEPARTMENTAL CLEARANCE", sect_s))
    story.append(Spacer(1, 3))

    cl_rows = [
        _frow("Department:", department_name),
        _frow("HOD Name:",   ""),
    ]
    cl_tbl = Table(cl_rows, colWidths=[lw, vw])
    cl_tbl.setStyle(TableStyle([
        ('FONTNAME',      (0,0),(-1,-1),'Helvetica'),
        ('FONTSIZE',      (0,0),(-1,-1), 9),
        ('TOPPADDING',    (0,0),(-1,-1), 2),
        ('BOTTOMPADDING', (0,0),(-1,-1), 2),
        ('LINEBELOW',     (1,0),(1,-1), 0.5, colors.black),
        ('VALIGN',        (0,0),(-1,-1),'BOTTOM'),
    ]))
    story.append(cl_tbl)
    story.append(Spacer(1, 3))

    sig_row = [[
        Paragraph("Signature: ___________________________", norm9),
        Paragraph("Date: _______________________________", norm9),
    ]]
    sig_tbl = Table(sig_row, colWidths=[W/2, W/2])
    sig_tbl.setStyle(TableStyle([
        ('TOPPADDING',    (0,0),(-1,-1), 2),
        ('BOTTOMPADDING', (0,0),(-1,-1), 2),
    ]))
    story.append(sig_tbl)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=4))

    # ── UNITS OF COMPETENCY TABLE ─────────────────────────────────────────────
    story.append(Paragraph("UNITS OF COMPETENCY", sect_s))
    story.append(Spacer(1, 3))

    u_header = [
        Paragraph("S/N",                    bold10),
        Paragraph("Unit of Competency",     bold10),
        Paragraph("Unit Type\n(Core/Common/Basic)", bold10),
        Paragraph("Unit Cost\n(Ksh)",       bold10),
    ]
    u_rows   = [u_header]
    total_cost = 0.0
    for i, ud in enumerate(units_data):
        unit = ud.get("unit") or {}
        cost_raw = ud.get("cost") or ""
        try:
            cost_val = float(cost_raw) if cost_raw else 0.0
        except (ValueError, TypeError):
            cost_val = 0.0
        total_cost += cost_val
        cost_str = f"{cost_val:,.2f}" if cost_val else ""
        u_rows.append([
            Paragraph(str(i+1), norm9),
            Paragraph(unit.get("name",""), norm9),
            Paragraph(ud.get("type","Core"), norm9),
            Paragraph(cost_str, norm9),
        ])

    # Pad to at least 8 rows so it looks like the physical form
    while len(u_rows) < 9:
        u_rows.append([Paragraph(str(len(u_rows)), norm9), Paragraph("", norm9),
                       Paragraph("", norm9), Paragraph("", norm9)])

    # Total row
    u_rows.append([
        Paragraph("", norm9),
        Paragraph("TOTAL", bold10),
        Paragraph("", norm9),
        Paragraph(f"{total_cost:,.2f}" if total_cost else "", bold10),
    ])

    col_w = [0.45*inch, W - 0.45*inch - 1.5*inch - 1.1*inch, 1.5*inch, 1.1*inch]
    utbl  = Table(u_rows, colWidths=col_w, repeatRows=1)
    utbl.setStyle(TableStyle([
        ('GRID',         (0,0), (-1,-2), 0.5, colors.black),
        ('LINEBELOW',    (0,-1),(-1,-1), 1.0, colors.black),
        ('LINEABOVE',    (0,-1),(-1,-1), 0.5, colors.black),
        ('BACKGROUND',   (0,0), (-1,0),  colors.HexColor('#E8E8E8')),
        ('FONTNAME',     (0,0), (-1,0),  'Helvetica-Bold'),
        ('FONTSIZE',     (0,0), (-1,-1), 9),
        ('TOPPADDING',   (0,0), (-1,-1), 3),
        ('BOTTOMPADDING',(0,0), (-1,-1), 3),
        ('VALIGN',       (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN',        (0,0), (0,-1),  'CENTER'),
        ('ALIGN',        (3,0), (3,-1),  'RIGHT'),
    ]))
    story.append(utbl)
    story.append(Spacer(1, 6))

    # ── FOOTER: SERIAL NUMBER ─────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=3))
    story.append(Paragraph(f"<b>Serial No:</b> {serial_number}", norm8))

    # ── SUPPORTING DOCUMENT PAGES ─────────────────────────────────────────────
    # Append uploaded documents as extra pages so the download is one complete PDF.
    # Priority order matches the physical form's required attachments list.
    _attach_order = [
        ('national_id',             'COPY OF NATIONAL ID / PASSPORT'),
        ('birth_certificate',       'COPY OF BIRTH CERTIFICATE'),
        ('kcse_certificate',        'KCSE CERTIFICATE (Module I students)'),
        ('kcse_result_slip',        'KCSE RESULT SLIP'),
        ('most_recent_result_slip', 'PREVIOUS MODULE RESULT SLIP (Continuing students)'),
    ]

    pdf_attachments = []   # (label, bytes) for PDF-type documents

    if documents and storage_client:
        from reportlab.platypus import PageBreak
        from PIL import Image as PILImage

        for doc_key, doc_label in _attach_order:
            rec = documents.get(doc_key)
            if not rec or not rec.get('file_path'):
                continue
            fp  = rec['file_path']
            ext = fp.rsplit('.', 1)[-1].lower() if '.' in fp else ''
            try:
                raw = bytes(storage_client.from_("assessment-evidence").download(fp))
            except Exception:
                continue   # skip documents that can't be fetched

            if ext in ('jpg', 'jpeg', 'png', 'webp', 'gif'):
                # Image → embed as a full A4 page inside this story
                try:
                    pimg = PILImage.open(_io.BytesIO(raw))
                    if pimg.mode not in ('RGB', 'L'):
                        pimg = pimg.convert('RGB')
                    max_w = A4[0] - 28*mm
                    max_h = A4[1] - 36*mm     # leave room for the label line
                    iw, ih = pimg.size
                    ratio  = min(max_w / iw, max_h / ih, 1.0)
                    out    = _io.BytesIO()
                    if ratio < 1.0:
                        pimg = pimg.resize((int(iw * ratio), int(ih * ratio)),
                                           PILImage.LANCZOS)
                    pimg.save(out, format='JPEG', quality=92)
                    out.seek(0)

                    story.append(PageBreak())
                    story.append(Paragraph(doc_label, sect_s))
                    story.append(Spacer(1, 6))
                    story.append(RLImage(out,
                                        width=iw * ratio,
                                        height=ih * ratio))
                except Exception as img_err:
                    story.append(PageBreak())
                    story.append(Paragraph(f"{doc_label} — could not embed: {img_err}", norm9))

            elif ext == 'pdf':
                # PDF → keep aside; merge after ReportLab builds the form
                pdf_attachments.append((doc_label, raw))

    # ── Build the ReportLab portion (form + any image attachments) ────────────
    pdf.build(story)
    form_bytes = buf.getvalue()

    # ── Merge any PDF-type attachments ────────────────────────────────────────
    if pdf_attachments:
        try:
            from pypdf import PdfWriter, PdfReader

            writer = PdfWriter()
            writer.append(PdfReader(_io.BytesIO(form_bytes)))

            for doc_label, pdf_raw in pdf_attachments:
                try:
                    writer.append(PdfReader(_io.BytesIO(pdf_raw)))
                except Exception:
                    pass   # corrupt / encrypted PDF — skip silently

            merged = _io.BytesIO()
            writer.write(merged)
            return merged.getvalue()
        except ImportError:
            pass   # pypdf not installed — return form + image pages only

    return form_bytes


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
        flash('Please select at least one unit of competency.', 'danger')
        return redirect(url_for("student.exam_booking_form"))

    # Collect form fields
    form_data = {
        "full_name":     request.form.get("full_name", "").strip(),
        "gender":        request.form.get("gender", "").strip(),
        "date_of_birth": request.form.get("date_of_birth", "").strip(),
        "mobile_number": request.form.get("mobile_number", "").strip(),
        "national_id_no":request.form.get("national_id_no", "").strip(),
        "module_level":  request.form.get("module_level", "").strip(),
        "pwd_status":    request.form.get("pwd_status", "N/A").strip(),
        "exam_year":     request.form.get("exam_year", str(datetime.now().year)),
        "exam_series":   request.form.get("exam_series", "1"),
        "term":          request.form.get("term", "1"),
    }

    # Get student data
    student = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}

    # Get course and department info (include id in classes join)
    enrollment = (db.table("enrollments")
                    .select("*, classes(id, name, course_id)")
                    .eq("student_id", student_id)
                    .execute().data or [])
    course_name = department_name = dept_code = course_code = ""

    if enrollment:
        class_data = enrollment[0].get("classes") or {}
        course_id  = class_data.get("course_id")
        if course_id:
            course = (db.table("courses").select("*, departments(name, code)")
                        .eq("id", course_id).single().execute().data or {})
            course_name     = course.get("name", "")
            course_code     = course.get("code", "GEN")
            dept            = course.get("departments") or {}
            department_name = dept.get("name", "")
            dept_code       = dept.get("code", "GEN")

    # Get unit details for selected units
    units_data = []
    for unit_id in selected_units:
        unit = db.table("units").select("*").eq("id", unit_id).single().execute().data
        if unit:
            units_data.append({
                "unit":      unit,
                "type":      request.form.get(f"unit_type_{unit_id}", "Core"),
                "attempt":   request.form.get(f"attempt_type_{unit_id}", "first_attempt"),
                "prev_grade":request.form.get(f"prev_grade_{unit_id}", "") or None,
                "prev_mid":  request.form.get(f"prev_marks_{unit_id}", "") or None,
                "cost":      request.form.get(f"unit_cost_{unit_id}", "") or None,
            })

    # Get documents from student_personal_documents (My Documents)
    documents_data = (db.table("student_personal_documents")
                        .select("*").eq("student_id", student_id).execute().data or [])
    documents = {doc["document_type"]: doc for doc in documents_data}

    # Build serial number — no slashes (they break storage paths)
    year          = form_data.get("exam_year", str(datetime.now().year))
    series        = form_data.get("exam_series", "1")
    term          = form_data.get("term", "1")
    unique_serial = str(uuid.uuid4().int)[:6].zfill(6)
    serial_number = f"TTTI-{year}-EXAM-{unique_serial}"   # hyphens, never slashes

    # Columns that have check constraints — map to their safe fallback values.
    # If the constraint rejects our value we null the column rather than fail.
    _CONSTRAINED = {
        "exam_session":         None,   # drop if constraint rejects
        "purpose":              None,
        "special_requirements": None,
        "attempt_type":         None,
    }

    def _extract_code(msg: str) -> str:
        """Pull the Postgres/PostgREST error code out of an exception message."""
        try:
            import json as _j
            return _j.loads(msg).get("code", "") if msg.strip().startswith("{") else ""
        except Exception:
            pass
        m = re.search(r"'code':\s*'([^']+)'", msg)
        return m.group(1) if m else ""

    def _insert_strip_bad(payload: dict) -> None:
        """
        Insert a row into exam_bookings, automatically handling:
          PGRST204 — unknown column  → drop it and retry
          23514    — check constraint → drop the offending column and retry
          23505    — duplicate key   → upsert on the natural key columns and retry
        Retries up to 25 times before raising.
        """
        data     = dict(payload)
        seen     = set()
        upserted = False
        for _ in range(25):
            try:
                if upserted:
                    # Use upsert so a re-submission updates the existing row
                    db.table("exam_bookings").upsert(
                        data,
                        on_conflict="student_id,unit_id,exam_date"
                    ).execute()
                else:
                    db.table("exam_bookings").insert(data).execute()
                return
            except Exception as exc:
                msg  = str(exc)
                code = _extract_code(msg)

                if code == "PGRST204":
                    # Unknown column — strip it
                    m = re.search(r"'(\w+)' column", msg)
                    if m:
                        bad = m.group(1)
                        if bad in seen: raise
                        seen.add(bad); data.pop(bad, None); continue

                elif code == "23514":
                    # Check constraint violation
                    m = re.search(r'"exam_bookings_(\w+)_check"', msg)
                    if m:
                        bad = m.group(1)
                        if bad in seen: raise
                        seen.add(bad); data.pop(bad, None); continue
                    # Fallback: strip known constrained cols one by one
                    for col in list(_CONSTRAINED.keys()):
                        if col not in seen and col in data:
                            seen.add(col); data.pop(col, None); break
                    else:
                        raise
                    continue

                elif code == "23505":
                    # Duplicate key — switch to upsert mode and retry
                    upserted = True
                    # Keep only columns that are safe to upsert
                    # (don't reset status/approval fields on re-submission)
                    for protected in ("status", "approved_by", "approved_at", "rejection_reason"):
                        data.pop(protected, None)
                    data["status"] = "pending"   # re-submission always resets to pending
                    continue

                raise   # genuine error — surface it

        raise RuntimeError("Could not insert/upsert exam booking after 25 attempts")

    # Insert exam booking records
    try:
        for ud in units_data:
            uid     = ud["unit"]["id"]
            payload = {
                "student_id":           student_id,
                "unit_id":              uid,
                "exam_date":            str(datetime.now().date()),
                "exam_session":         series,          # raw "1"/"2"/"3" — matches DB constraint
                "purpose":              f"{ud['type']} — {form_data.get('module_level','')}",
                "status":               "pending",
                "serial_number":        serial_number,
                "special_requirements": form_data.get("pwd_status", "N/A"),
                "attempt_type":         ud["attempt"],
            }
            if ud["prev_grade"]: payload["previous_grade"]    = ud["prev_grade"]
            if ud["prev_mid"]:   payload["previous_marks_id"] = ud["prev_mid"]

            _insert_strip_bad(payload)

        write_audit_log("create_exam_booking", target=f"booking:{serial_number}",
                        detail={"units": len(units_data)})
    except Exception as db_err:
        flash(f"Error saving booking: {db_err}", "danger")
        return redirect(url_for("student.exam_booking_form"))
    
    # Generate PDF — Form 1A design matching the physical form
    try:
        pdf_value  = _build_exam_booking_pdf(
            student=student, course_name=course_name, course_code=course_code,
            department_name=department_name, units_data=units_data,
            serial_number=serial_number, year=year, series=series, term=term,
            form_data=form_data,
            documents=documents,
            storage_client=get_service_client().storage,
        )
        safe_serial = serial_number.replace("/", "-")
        flash(f'Exam booking created! Serial Number: {serial_number}', 'success')
        flash('Download, print and hand it to your HOD for departmental clearance.', 'info')
        response = make_response(pdf_value)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=Exam_Booking_{safe_serial}.pdf'
        return response
    except ImportError:
        flash('PDF generation requires reportlab & pillow: pip install reportlab pillow', 'warning')
        flash(f'Exam booking saved. Serial Number: {serial_number}', 'success')
        return redirect(url_for("student.exam_bookings"))
    except Exception as e:
        flash(f'Error generating PDF: {e}', 'danger')
        flash(f'Exam booking created successfully! Serial Number: {serial_number}', 'success')
        return redirect(url_for("student.exam_bookings"))


@student_bp.route("/exam-bookings/<booking_id>/download")
@student_required
def download_exam_booking(booking_id):
    """Regenerate and stream the exam booking PDF — no external bucket required."""
    db         = get_service_client()
    user       = current_user()
    student_id = user["id"]

    # ── 1. Fetch the target booking ──────────────────────────────────────────
    booking_row = (db.table("exam_bookings")
                     .select("id, status, serial_number, student_id")
                     .eq("id", booking_id)
                     .eq("student_id", student_id)
                     .limit(1)
                     .execute().data or [])
    if not booking_row:
        abort(404)
    booking_row = booking_row[0]

    if booking_row.get("status") == "rejected":
        flash("Rejected bookings cannot be downloaded.", "warning")
        return redirect(url_for("student.exam_bookings"))

    serial_number = booking_row.get("serial_number") or ""

    # ── 2. Fetch all units in this submission (same serial or same booking) ──
    if serial_number:
        all_rows = (db.table("exam_bookings")
                      .select("*, units(id, name, code)")
                      .eq("student_id", student_id)
                      .eq("serial_number", serial_number)
                      .execute().data or [])
    else:
        all_rows = [booking_row]   # single row, no serial stored

    if not all_rows:
        all_rows = [booking_row]

    first = all_rows[0]
    series = str(first.get("exam_session", "1"))
    year   = str(first.get("exam_date", str(datetime.now().year)))[:4]

    # ── 3. Student / course / documents ─────────────────────────────────────
    student    = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}
    enrollment = (db.table("enrollments")
                    .select("*, classes(id, name, course_id)")
                    .eq("student_id", student_id)
                    .execute().data or [])
    course_name = department_name = course_code = ""
    if enrollment:
        cls = enrollment[0].get("classes") or {}
        cid = cls.get("course_id")
        if cid:
            crs = (db.table("courses").select("*, departments(name)")
                     .eq("id", cid).single().execute().data or {})
            course_name     = crs.get("name", "")
            course_code     = crs.get("code", "")
            department_name = (crs.get("departments") or {}).get("name", "")

    # Build units_data list from the booking rows
    units_data = []
    for row in all_rows:
        unit = row.get("units") or {}
        if not unit.get("name"):
            continue
        purpose   = row.get("purpose", "")
        unit_type = purpose.split(" — ")[0].strip() if " — " in purpose else "Core"
        units_data.append({
            "unit":    unit,
            "type":    unit_type,
            "attempt": row.get("attempt_type", "first_attempt"),
        })

    # Fetch student's uploaded documents for attachment
    docs_raw  = (db.table("student_personal_documents")
                   .select("*").eq("student_id", student_id).execute().data or [])
    documents = {d["document_type"]: d for d in docs_raw}

    # ── Generate PDF using shared Form 1A builder ────────────────────────────
    try:
        pdf_bytes = _build_exam_booking_pdf(
            student=student, course_name=course_name, course_code=course_code,
            department_name=department_name, units_data=units_data,
            serial_number=serial_number or booking_id[:8].upper(),
            year=year, series=series, term="",
            documents=documents,
            storage_client=db.storage,
        )
        safe = (serial_number or booking_id[:8]).replace("/", "-")
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'inline; filename="ExamBooking_{safe}.pdf"'
        return resp
    except ImportError:
        flash("PDF generation requires reportlab & pillow. Run: pip install reportlab pillow", "warning")
        return redirect(url_for("student.exam_bookings"))
    except Exception as exc:
        flash(f"Could not generate PDF: {exc}", "danger")
        return redirect(url_for("student.exam_bookings"))


# ── Delete Exam Booking ────────────────────────────────────────────────────────

@student_bp.route("/exam-bookings/<booking_id>/delete", methods=["POST"])
@student_required
def delete_exam_booking(booking_id):
    """Delete an exam booking (pending or rejected only). Removes the entire batch."""
    db         = get_service_client()
    user       = current_user()
    student_id = user["id"]

    # Fetch the booking — must belong to this student
    rows = (db.table("exam_bookings")
              .select("id, status, serial_number, student_id")
              .eq("id", booking_id)
              .eq("student_id", student_id)
              .limit(1)
              .execute().data or [])

    if not rows:
        flash("Booking not found.", "warning")
        return redirect(url_for("student.exam_booking_form"))

    booking = rows[0]

    if booking.get("status") == "approved":
        flash("Approved bookings cannot be deleted. Contact your HOD.", "warning")
        return redirect(url_for("student.exam_booking_form"))

    # Delete all rows sharing the same serial_number (entire submission batch)
    serial = booking.get("serial_number")
    try:
        if serial:
            db.table("exam_bookings").delete()\
              .eq("student_id", student_id)\
              .eq("serial_number", serial)\
              .execute()
        else:
            db.table("exam_bookings").delete()\
              .eq("id", booking_id)\
              .eq("student_id", student_id)\
              .execute()
        write_audit_log("delete_exam_booking",
                        target=f"booking:{serial or booking_id}",
                        detail={"status": booking.get("status")})
        flash("Exam booking deleted successfully.", "success")
    except Exception as e:
        flash(f"Could not delete booking: {e}", "danger")

    return redirect(url_for("student.exam_booking_form"))


# ── Marks Viewing ─────────────────────────────────────────────────────────────

@student_bp.route("/marks")
@student_required
def marks():
    """
    Marks & Transcript — reads from formative_assessments + formative_marks
    (the tables the trainer dashboard writes to).
    """
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()

    from collections import OrderedDict

    # ── Student profile ───────────────────────────────────────────────────────
    profile = (db.table("user_profiles")
                 .select("full_name, admission_no, mobile_number")
                 .eq("id", student_id).limit(1).execute().data or [])
    profile = profile[0] if profile else {}

    enrollment = (db.table("enrollments")
                    .select("class_id, classes(name, departments(name))")
                    .eq("student_id", student_id).limit(1).execute().data or [])
    class_name = dept_name = ""
    class_id   = None
    if enrollment:
        class_id = enrollment[0].get("class_id")
        cls  = enrollment[0].get("classes") or {}
        dept = cls.get("departments") or {}
        class_name = cls.get("name", "")
        dept_name  = dept.get("name", "")

    # ── Fetch assessment definitions for the student's class ─────────────────
    assessments = []
    if class_id:
        q = (db.table("formative_assessments")
               .select("id, unit_id, assessment_name, assessment_type, max_marks, year, term, "
                       "units(name, code), "
                       "trainer:user_profiles!formative_assessments_trainer_id_fkey(full_name)")
               .eq("class_id", class_id)
               .eq("year", int(year)))
        if term:
            q = q.eq("term", int(term))
        assessments = (q.order("unit_id")
                        .order("assessment_type")
                        .order("created_at")
                        .execute().data or [])

    # ── Fetch marks for this student ──────────────────────────────────────────
    marks_map = {}   # assessment_id → marks_obtained
    if assessments:
        a_ids = [a["id"] for a in assessments]
        fm = (db.table("formative_marks")
                .select("assessment_id, marks_obtained")
                .eq("student_id", student_id)
                .in_("assessment_id", a_ids)
                .execute().data or [])
        marks_map = {m["assessment_id"]: m["marks_obtained"] for m in fm}

    # ── Group by unit ─────────────────────────────────────────────────────────
    by_unit = OrderedDict()
    for a in assessments:
        uid  = a["unit_id"]
        unit = a.get("units") or {}
        if uid not in by_unit:
            by_unit[uid] = {"unit": unit, "term": a.get("term"), "assessments": []}

        obt = marks_map.get(a["id"])          # None = not yet entered by trainer
        mx  = float(a.get("max_marks") or 100)
        if obt is not None:
            pct   = round(float(obt) / mx * 100, 1) if mx else 0
            grade = ("M" if pct >= 85 else "P" if pct >= 70
                     else "C" if pct >= 50 else "NYC")
        else:
            pct   = None
            grade = None            # None → template renders "Pending"

        by_unit[uid]["assessments"].append({
            "assessment_name": a.get("assessment_name", ""),
            "assessment_type": (a.get("assessment_type") or "OTHER").upper(),
            "term":            a.get("term"),
            "cycle":           None,
            "marks_obtained":  obt,       # None if trainer hasn't entered yet
            "max_marks":       mx,
            "grade":           grade,
            "remarks":         None,
            "trainer":         a.get("trainer"),
        })

    # ── Per-unit totals (only rows with marks entered) ────────────────────────
    units_data = []
    for uid, data in by_unit.items():
        entered = [a for a in data["assessments"] if a["marks_obtained"] is not None]
        total_obt = round(sum(float(a["marks_obtained"]) for a in entered), 1) if entered else 0
        total_max = round(sum(a["max_marks"]              for a in entered), 1) if entered else 0
        pct       = round(total_obt / total_max * 100, 1) if total_max else 0
        final     = ("M" if pct >= 85 else "P" if pct >= 70
                     else "C" if pct >= 50 else "NYC") if entered else "—"
        data.update({"total_obt": total_obt, "total_max": total_max,
                     "pct": pct, "final_grade": final, "has_marks": bool(entered)})
        units_data.append(data)

    # ── Overall stats ─────────────────────────────────────────────────────────
    scored = [u for u in units_data if u["has_marks"]]
    overall = round(sum(u["pct"] for u in scored) / len(scored), 1) if scored else 0
    passed  = sum(1 for u in scored if u["final_grade"] in ("M","P","C"))

    return render_template("student/marks.html",
                           units_data=units_data,
                           profile=profile,
                           class_name=class_name,
                           dept_name=dept_name,
                           year=year,
                           term=term,
                           overall=overall,
                           passed=passed)


# ── Result Slip PDF Download ─────────────────────────────────────────────────────

@student_bp.route("/marks/download-result-slip")
@student_required
def download_result_slip():
    """
    Generate and stream the TTTI Academic Result Slip PDF.
    Layout: centred header → left-aligned course/unit info → assessment table → signatures.
    """
    db         = get_service_client()
    user       = current_user()
    student_id = user["id"]

    year = request.args.get("year", str(datetime.now().year))
    term = request.args.get("term", "").strip()

    # ── Fetch all needed data ─────────────────────────────────────────────────
    from collections import OrderedDict

    student    = db.table("user_profiles").select("*").eq("id", student_id).single().execute().data or {}
    enrollment = (db.table("enrollments")
                    .select("class_id, classes(id, name, course_id, departments(name))")
                    .eq("student_id", student_id).limit(1).execute().data or [])

    class_name = dept_name = course_name = course_code = ""
    class_id   = None
    if enrollment:
        class_id = enrollment[0].get("class_id")
        cls  = enrollment[0].get("classes") or {}
        dept = cls.get("departments") or {}
        class_name = cls.get("name", "")
        dept_name  = dept.get("name", "")
        cid = cls.get("course_id")
        if cid:
            crs = db.table("courses").select("name, code").eq("id", cid).single().execute().data or {}
            course_name = crs.get("name", "")
            course_code = crs.get("code", "")

    # ── Fetch assessment definitions + marks (same tables trainer uses) ───────
    assessments = []
    if class_id:
        q = (db.table("formative_assessments")
               .select("id, unit_id, assessment_name, assessment_type, max_marks, year, term, "
                       "units(name, code), "
                       "trainer:user_profiles!formative_assessments_trainer_id_fkey(full_name)")
               .eq("class_id", class_id)
               .eq("year", int(year)))
        if term:
            q = q.eq("term", int(term))
        assessments = (q.order("unit_id").order("assessment_type")
                        .order("created_at").execute().data or [])

    marks_map = {}
    if assessments:
        a_ids = [a["id"] for a in assessments]
        fm = (db.table("formative_marks")
                .select("assessment_id, marks_obtained")
                .eq("student_id", student_id)
                .in_("assessment_id", a_ids)
                .execute().data or [])
        marks_map = {m["assessment_id"]: m["marks_obtained"] for m in fm}

    # ── Build by_unit (only include entries where marks exist) ────────────────
    by_unit = OrderedDict()
    for a in assessments:
        uid  = a["unit_id"]
        unit = a.get("units") or {}
        if uid not in by_unit:
            by_unit[uid] = {"unit": unit, "rows": []}
        obt = marks_map.get(a["id"])
        mx  = float(a.get("max_marks") or 100)
        if obt is not None:
            pct   = round(float(obt) / mx * 100, 1) if mx else 0
            grade = ("M" if pct >= 85 else "P" if pct >= 70
                     else "C" if pct >= 50 else "NYC")
        else:
            pct = grade = None
        by_unit[uid]["rows"].append({
            "assessment_name": a.get("assessment_name",""),
            "assessment_type": (a.get("assessment_type") or "OTHER").upper(),
            "term":            a.get("term"),
            "cycle":           None,
            "marks_obtained":  obt,
            "max_marks":       mx,
            "grade":           grade,
            "trainer":         a.get("trainer"),
        })

    # ── Build PDF ─────────────────────────────────────────────────────────────
    try:
        import io as _io, os as _os
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                        Table, TableStyle, HRFlowable,
                                        Image as RLImage, KeepTogether)

        buf = _io.BytesIO()
        pdf = SimpleDocTemplate(buf, pagesize=A4,
                                leftMargin=20*mm, rightMargin=20*mm,
                                topMargin=15*mm,  bottomMargin=15*mm)
        W = A4[0] - 40*mm

        base   = getSampleStyleSheet()
        ctr14b = ParagraphStyle('c14b', parent=base['Normal'], fontSize=14,
                                fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=2)
        ctr11b = ParagraphStyle('c11b', parent=base['Normal'], fontSize=11,
                                fontName='Helvetica-Bold', alignment=TA_CENTER, spaceAfter=2)
        ctr9   = ParagraphStyle('c9',  parent=base['Normal'], fontSize=9,
                                fontName='Helvetica', alignment=TA_CENTER, spaceAfter=1)
        lft10b = ParagraphStyle('l10b', parent=base['Normal'], fontSize=10,
                                fontName='Helvetica-Bold', spaceAfter=3)
        lft9   = ParagraphStyle('l9',  parent=base['Normal'], fontSize=9,
                                fontName='Helvetica', spaceAfter=2)
        lft9b  = ParagraphStyle('l9b', parent=base['Normal'], fontSize=9,
                                fontName='Helvetica-Bold', spaceAfter=2)
        tbl_h  = ParagraphStyle('th', parent=base['Normal'], fontSize=8,
                                fontName='Helvetica-Bold', alignment=TA_CENTER)
        tbl_c  = ParagraphStyle('tc', parent=base['Normal'], fontSize=8,
                                fontName='Helvetica', alignment=TA_CENTER)
        tbl_l  = ParagraphStyle('tl', parent=base['Normal'], fontSize=8,
                                fontName='Helvetica', alignment=TA_LEFT)

        DARK_BLUE  = colors.HexColor('#0f2c54')
        MID_BLUE   = colors.HexColor('#1e40af')
        LIGHT_GREY = colors.HexColor('#f8fafc')
        BORDER     = colors.HexColor('#e2e8f0')

        TYPE_BG = {'ORAL': colors.HexColor('#fff7ed'),
                   'PRACTICAL': colors.HexColor('#eff6ff'),
                   'WRITTEN':   colors.HexColor('#f5f3ff'),
                   'CA':        colors.HexColor('#f0fdf4'),
                   'IA':        colors.HexColor('#fef9c3')}
        GRADE_BG = {'M':   colors.HexColor('#dcfce7'),
                    'P':   colors.HexColor('#dbeafe'),
                    'C':   colors.HexColor('#fef3c7'),
                    'NYC': colors.HexColor('#fee2e2')}

        story = []

        # ════════════════════════════════════════════════════════════════════
        # 1.  CENTRED HEADER  ─  Logo · Institute · Examination Department
        # ════════════════════════════════════════════════════════════════════
        logo_path = _os.path.join(_os.path.dirname(__file__),
                                  '..', 'static', 'assets', 'THIKATTILOGO.jpg')
        logo_cell = Paragraph("", lft9)
        if _os.path.exists(logo_path):
            try:
                logo_cell = RLImage(logo_path, width=22*mm, height=22*mm)
            except Exception:
                pass

        header_content = [
            Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", ctr14b),
            Paragraph("EXAMINATION DEPARTMENT", ctr11b),
            Paragraph("ACADEMIC RESULT SLIP", ctr9),
            Paragraph(f"Year: {year}" + (f"  |  Term: {term}" if term else ""), ctr9),
        ]

        hdr_tbl = Table([[logo_cell, header_content, logo_cell]],
                        colWidths=[25*mm, W - 50*mm, 25*mm])
        hdr_tbl.setStyle(TableStyle([
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN',         (1,0), (1,0),   'CENTER'),
            ('TOPPADDING',    (0,0), (-1,-1),  0),
            ('BOTTOMPADDING', (0,0), (-1,-1),  0),
        ]))
        story.append(hdr_tbl)
        story.append(HRFlowable(width="100%", thickness=2,
                                color=DARK_BLUE, spaceAfter=6))

        # ════════════════════════════════════════════════════════════════════
        # 2.  LEFT-ALIGNED STUDENT & COURSE INFO
        # ════════════════════════════════════════════════════════════════════
        info_pairs = [
            ["Student Name:", student.get("full_name", "—"),
             "Admission No:", student.get("admission_no", "—")],
            ["Course Name:",  course_name or "—",
             "Course Code:",  course_code or "—"],
            ["Department:",   dept_name   or "—",
             "Class:",        class_name  or "—"],
        ]
        for pair in info_pairs:
            row_tbl = Table(
                [[Paragraph(pair[0], lft9b), Paragraph(pair[1], lft9),
                  Paragraph(pair[2], lft9b), Paragraph(pair[3], lft9)]],
                colWidths=[28*mm, W/2 - 28*mm, 28*mm, W/2 - 28*mm]
            )
            row_tbl.setStyle(TableStyle([
                ('TOPPADDING',    (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('LINEBELOW',     (1,0), (1,0),   0.5, colors.grey),
                ('LINEBELOW',     (3,0), (3,0),   0.5, colors.grey),
                ('VALIGN',        (0,0), (-1,-1), 'BOTTOM'),
            ]))
            story.append(row_tbl)

        story.append(Spacer(1, 8))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=BORDER, spaceAfter=6))

        # ════════════════════════════════════════════════════════════════════
        # 3.  COMPACT MARKS TABLE  —  ONE UNIT = ONE ROW
        #     Columns: # | Code | Unit Name | Tm | ORAL | PRACTICAL |
        #              WRITTEN | CA | IA | Total | Score% | Grade
        # ════════════════════════════════════════════════════════════════════
        TYPE_ORDER = ['ORAL', 'PRACTICAL', 'WRITTEN', 'CA', 'IA']

        # Determine which types are actually present so we only make those columns
        present_types = []
        for t in TYPE_ORDER:
            for ud in by_unit.values():
                if any((r.get("assessment_type") or "").upper() == t for r in ud["rows"]):
                    present_types.append(t)
                    break

        if not by_unit:
            story.append(Paragraph("No assessment records found for the selected period.", lft9))
        else:
            # ── Build header row ──────────────────────────────────────────────
            TYPE_HDR_COLOR = {
                'ORAL':      colors.HexColor('#c2410c'),
                'PRACTICAL': colors.HexColor('#1d4ed8'),
                'WRITTEN':   colors.HexColor('#6d28d9'),
                'CA':        colors.HexColor('#15803d'),
                'IA':        colors.HexColor('#854d0e'),
            }
            TYPE_BG2 = {
                'ORAL':      colors.HexColor('#fff7ed'),
                'PRACTICAL': colors.HexColor('#eff6ff'),
                'WRITTEN':   colors.HexColor('#f5f3ff'),
                'CA':        colors.HexColor('#f0fdf4'),
                'IA':        colors.HexColor('#fef9c3'),
            }

            hdr = ([Paragraph("#",     tbl_h),
                    Paragraph("Code",  tbl_h),
                    Paragraph("Unit Name", tbl_l)] +
                   [Paragraph("Tm",    tbl_h)] +
                   [Paragraph(t, ParagraphStyle(f'th_{t}', parent=tbl_h,
                                                textColor=TYPE_HDR_COLOR.get(t, colors.white)))
                    for t in present_types] +
                   [Paragraph("Total", tbl_h),
                    Paragraph("Score", tbl_h),
                    Paragraph("Grade", tbl_h)])

            tbl_data  = [hdr]
            tbl_style = [
                ('BACKGROUND',    (0,0), (-1,0),  MID_BLUE),
                ('TEXTCOLOR',     (0,0), (-1,0),  colors.white),
                ('FONTNAME',      (0,0), (-1,-1), 'Helvetica'),
                ('FONTSIZE',      (0,0), (-1,-1), 7.5),
                ('TOPPADDING',    (0,0), (-1,-1), 3),
                ('BOTTOMPADDING', (0,0), (-1,-1), 3),
                ('LEFTPADDING',   (0,0), (-1,-1), 3),
                ('RIGHTPADDING',  (0,0), (-1,-1), 3),
                ('GRID',          (0,0), (-1,-1), 0.4, BORDER),
                ('ALIGN',         (0,0), (-1,-1), 'CENTER'),
                ('ALIGN',         (2,0), (2,-1),  'LEFT'),
                ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0,1),(-1,-1),
                 [colors.white, colors.HexColor('#f8fafc')]),
            ]

            # ── One data row per unit ─────────────────────────────────────────
            for row_i, (uid, ud) in enumerate(by_unit.items(), start=1):
                unit = ud["unit"]
                rows = ud["rows"]

                # Group rows by type
                by_type = {}
                for r in rows:
                    t = (r.get("assessment_type") or "OTHER").upper()
                    by_type.setdefault(t, []).append(r)

                # Per-type cells: list marks as "val(name_abbrev)" strings
                type_cells = []
                for t in present_types:
                    t_rows = by_type.get(t, [])
                    if not t_rows:
                        type_cells.append(Paragraph("—", tbl_c))
                        continue
                    # Build a compact string: "90  70  —" with grade colouring
                    lines = []
                    for r in t_rows:
                        obt_raw = r.get("marks_obtained")
                        if obt_raw is not None:
                            mx    = float(r.get("max_marks") or 100)
                            obt   = float(obt_raw)
                            pct_v = obt / mx * 100 if mx else 0
                            grade = (r.get("grade") or "").upper()
                            # Short abbreviation of name: first word + number if any
                            name = r.get("assessment_name") or ""
                            lines.append(f"{obt}")
                        else:
                            lines.append("—")
                    cell_txt = "  ".join(lines)
                    type_cells.append(Paragraph(cell_txt, tbl_c))

                # Unit total
                entered = [r for r in rows if r.get("marks_obtained") is not None]
                u_obt = round(sum(float(r["marks_obtained"]) for r in entered), 1) if entered else 0
                u_mx  = round(sum(float(r.get("max_marks") or 100) for r in entered), 1) if entered else 0
                u_pct = round(u_obt / u_mx * 100, 1) if u_mx else 0
                final = ("M" if u_pct >= 85 else "P" if u_pct >= 70
                         else "C" if u_pct >= 50 else "NYC") if entered else "—"
                grade_bg = GRADE_BG.get(final, colors.white)

                data_row = (
                    [Paragraph(str(row_i),                      tbl_c),
                     Paragraph(unit.get("code","—"),            tbl_c),
                     Paragraph(unit.get("name","—"),            tbl_l),
                     Paragraph(f"T{rows[0].get('term','') or '—'}" if rows else "—", tbl_c)]
                    + type_cells +
                    [Paragraph(f"<b>{u_obt}/{u_mx}</b>" if entered else "—", tbl_c),
                     Paragraph(f"<b>{u_pct}%</b>"       if entered else "—", tbl_c),
                     Paragraph(f"<b>{final}</b>",                             tbl_c)]
                )
                tbl_data.append(data_row)
                ri = len(tbl_data) - 1
                # Grade cell colour
                grade_col_idx = len(hdr) - 1
                tbl_style.append(('BACKGROUND', (grade_col_idx,ri), (grade_col_idx,ri), grade_bg))

            # ── Column widths ─────────────────────────────────────────────────
            # Fixed: #(7) Code(14) Name(dynamic) Tm(8) ... type cols ... Total(18) Score(16) Grade(13)
            fixed = 7*mm + 14*mm + 8*mm + 18*mm + 16*mm + 13*mm
            type_col_w = 14*mm   # per type column
            name_w = W - fixed - type_col_w * len(present_types)
            name_w = max(name_w, 30*mm)
            col_widths = ([7*mm, 14*mm, name_w, 8*mm] +
                          [type_col_w] * len(present_types) +
                          [18*mm, 16*mm, 13*mm])

            compact_tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
            compact_tbl.setStyle(TableStyle(tbl_style))
            story.append(compact_tbl)
            story.append(Spacer(1, 10))

        # ════════════════════════════════════════════════════════════════════
        # 4.  GRADE SCALE
        # ════════════════════════════════════════════════════════════════════
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
        scale = Table([[
            Paragraph("<b>M — Mastery</b> 85–100%",           lft9),
            Paragraph("<b>P — Proficient</b> 70–84%",         lft9),
            Paragraph("<b>C — Competent</b> 50–69%",          lft9),
            Paragraph("<b>NYC — Not Yet Competent</b> 0–49%", lft9),
        ]], colWidths=[W/4]*4)
        scale.setStyle(TableStyle([
            ('BACKGROUND',    (0,0),(-1,-1), LIGHT_GREY),
            ('BOX',           (0,0),(-1,-1), 0.5, BORDER),
            ('TOPPADDING',    (0,0),(-1,-1), 4),
            ('BOTTOMPADDING', (0,0),(-1,-1), 4),
            ('LEFTPADDING',   (0,0),(-1,-1), 6),
        ]))
        story += [scale, Spacer(1, 16)]

        # ════════════════════════════════════════════════════════════════════
        # 5.  OFFICIAL SIGNATURES  (HOD left · Examinations right)
        # ════════════════════════════════════════════════════════════════════
        story.append(HRFlowable(width="100%", thickness=1.5,
                                color=DARK_BLUE, spaceAfter=10))
        story.append(Paragraph("OFFICIAL VERIFICATION", lft10b))
        story.append(Spacer(1, 8))

        # Use a simple 2-column layout; each column is self-contained.
        half = W / 2 - 4*mm
        line = "_" * 38        # underline length

        def _sig_block(title):
            """Return a Table cell containing one signature block."""
            rows = [
                [Paragraph(f"<b>{title}</b>",
                           ParagraphStyle('sh', parent=lft9b, fontSize=9,
                                          textColor=DARK_BLUE))],
                [Spacer(1, 6)],
                [Paragraph(f"Name:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
                [Spacer(1, 4)],
                [Paragraph(f"Signature:&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
                [Spacer(1, 4)],
                [Paragraph(f"Stamp/Date: {line}", lft9)],
            ]
            t = Table(rows, colWidths=[half])
            t.setStyle(TableStyle([
                ('TOPPADDING',    (0,0),(-1,-1), 2),
                ('BOTTOMPADDING', (0,0),(-1,-1), 2),
                ('LEFTPADDING',   (0,0),(-1,-1), 0),
                ('RIGHTPADDING',  (0,0),(-1,-1), 0),
            ]))
            return t

        sig_outer = Table(
            [[_sig_block("HEAD OF DEPARTMENT"),
              Spacer(8*mm, 1),
              _sig_block("EXAMINATIONS OFFICER")]],
            colWidths=[half, 8*mm, half]
        )
        sig_outer.setStyle(TableStyle([
            ('VALIGN', (0,0),(-1,-1), 'TOP'),
            ('TOPPADDING',    (0,0),(-1,-1), 0),
            ('BOTTOMPADDING', (0,0),(-1,-1), 0),
        ]))
        story.append(sig_outer)

        # Footer timestamp
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=3))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%d %B %Y  %H:%M')}  ·  "
            f"{student.get('full_name','—')}  ·  Adm: {student.get('admission_no','—')}",
            ctr9))

        # ════════════════════════════════════════════════════════════════════
        # 6.  WATERMARK  (drawn on every page via onPage callback)
        # ════════════════════════════════════════════════════════════════════
        import math as _math
        _wm_text = "TTTI OFFICIAL DOCUMENT"
        _adm_no  = student.get("admission_no","") or ""

        def _draw_watermark(canvas_obj, doc_obj):
            canvas_obj.saveState()
            canvas_obj.setFont("Helvetica-Bold", 42)
            canvas_obj.setFillColorRGB(0.75, 0.75, 0.75, alpha=0.18)
            # Centre of A4
            cx = A4[0] / 2
            cy = A4[1] / 2
            canvas_obj.translate(cx, cy)
            canvas_obj.rotate(45)
            canvas_obj.drawCentredString(0, 20,  _wm_text)
            canvas_obj.drawCentredString(0, -30, _adm_no)
            canvas_obj.restoreState()

        # Build with watermark callback
        pdf.build(story,
                  onFirstPage=_draw_watermark,
                  onLaterPages=_draw_watermark)
        pdf_bytes = buf.getvalue()

        fname = f"ResultSlip_{student.get('admission_no','student')}_{year}"
        if term:
            fname += f"_T{term}"
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        resp.headers["Content-Disposition"] = f'attachment; filename="{fname}.pdf"'
        return resp

    except ImportError:
        flash("PDF generation requires reportlab. Run: pip install reportlab pillow", "warning")
        return redirect(url_for("student.marks"))
    except Exception as exc:
        flash(f"Could not generate PDF: {exc}", "danger")
        return redirect(url_for("student.marks"))


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
        svc.storage.from_("assessment-scripts").upload(
            path=storage_path,
            file=file_data,
            file_options={"content-type": file.content_type, "content-disposition": "inline"}
        )

        # Get public URL
        import os
        file_url = f"{os.environ.get('SUPABASE_URL','').strip()}/storage/v1/object/public/assessment-scripts/{storage_path}"

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
        _furl = document.get("file_url", "")
        storage_path = _furl.split("/assessment-scripts/")[-1] if "/assessment-scripts/" in _furl else _furl.split("documents/")[-1]
        svc = get_service_client()
        svc.storage.from_("assessment-scripts").remove([storage_path])
        
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
    
    # Get student's class + department (course) via enrollments
    enrollment = (db.table("enrollments")
                  .select("class_id, classes(id, name, departments(name))")
                  .eq("student_id", student_id)
                  .limit(1)
                  .execute().data or [])

    course_name = ""
    if enrollment:
        cls  = enrollment[0].get("classes") or {}
        dept = cls.get("departments") or {}
        class_label = cls.get("name", "")
        dept_label  = dept.get("name", "")
        if dept_label and class_label:
            course_name = f"{dept_label} — {class_label}"
        else:
            course_name = dept_label or class_label

    # Get student profile for form pre-fill
    profile_rows = (db.table("user_profiles")
                      .select("full_name, admission_no, mobile_number")
                      .eq("id", student_id)
                      .limit(1)
                      .execute().data or [])
    profile = profile_rows[0] if profile_rows else {}

    enrolled_units = []  # kept for backward-compat

    # Get ALL student attachments (for history table)
    all_attachments = (db.table("industrial_attachments")
                       .select("*, companies(name, address, latitude, longitude, contact_person, contact_phone), units(name, code)")
                       .eq("student_id", student_id)
                       .order("created_at", desc=True)
                       .execute().data or [])

    # Current attachment = most recent attachment still in the approval / activity lifecycle
    current_attachment = None
    for att in all_attachments:
        if att.get("status") in ("active", "pending", "approved", "rejected"):
            current_attachment = att
            break
    # Fall back to most recent of any status
    if not current_attachment and all_attachments:
        current_attachment = all_attachments[0]

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

    open_period = get_open_period(db)
    can_submit = True
    submit_block_msg = ""
    if open_period:
        eligible = student_can_submit_placement(
            db, student_id,
            open_period.get("term", ""),
            open_period.get("year", datetime.now().year),
        )
        can_submit, submit_block_msg, _ = eligible
    elif attachment_periods_exist(db):
        can_submit = False
        submit_block_msg = (
            "No attachment application window is currently open. "
            "The liaison officer will open the period and issue introduction letters when ready."
        )

    return render_template("student/industrial_attachment.html",
                          current_attachment=current_attachment,
                          all_attachments=all_attachments,
                          enrolled_units=enrolled_units,
                          course_name=course_name,
                          companies=[],
                          today_logs=today_logs,
                          profile=profile,
                          open_period=open_period,
                          can_submit_placement=can_submit,
                          submit_block_msg=submit_block_msg,
                          placement_status_label=placement_status_label)


@student_bp.route("/industrial-attachment/request", methods=["POST"])
@student_required
def request_attachment():
    """Submit placement details after securing a company externally."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    company_name = (request.form.get("company_name") or "").strip()
    industry = (request.form.get("industry") or "Other").strip()
    company_department = (request.form.get("company_department") or "").strip()
    company_address = (request.form.get("company_address") or "").strip()
    county = (request.form.get("county") or "").strip()
    town = (request.form.get("town") or "").strip()
    company_email = (request.form.get("company_email") or "").strip()
    company_phone = (request.form.get("company_phone") or "").strip()
    website = (request.form.get("website") or "").strip()

    supervisor_name = (request.form.get("supervisor_name") or "").strip()
    supervisor_position = (request.form.get("supervisor_position") or "").strip()
    supervisor_contact = (request.form.get("supervisor_contact") or "").strip()
    supervisor_email = (request.form.get("supervisor_email") or "").strip()

    attachment_term = (request.form.get("attachment_term") or "").strip()
    attachment_year_raw = (request.form.get("attachment_year") or "").strip()
    start_date = (request.form.get("start_date") or "").strip()
    end_date = (request.form.get("end_date") or "").strip()
    expected_hours = (request.form.get("expected_working_hours") or "").strip()
    mobile_number = (request.form.get("mobile_number") or "").strip()

    acceptance_letter = request.files.get("acceptance_letter")
    offer_letter = request.files.get("offer_letter")
    intro_letter = request.files.get("introduction_letter")
    company_stamp = request.files.get("company_stamp")
    signed_form = request.files.get("signed_acceptance_form")

    lat_raw = request.form.get("latitude", "").strip()
    lng_raw = request.form.get("longitude", "").strip()
    try:
        latitude = float(lat_raw) if lat_raw else None
        longitude = float(lng_raw) if lng_raw else None
    except ValueError:
        latitude = longitude = None

    if not all([company_name, company_address, county, town, supervisor_name,
                supervisor_position, supervisor_contact, attachment_term, start_date, end_date]):
        flash("Please complete all required placement fields.", "error")
        return redirect(url_for("student.industrial_attachment"))

    if not acceptance_letter or not acceptance_letter.filename:
        flash("Upload the company acceptance letter before submitting.", "error")
        return redirect(url_for("student.industrial_attachment"))

    try:
        year_int = int(attachment_year_raw) if attachment_year_raw else datetime.now().year
    except ValueError:
        year_int = datetime.now().year

    allowed, block_msg, ctx = student_can_submit_placement(db, student_id, attachment_term, year_int)
    if not allowed:
        flash(block_msg, "error")
        return redirect(url_for("student.industrial_attachment"))

    period = ctx.get("period")
    period_id = period.get("id") if period else None

    try:
        letter_url, letter_path = upload_placement_document(
            acceptance_letter, student_id, company_name
        )

        doc_urls = {}
        for label, fobj in [
            ("offer_letter", offer_letter),
            ("introduction_letter", intro_letter),
            ("company_stamp", company_stamp),
            ("signed_acceptance_form", signed_form),
        ]:
            if fobj and fobj.filename:
                url, _path = upload_placement_document(fobj, student_id, label)
                doc_urls[label + "_url"] = url

        company_payload = {
            "name": company_name,
            "industry_classification": industry if industry in (
                "Electrical Engineering", "Mechanical Engineering", "Information Technology",
                "Civil Engineering", "Automotive Engineering", "Hospitality",
                "Business Management", "Health Sciences", "Agriculture",
                "Construction", "Manufacturing", "Other"
            ) else "Other",
            "address": company_address,
            "city": town,
            "county": county,
            "email": company_email or None,
            "phone_number": company_phone or None,
            "website": website or None,
            "company_department": company_department or None,
            "contact_person": supervisor_name,
            "contact_phone": supervisor_contact,
            "contact_email": supervisor_email or None,
            "is_active": True,
            "available_slots": 1,
            "created_by": student_id,
        }
        if latitude is not None:
            company_payload["latitude"] = latitude
        if longitude is not None:
            company_payload["longitude"] = longitude

        def _insert_company(payload):
            try:
                return db.table("companies").insert(payload).execute()
            except Exception:
                fallback = dict(payload)
                for k in ("county", "company_department"):
                    fallback.pop(k, None)
                return db.table("companies").insert(fallback).execute()

        company_res = _insert_company(company_payload)
        company_id = company_res.data[0]["id"]

        if mobile_number:
            try:
                db.table("user_profiles").update({"mobile_number": mobile_number}).eq("id", student_id).execute()
            except Exception:
                pass

        placement_details = {
            "county": county,
            "town": town,
            "company_department": company_department,
            "expected_working_hours": expected_hours,
            "workflow": "placement_first_v1",
        }

        att_payload = {
            "student_id": student_id,
            "company_id": company_id,
            "start_date": start_date,
            "end_date": end_date,
            "status": "pending",
            "placement_status": "pending_verification",
            "created_by": student_id,
            "acceptance_letter_url": letter_url,
            "acceptance_letter_name": acceptance_letter.filename,
            "acceptance_letter_path": letter_path,
            "acceptance_letter_status": "pending",
            "supervisor_email": supervisor_email or None,
            "supervisor_position": supervisor_position,
            "expected_working_hours": expected_hours or None,
            "placement_details": placement_details,
            "attachment_term": attachment_term,
            "attachment_year": year_int,
        }
        if period_id:
            att_payload["period_id"] = period_id
        att_payload.update(doc_urls)

        def _insert_attachment(payload):
            try:
                return db.table("industrial_attachments").insert(payload).execute()
            except Exception:
                fallback = dict(payload)
                for k in (
                    "placement_status", "placement_details", "period_id",
                    "expected_working_hours", "supervisor_position",
                    "offer_letter_url", "introduction_letter_url",
                    "company_stamp_url", "signed_acceptance_form_url",
                ):
                    fallback.pop(k, None)
                return db.table("industrial_attachments").insert(fallback).execute()

        _insert_attachment(att_payload)

        notify_liaison_officers(
            db,
            title="New Placement Submission",
            message=f"{user.get('full_name', 'A trainee')} submitted placement details for {company_name}.",
            action_url="/liaison-officer/attachments?status=pending",
        )

        write_audit_log("submit_placement", target=f"company:{company_id}",
                        detail={"company": company_name, "supervisor": supervisor_name, "term": attachment_term})
        flash(
            "Placement submitted successfully. The liaison officer will verify your company details and documents.",
            "success",
        )
    except Exception as e:
        flash(f"Error submitting placement: {e}", "error")

    return redirect(url_for("student.industrial_attachment"))


# ── Delete Pending Attachment ─────────────────────────────────────────────────

@student_bp.route("/industrial-attachment/<att_id>/delete", methods=["POST"])
@student_required
def delete_attachment(att_id):
    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    row = (db.table("industrial_attachments")
             .select("id, status, company_id, created_by, acceptance_letter_path")
             .eq("id", att_id)
             .eq("student_id", student_id)
             .limit(1)
             .execute().data or [])

    if not row:
        flash("Attachment not found.", "error")
        return redirect(url_for("student.industrial_attachment"))

    att = row[0]
    if att.get("status") != "pending":
        flash("Only submitted (pending) attachments can be deleted.", "error")
        return redirect(url_for("student.industrial_attachment"))

    try:
        company_id = att.get("company_id")
        letter_path = att.get("acceptance_letter_path")
        db.table("industrial_attachments").delete().eq("id", att_id).execute()
        if letter_path:
            try:
                db.storage.from_("assessment-scripts").remove([letter_path])
            except Exception:
                pass
        # Clean up the company record if it was created by this student
        if company_id:
            try:
                db.table("companies").delete().eq("id", company_id).eq("created_by", student_id).execute()
            except Exception:
                pass
        write_audit_log("delete_attachment", target=f"attachment:{att_id}")
        flash("Attachment registration deleted.", "success")
    except Exception as e:
        flash(f"Could not delete attachment: {e}", "error")

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
        lat1_deg, lon1_deg = float(latitude), float(longitude)
        lat2, lon2 = float(company_lat), float(company_lon)

        # Convert to radians for distance calculation only
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1_deg, lon1_deg, lat2, lon2])
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
            "latitude": lat1_deg,
            "longitude": lon1_deg,
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
    
    # Get student's active attachment (use list query to avoid PGRST116 on 0 rows)
    attachment_rows = (db.table("industrial_attachments")
                       .select("*, companies(name)")
                       .eq("student_id", student_id)
                       .eq("status", "active")
                       .limit(1)
                       .execute().data or [])

    active_attachment = attachment_rows[0] if attachment_rows else None

    # If no active attachment, also check for any attachment (pending/approved)
    if not active_attachment:
        any_rows = (db.table("industrial_attachments")
                    .select("*, companies(name)")
                    .eq("student_id", student_id)
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute().data or [])
        active_attachment = any_rows[0] if any_rows else None

    # Get logbook entries — grouped by ISO week for weekly approval display
    from collections import defaultdict
    from datetime import timedelta

    logbooks = []
    weeks_grouped = {}  # week_start_str → { label, entries, week_status }

    if active_attachment:
        import os as _os
        _supabase_url = _os.environ.get("SUPABASE_URL", "").strip()

        logbooks = (db.table("digital_logbook")
                   .select("*")
                   .eq("student_id", student_id)
                   .eq("attachment_id", active_attachment["id"])
                   .order("log_date", desc=True)
                   .order("entry_time", desc=False)
                   .execute().data or [])

        for entry in logbooks:
            ev_paths = entry.get("evidence_urls") or []
            entry["_evidence"] = [
                {
                    "url":  f"{_supabase_url}/storage/v1/object/public/assessment-evidence/{p}",
                    "ext":  p.rsplit(".", 1)[-1].lower() if "." in p else "bin",
                    "name": p.rsplit("/", 1)[-1],
                }
                for p in ev_paths if p
            ]

        # Group by week (Monday–Sunday)
        week_buckets = defaultdict(list)
        for entry in logbooks:
            try:
                d = datetime.strptime(entry["log_date"], "%Y-%m-%d")
            except Exception:
                d = datetime.now()
            monday = d - timedelta(days=d.weekday())
            week_buckets[monday.strftime("%Y-%m-%d")].append(entry)

        for week_start, entries in sorted(week_buckets.items(), reverse=True):
            ws = datetime.strptime(week_start, "%Y-%m-%d")
            we = ws + timedelta(days=6)
            label = f"{ws.strftime('%d %b')} – {we.strftime('%d %b %Y')}"
            weeks_grouped[week_start] = {
                "label":   label,
                "entries": entries,
            }

    today_str = datetime.now().strftime("%Y-%m-%d")

    # Fetch personal documents uploaded via My Documents
    personal_docs_raw = (db.table("student_personal_documents")
                          .select("document_type, document_name, file_url, file_name, status, updated_at")
                          .eq("student_id", student_id)
                          .execute().data or [])

    return render_template("student/logbook.html",
                          attachment=active_attachment,
                          logbooks=logbooks,
                          weeks_grouped=weeks_grouped,
                          today_str=today_str,
                          personal_docs=personal_docs_raw)


@student_bp.route("/logbook/add", methods=["POST"])
@student_required
def add_logbook():
    """Add a new logbook entry."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    attachment_id         = request.form.get("attachment_id", "").strip()
    log_date              = request.form.get("log_date", "").strip()
    entry_time            = request.form.get("entry_time", "").strip()  # e.g. "08:00-11:00"
    tasks_performed       = request.form.get("tasks_performed", "").strip()
    skills_applied        = request.form.get("skills_applied", "").strip()
    challenges_encountered= request.form.get("challenges_encountered", "").strip()
    achievements          = request.form.get("achievements", "").strip()

    # Map time slot to hours_worked (start hour of 3-hr block)
    slot_hours = {"08:00-11:00": 8, "11:00-14:00": 11, "14:00-17:00": 14, "17:00-20:00": 17}
    hours_worked = slot_hours.get(entry_time)

    if not all([attachment_id, log_date, entry_time, tasks_performed]):
        flash("Date, time slot, and activity description are required.", "error")
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
            "student_id":           student_id,
            "attachment_id":        attachment_id,
            "log_date":             log_date,
            "entry_time":           entry_time,
            "tasks_performed":      tasks_performed,
            "skills_applied":       skills_applied,
            "hours_worked":         hours_worked,
            "challenges_encountered": challenges_encountered,
            "achievements":         achievements,
            "evidence_urls":        evidence_paths if evidence_paths else None,
        }).execute()

        write_audit_log("add_logbook", target=f"attachment:{attachment_id}")
        flash("Logbook entry added successfully.", "success")
    except Exception as e:
        flash(f"Error adding logbook entry: {e}", "error")

    return redirect(url_for("student.logbook"))


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
            # Check if employment record exists (table may not exist yet — run supabase_schema.sql)
            existing = (db.table("employment_tracking")
                       .select("id")
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

    # Get current employment status (graceful if tables not yet created in DB)
    current_status = None
    projects = []
    try:
        employment_record = (db.table("employment_tracking")
                            .select("*")
                            .eq("student_id", student_id)
                            .execute().data or [])
        current_status = employment_record[0] if employment_record else None
    except Exception:
        pass

    try:
        projects = (db.table("employment_projects")
                   .select("*")
                   .eq("student_id", student_id)
                   .order("created_at", desc=True)
                   .execute().data or [])
    except Exception:
        pass

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


# ── TTTI Guardian AI Ask ───────────────────────────────────────────────────────

@student_bp.route("/ai-ask", methods=["POST"])
@student_required
def ai_ask():
    """Return a data-driven answer for the TTTI Guardian AI Assistant."""
    data = request.get_json(silent=True) or {}
    question = (data.get("q") or "").strip().lower()
    if not question:
        return jsonify({"reply": "Please type a question so I can help you."})

    db = get_service_client()
    user = current_user()
    student_id = user["id"]

    # ── helpers ──────────────────────────────────────────────────────────────
    def _att():
        rows = db.table("attendance").select("status").eq("student_id", student_id).execute().data or []
        total = len(rows)
        present = sum(1 for r in rows if r.get("status") == "present")
        pct = round(present / total * 100, 1) if total else 0
        return total, present, pct

    def _docs():
        rows = db.table("student_personal_documents").select("document_type, status").eq("student_id", student_id).execute().data or []
        return {r["document_type"]: r.get("status", "uploaded") for r in rows}

    def _clearance():
        rows = db.table("clearance_requests").select("status, stage").eq("student_id", student_id).order("created_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None

    def _exam_bookings():
        rows = db.table("exam_bookings").select("status, units(name, code)").eq("student_id", student_id).order("created_at", desc=True).limit(5).execute().data or []
        return rows

    def _poe():
        rows = db.table("assessments").select("status").eq("student_id", student_id).execute().data or []
        total = len(rows)
        approved = sum(1 for r in rows if r.get("status") == "approved")
        pending  = sum(1 for r in rows if r.get("status") == "pending")
        rejected = sum(1 for r in rows if r.get("status") == "rejected")
        return total, approved, pending, rejected

    def _attachment():
        rows = db.table("industrial_attachments").select("status, companies(name)").eq("student_id", student_id).order("created_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None

    def _logbook():
        rows = db.table("digital_logbook").select("id").eq("student_id", student_id).execute().data or []
        return len(rows)

    def _marks():
        rows = db.table("marks").select("unit_id, marks_obtained, grade, units(name, code)").eq("student_id", student_id).order("created_at", desc=True).execute().data or []
        return rows

    # ── intent detection ─────────────────────────────────────────────────────
    kw = question

    # Attendance
    if any(x in kw for x in ("attend", "present", "absent", "lesson", "75")):
        total, present, pct = _att()
        if total == 0:
            return jsonify({"reply": "You have no attendance records yet. Your trainer marks attendance each lesson — come back after your first class."})
        status = "Good standing" if pct >= 75 else "Below threshold"
        tip = "" if pct >= 75 else " You must reach 75% to be eligible for exam booking. Speak to your trainer immediately."
        return jsonify({"reply": f"Your attendance: {present}/{total} lessons = {pct}% ({status}).{tip}"})

    # POE / Assessment uploads
    if any(x in kw for x in ("poe", "portfolio", "assessment", "upload", "evidence", "submit")):
        total, approved, pending, rejected = _poe()
        if total == 0:
            return jsonify({"reply": "You haven't uploaded any POE yet. Go to Upload POE in the sidebar, select your unit, fill in the task details, and attach your evidence files."})
        parts = [f"Total: {total}"]
        if approved: parts.append(f"{approved} approved")
        if pending:  parts.append(f"{pending} pending review")
        if rejected: parts.append(f"{rejected} need resubmission")
        hint = " Check the rejected ones and resubmit with corrections." if rejected else ""
        return jsonify({"reply": "Your POE status — " + ", ".join(parts) + "." + hint})

    # Exam booking
    if any(x in kw for x in ("exam", "book", "booking", "examination")):
        bookings = _exam_bookings()
        total, present, pct = _att()
        docs = _docs()
        required = ['national_id', 'birth_certificate', 'kcse_certificate', 'passport_photo']
        missing = [d.replace("_", " ").title() for d in required if d not in docs]
        issues = []
        if pct < 75 and total > 0: issues.append(f"attendance is {pct}% (need at least 75%)")
        if total == 0: issues.append("no attendance records found")
        if missing: issues.append("missing documents: " + ", ".join(missing))
        if issues:
            return jsonify({"reply": "You cannot book exams yet — " + "; ".join(issues) + ". Fix these first, then use Exam Booking Form in the sidebar."})
        if not bookings:
            return jsonify({"reply": "You are eligible to book an exam. Go to Exam Booking Form in the sidebar. Your HOD approves first, then the Exam Officer confirms."})
        lines = []
        for b in bookings:
            unit = b.get("units") or {}
            uname = unit.get("name") or unit.get("code") or "Unit"
            lines.append(f"{uname}: {b.get('status', 'pending')}")
        return jsonify({"reply": "Your exam bookings:\n" + "\n".join("• " + l for l in lines)})

    # Clearance
    if any(x in kw for x in ("clear", "clearance", "library", "finance", "games", "store")):
        cl = _clearance()
        if not cl:
            return jsonify({"reply": "You haven't applied for clearance yet. Go to Course Clearance in the sidebar. The 7-stage process: Trainer → HOD → Library → Store → Games → Finance → Deputy Principal. All fees must be cleared first."})
        st = cl.get("status", "")
        sg = cl.get("stage", "")
        return jsonify({"reply": f"Your clearance is currently at stage: {sg}, status: {st}. Check the Clearance page for updates from each approver."})

    # Documents / admission
    if any(x in kw for x in ("document", "admit", "national id", "birth", "kcse", "passport", "certif")):
        docs = _docs()
        required = ['national_id', 'birth_certificate', 'kcse_certificate', 'passport_photo']
        uploaded = [d.replace("_", " ").title() for d in required if d in docs]
        missing  = [d.replace("_", " ").title() for d in required if d not in docs]
        if missing:
            return jsonify({"reply": f"Documents uploaded: {', '.join(uploaded) or 'none'}.\nStill missing: {', '.join(missing)}.\nUpload them via Admission Documents in the sidebar."})
        statuses = [f"{d.replace('_', ' ').title()}: {docs[d]}" for d in required]
        return jsonify({"reply": "All 4 required documents uploaded.\n" + "\n".join("• " + s for s in statuses)})

    # Industrial attachment
    if any(x in kw for x in ("attach", "industry", "company", "placement", "industrial", "intern")):
        att = _attachment()
        if not att:
            return jsonify({"reply": "You don't have an industrial attachment record yet. Go to Industrial Attachment in the sidebar and submit a request with your company details."})
        co = (att.get("companies") or {}).get("name") or "your company"
        st = att.get("status", "pending")
        label = {"pending": "Submitted (awaiting dept admin review)", "active": "Active", "completed": "Completed", "rejected": "Rejected"}.get(st, st)
        return jsonify({"reply": f"Industrial Attachment at {co} — Status: {label}."})

    # Logbook
    if any(x in kw for x in ("logbook", "log book", "log entry", "diary", "daily log")):
        count = _logbook()
        att = _attachment()
        if not att:
            return jsonify({"reply": "The logbook is for students on active industrial attachment. Submit an attachment request first."})
        st = att.get("status", "pending")
        if st != "active":
            return jsonify({"reply": f"Your attachment is currently '{st}'. The logbook is available once your attachment becomes active."})
        return jsonify({"reply": f"You have {count} logbook {'entry' if count == 1 else 'entries'} recorded. Add new ones via Digital Logbook in the sidebar. Entries are reviewed by your department admin."})

    # Marks / grades
    if any(x in kw for x in ("mark", "grade", "score", "result", "pass", "fail")):
        marks = _marks()
        if not marks:
            return jsonify({"reply": "No marks have been recorded for you yet. Marks are entered by your trainer after assessments."})
        lines = []
        for m in marks[:8]:
            u = m.get("units") or {}
            name = u.get("name") or u.get("code") or "Unit"
            score = m.get("marks_obtained", "—")
            grade = m.get("grade") or ""
            lines.append(f"{name}: {score}" + (f" ({grade})" if grade else ""))
        return jsonify({"reply": "Your recent marks:\n" + "\n".join("• " + l for l in lines)})

    # Profile / password
    if any(x in kw for x in ("password", "profile", "change password", "phone", "email")):
        return jsonify({"reply": "To update your profile or change your password, click your name or avatar in the top bar and select Profile. You can update your phone number, email, and password there."})

    # Fees / finance
    if any(x in kw for x in ("fee", "fees", "finance", "payment", "pay", "balance", "tuition")):
        return jsonify({"reply": "For fee balance and payment details, contact the Finance office. Fees must be fully cleared before your Course Clearance can reach the Finance approval stage."})

    # Default — return a personalised snapshot
    try:
        _, _, pct = _att()
        total_p, approved_p, pending_p, _ = _poe()
        att_info = f"Attendance: {pct}%" if pct > 0 else "No attendance recorded"
        poe_info  = f"POE: {total_p} uploads ({approved_p} approved)" if total_p > 0 else "No POE uploaded yet"
    except Exception:
        att_info = poe_info = ""
    summary = f" Your quick summary — {att_info} | {poe_info}." if att_info else ""
    return jsonify({"reply": f"I can help with: attendance, POE uploads, exam booking, clearance, admission documents, industrial attachment, logbook, and marks.{summary}\n\nWhat would you like to know?"})
