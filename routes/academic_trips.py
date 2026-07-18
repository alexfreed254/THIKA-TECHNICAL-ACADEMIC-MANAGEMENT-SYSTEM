"""
Academic Trips Module
Handles trip reports upload, viewing, and management
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from functools import wraps
from datetime import datetime
from db import get_service_client
from auth_utils import current_user, login_required
import os
import uuid
import re

academic_trips_bp = Blueprint("academic_trips", __name__, url_prefix="/academic-trips")

TRIP_MEDIA_BUCKET = "trip-media"
MAX_MEDIA_BYTES = 50 * 1024 * 1024

TRIP_PORTAL_BASE = {
    "trainer":     "trainer/base.html",
    "dept_admin":  "dept_admin/base.html",
    "super_admin": "super_admin/base.html",
}


def _portal_base(role: str) -> str:
    return TRIP_PORTAL_BASE.get(role, "trainer/base.html")


def _supabase_public_url(path: str) -> str:
    base = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    if not base or not path:
        return path or ""
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base}/storage/v1/object/public/{TRIP_MEDIA_BUCKET}/{path.lstrip('/')}"


def _annotate_media(media_rows):
    for m in media_rows or []:
        m["public_url"] = _supabase_public_url(m.get("file_path") or "")
    return media_rows


def _safe_filename(name: str) -> str:
    name = (name or "file").strip()
    name = re.sub(r"[^\w.\-]+", "_", name)
    return name[:120] or "file"


# ============================================================================
# ACCESS CONTROL DECORATORS
# ============================================================================

def trainer_or_coordinator_required(f):
    """Decorator to ensure user is trainer or trip coordinator"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user = current_user()
        if not user:
            abort(401)
        role = user.get("role")
        if role not in ["trainer", "trip_coordinator", "super_admin"]:
            flash("Access denied. Only trainers and trip coordinators can upload trips.", "error")
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def dept_admin_or_super_required(f):
    """Decorator for department admin or super admin"""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        user = current_user()
        if not user:
            abort(401)
        role = user.get("role")
        if role not in ["dept_admin", "super_admin"]:
            flash("Access denied. Only department admins can view trips.", "error")
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_user_department(db, user_id):
    """Get user's department ID"""
    try:
        result = db.table("user_profiles").select("department_id").eq("id", user_id).single().execute()
        return result.data.get("department_id") if result.data else None
    except:
        return None


def filter_trips_by_role(db, user):
    """Filter trips based on user role"""
    role = user.get("role")
    query = db.table("academic_trips").select(
        "*, "
        "classes(id, name, department_id), "
        "departments(id, name), "
        "uploader:user_profiles!academic_trips_uploaded_by_fkey(full_name, role), "
        "reviewer:user_profiles!academic_trips_reviewed_by_fkey(full_name)"
    )
    
    # Super admin sees everything
    if role == "super_admin":
        return query.order("trip_date", desc=True)
    
    # Department admin sees only their department
    elif role == "dept_admin":
        dept_id = get_user_department(db, user["id"])
        if dept_id:
            return query.eq("department_id", dept_id).order("trip_date", desc=True)
        else:
            return query.eq("department_id", "00000000-0000-0000-0000-000000000000")  # No results
    
    # Trainers/coordinators see trips they uploaded or from their department
    else:
        dept_id = get_user_department(db, user["id"])
        if dept_id:
            return query.or_(f"uploaded_by.eq.{user['id']},department_id.eq.{dept_id}").order("trip_date", desc=True)
        else:
            return query.eq("uploaded_by", user["id"]).order("trip_date", desc=True)


# ============================================================================
# ROUTES - VIEWING
# ============================================================================

@academic_trips_bp.route("/")
@login_required
def index():
    """Main trips listing page with filters"""
    db = get_service_client()
    user = current_user()
    
    # Get filter parameters
    filter_day = request.args.get("day")
    filter_term = request.args.get("term")
    filter_year = request.args.get("year")
    filter_class = request.args.get("class_id")
    filter_dept = request.args.get("department_id")
    
    # Base query with role-based filtering
    query = filter_trips_by_role(db, user)
    
    # Apply filters
    if filter_day:
        query = query.eq("trip_date", filter_day)
    if filter_term:
        query = query.eq("term", int(filter_term))
    if filter_year:
        query = query.eq("year", int(filter_year))
    if filter_class:
        query = query.eq("class_id", filter_class)
    if filter_dept and user.get("role") == "super_admin":
        query = query.eq("department_id", filter_dept)
    
    trips = query.execute().data or []
    
    # Get filter options
    departments = []
    classes = []
    
    if user.get("role") == "super_admin":
        departments = db.table("departments").select("id, name").order("name").execute().data or []
        classes = db.table("classes").select("id, name, department_id").order("name").execute().data or []
    elif user.get("role") == "dept_admin":
        dept_id = get_user_department(db, user["id"])
        if dept_id:
            departments = db.table("departments").select("id, name").eq("id", dept_id).execute().data or []
            classes = db.table("classes").select("id, name, department_id").eq("department_id", dept_id).order("name").execute().data or []
    else:
        dept_id = get_user_department(db, user["id"])
        if dept_id:
            classes = db.table("classes").select("id, name, department_id").eq("department_id", dept_id).order("name").execute().data or []
    
    # Get unique years from trips
    years = sorted(set(t["year"] for t in trips if t.get("year")), reverse=True)
    
    return render_template(
        "academic_trips/index.html",
        portal_base=_portal_base(user.get("role")),
        trips=trips,
        departments=departments,
        classes=classes,
        years=years,
        filters={
            "day": filter_day,
            "term": filter_term,
            "year": filter_year,
            "class_id": filter_class,
            "department_id": filter_dept
        }
    )


@academic_trips_bp.route("/<trip_id>")
@login_required
def view_trip(trip_id):
    """View individual trip details"""
    db = get_service_client()
    user = current_user()
    
    # Get trip details
    trip = (db.table("academic_trips")
           .select(
               "*, "
               "classes(id, name, department_id), "
               "departments(id, name), "
               "uploader:user_profiles!academic_trips_uploaded_by_fkey(full_name, role, mobile_number), "
               "reviewer:user_profiles!academic_trips_reviewed_by_fkey(full_name)"
           )
           .eq("id", trip_id)
           .limit(1)
           .execute().data or [None])[0]
    
    if not trip:
        abort(404)
    
    # Check access permission
    role = user.get("role")
    if role not in ["super_admin"]:
        if role == "dept_admin":
            user_dept = get_user_department(db, user["id"])
            if trip["department_id"] != user_dept:
                abort(403)
        elif trip["uploaded_by"] != user["id"]:
            user_dept = get_user_department(db, user["id"])
            if trip["department_id"] != user_dept:
                abort(403)
    
    # Get media
    media = (db.table("academic_trip_media")
            .select("*")
            .eq("trip_id", trip_id)
            .order("sequence_order")
            .execute().data or [])
    _annotate_media(media)

    return render_template(
        "academic_trips/view_trip.html",
        portal_base=_portal_base(user.get("role")),
        trip=trip,
        media=media
    )


# ============================================================================
# ROUTES - UPLOAD/CREATE
# ============================================================================

@academic_trips_bp.route("/upload", methods=["GET", "POST"])
@trainer_or_coordinator_required
def upload_trip():
    """Upload new trip report"""
    db = get_service_client()
    user = current_user()
    
    if request.method == "GET":
        # Get user's department classes (super_admin: all classes)
        classes = []
        if user.get("role") == "super_admin":
            classes = (db.table("classes")
                      .select("id, name, department_id")
                      .order("name")
                      .execute().data or [])
        else:
            dept_id = get_user_department(db, user["id"])
            if dept_id:
                classes = (db.table("classes")
                          .select("id, name, department_id")
                          .eq("department_id", dept_id)
                          .order("name")
                          .execute().data or [])

        return render_template(
            "academic_trips/upload_form.html",
            portal_base=_portal_base(user.get("role")),
            classes=classes,
        )
    
    # POST: Handle form submission
    try:
        # Get form data - convert to uppercase
        trip_title = request.form.get("trip_title", "").strip().upper()
        destination = request.form.get("destination", "").strip().upper()
        trip_date = request.form.get("trip_date")
        class_id = request.form.get("class_id")
        term = request.form.get("term")
        year = request.form.get("year")
        num_trainees = request.form.get("number_of_trainees")
        num_trainers = request.form.get("number_of_trainers")
        accompanying_trainers = request.form.get("accompanying_trainers", "").strip().upper()
        report_description = request.form.get("report_description", "").strip()
        objectives = request.form.get("objectives", "").strip()
        outcomes = request.form.get("outcomes", "").strip()
        
        # Validation
        if not all([trip_title, destination, trip_date, class_id, term, year, num_trainees, num_trainers]):
            flash("Please fill in all required fields.", "error")
            return redirect(url_for("academic_trips.upload_trip"))
        
        # Get department from class
        class_data = db.table("classes").select("department_id").eq("id", class_id).single().execute().data
        if not class_data:
            flash("Invalid class selected.", "error")
            return redirect(url_for("academic_trips.upload_trip"))
        
        department_id = class_data["department_id"]
        
        # Create trip record
        trip_data = {
            "trip_title": trip_title,
            "destination": destination,
            "trip_date": trip_date,
            "class_id": class_id,
            "department_id": department_id,
            "term": int(term),
            "year": int(year),
            "number_of_trainees": int(num_trainees),
            "number_of_trainers": int(num_trainers),
            "accompanying_trainers": accompanying_trainers,
            "report_description": report_description,
            "objectives": objectives,
            "outcomes": outcomes,
            "uploaded_by": user["id"],
            # DB CHECK allows trainer | trip_coordinator only
            "uploader_role": (
                "trip_coordinator"
                if user.get("role") == "trip_coordinator"
                else "trainer"
            ),
            "status": "submitted"
        }
        
        result = db.table("academic_trips").insert(trip_data).execute()
        trip_id = result.data[0]["id"]
        
        flash("Trip report uploaded successfully! You can now add photos/videos.", "success")
        return redirect(url_for("academic_trips.add_media", trip_id=trip_id))
        
    except Exception as e:
        flash(f"Error uploading trip: {str(e)}", "error")
        return redirect(url_for("academic_trips.upload_trip"))


@academic_trips_bp.route("/<trip_id>/add-media", methods=["GET", "POST"])
@trainer_or_coordinator_required
def add_media(trip_id):
    """Add photos/videos to trip"""
    db = get_service_client()
    user = current_user()

    trip = (db.table("academic_trips")
              .select("*")
              .eq("id", trip_id)
              .limit(1)
              .execute().data or [None])[0]
    if not trip:
        abort(404)

    # Owner or super_admin may manage media
    if trip["uploaded_by"] != user["id"] and user.get("role") != "super_admin":
        abort(403)

    if request.method == "GET":
        media = (db.table("academic_trip_media")
                .select("*")
                .eq("trip_id", trip_id)
                .order("sequence_order")
                .execute().data or [])
        _annotate_media(media)
        return render_template(
            "academic_trips/add_media.html",
            portal_base=_portal_base(user.get("role")),
            trip=trip,
            media=media
        )

    # POST: multipart upload (AJAX or form)
    files = request.files.getlist("files") or request.files.getlist("file")
    if not files:
        single = request.files.get("file")
        if single:
            files = [single]

    if not files:
        if request.accept_mimetypes.best == "application/json" or request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"success": False, "message": "No files uploaded"}), 400
        flash("No files selected.", "error")
        return redirect(url_for("academic_trips.add_media", trip_id=trip_id))

    captions = request.form.getlist("captions") or []
    existing = (db.table("academic_trip_media")
                  .select("sequence_order")
                  .eq("trip_id", trip_id)
                  .order("sequence_order", desc=True)
                  .limit(1)
                  .execute().data or [])
    next_seq = (existing[0]["sequence_order"] + 1) if existing else 0

    uploaded = []
    errors = []

    for idx, f in enumerate(files):
        if not f or not f.filename:
            continue
        try:
            raw = f.read()
            if not raw:
                errors.append(f"{f.filename}: empty file")
                continue
            if len(raw) > MAX_MEDIA_BYTES:
                errors.append(f"{f.filename}: exceeds 50MB limit")
                continue

            ctype = (f.content_type or "").lower()
            if ctype.startswith("image/"):
                file_type = "photo"
            elif ctype.startswith("video/"):
                file_type = "video"
            else:
                # Fallback by extension
                ext = (f.filename.rsplit(".", 1)[-1] if "." in f.filename else "").lower()
                if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
                    file_type = "photo"
                    ctype = ctype or f"image/{ext}"
                elif ext in ("mp4", "mov", "avi", "webm", "mkv"):
                    file_type = "video"
                    ctype = ctype or f"video/{ext}"
                else:
                    errors.append(f"{f.filename}: unsupported type")
                    continue

            safe = _safe_filename(f.filename)
            storage_path = f"{trip_id}/{uuid.uuid4().hex}_{safe}"
            db.storage.from_(TRIP_MEDIA_BUCKET).upload(
                path=storage_path,
                file=raw,
                file_options={
                    "content-type": ctype or "application/octet-stream",
                    "content-disposition": "inline",
                },
            )

            caption = captions[idx] if idx < len(captions) else request.form.get("caption", "")
            caption = (caption or "").strip() or None

            row = {
                "trip_id": trip_id,
                "file_path": storage_path,
                "file_name": f.filename,
                "file_size": len(raw),
                "file_type": file_type,
                "caption": caption,
                "sequence_order": next_seq,
            }
            next_seq += 1
            inserted = db.table("academic_trip_media").insert(row).execute().data or []
            if inserted:
                inserted[0]["public_url"] = _supabase_public_url(storage_path)
                uploaded.append(inserted[0])
            else:
                uploaded.append({**row, "public_url": _supabase_public_url(storage_path)})
        except Exception as e:
            errors.append(f"{f.filename}: {e}")

    wants_json = (
        request.accept_mimetypes.best == "application/json"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.args.get("format") == "json"
    )
    if wants_json:
        ok = len(uploaded) > 0
        return jsonify({
            "success": ok,
            "uploaded": len(uploaded),
            "media": uploaded,
            "errors": errors,
            "message": (
                f"Uploaded {len(uploaded)} file(s)."
                + (f" Some failed: {'; '.join(errors)}" if errors else "")
            ),
        }), (200 if ok else 400)

    if uploaded:
        flash(f"Uploaded {len(uploaded)} file(s) successfully.", "success")
    if errors:
        flash("Some uploads failed: " + "; ".join(errors[:3]), "error")
    return redirect(url_for("academic_trips.add_media", trip_id=trip_id))


@academic_trips_bp.route("/<trip_id>/media/<media_id>/delete", methods=["POST"])
@trainer_or_coordinator_required
def delete_media(trip_id, media_id):
    db = get_service_client()
    user = current_user()
    trip = (db.table("academic_trips").select("id, uploaded_by")
              .eq("id", trip_id).limit(1).execute().data or [None])[0]
    if not trip:
        return jsonify({"success": False, "message": "Trip not found"}), 404
    if trip["uploaded_by"] != user["id"] and user.get("role") != "super_admin":
        return jsonify({"success": False, "message": "Access denied"}), 403

    media = (db.table("academic_trip_media").select("*")
               .eq("id", media_id).eq("trip_id", trip_id)
               .limit(1).execute().data or [None])[0]
    if not media:
        return jsonify({"success": False, "message": "Media not found"}), 404

    try:
        path = media.get("file_path")
        if path and not path.startswith("http"):
            try:
                db.storage.from_(TRIP_MEDIA_BUCKET).remove([path])
            except Exception:
                pass
        db.table("academic_trip_media").delete().eq("id", media_id).execute()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# ROUTES - MANAGEMENT (Admin)
# ============================================================================

@academic_trips_bp.route("/<trip_id>/review", methods=["POST"])
@dept_admin_or_super_required
def review_trip(trip_id):
    """Mark trip as reviewed"""
    db = get_service_client()
    user = current_user()

    review_notes = request.form.get("review_notes", "").strip()

    try:
        db.table("academic_trips").update({
            "status": "reviewed",
            "reviewed_by": user["id"],
            "reviewed_at": datetime.now().isoformat(),
            "review_notes": review_notes
        }).eq("id", trip_id).execute()

        flash("Trip report reviewed successfully.", "success")
    except Exception as e:
        flash(f"Error reviewing trip: {str(e)}", "error")

    return redirect(url_for("academic_trips.view_trip", trip_id=trip_id))


@academic_trips_bp.route("/<trip_id>/delete", methods=["POST"])
@login_required
def delete_trip(trip_id):
    """Delete trip (only by uploader or super admin)"""
    db = get_service_client()
    user = current_user()

    trip = db.table("academic_trips").select("*").eq("id", trip_id).single().execute().data
    if not trip:
        return jsonify({"success": False, "message": "Trip not found"}), 404

    if user["id"] != trip["uploaded_by"] and user.get("role") != "super_admin":
        return jsonify({"success": False, "message": "Access denied"}), 403

    try:
        media = db.table("academic_trip_media").select("*").eq("trip_id", trip_id).execute().data or []
        paths = [m["file_path"] for m in media if m.get("file_path") and not str(m["file_path"]).startswith("http")]
        if paths:
            try:
                db.storage.from_(TRIP_MEDIA_BUCKET).remove(paths)
            except Exception:
                pass

        db.table("academic_trips").delete().eq("id", trip_id).execute()
        return jsonify({"success": True, "message": "Trip deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# ============================================================================
# API ENDPOINTS (for AJAX)
# ============================================================================

@academic_trips_bp.route("/api/classes/<department_id>")
@login_required
def api_get_classes(department_id):
    """Get classes for a department"""
    db = get_service_client()
    classes = (db.table("classes")
              .select("id, name")
              .eq("department_id", department_id)
              .order("name")
              .execute().data or [])
    return jsonify(classes)
