"""
routes/auth_merged.py — Unified login / logout for both systems.

Supports:
- Staff (super_admin, dept_admin, trainer): Supabase Auth (JWT)
- Students: Admission number + password hash

Uses the unified auth_utils_unified.py for authentication.
"""

import traceback
from flask import (Blueprint, render_template, request,
                   session, redirect, url_for, jsonify, flash)
from auth_utils import (
    SESSION_USER, SESSION_ACCESS, SESSION_REFRESH,
    authenticate_staff, authenticate_student,
    write_audit_log, current_user, is_authenticated,
    create_student_auth_user
)
from db import get_service_client
from extensions import limiter
from security_utils import session_safe_profile

auth_bp = Blueprint("auth", __name__)


def _ensure_profile(user_id: str, email: str) -> dict:
    """Returns the user_profiles row, creating it if missing."""
    svc = get_service_client()
    try:
        res = (svc.table("user_profiles")
                  .select("*")
                  .eq("id", user_id)
                  .limit(1)
                  .execute().data or [])
        if res:
            return res[0]
    except Exception:
        pass

    # Profile missing — create a default row
    try:
        svc.table("user_profiles").insert({
            "id":            user_id,
            "email":         email,
            "full_name":     email,
            "role":          "student",
            "is_active":     True,
        }).execute()
        res = (svc.table("user_profiles")
                  .select("*")
                  .eq("id", user_id)
                  .limit(1)
                  .execute().data or [])
        return res[0] if res else None
    except Exception as exc:
        print(f"[auth] _ensure_profile failed for {user_id}: {exc}")
        return None


# ─────────────────────────────────────────────────────────────
# LOGIN PAGE
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("8 per minute", methods=["POST"])
def login():
    db = get_service_client()
    departments = db.table("departments").select("*").order("name").execute().data or []

    if is_authenticated():
        user = current_user()
        role = user.get("role")
        if role == "super_admin":
            return redirect(url_for("super_admin.dashboard"))
        elif role == "dept_admin":
            return redirect(url_for("dept_admin.dashboard"))
        elif role == "trainer":
            return redirect(url_for("trainer.dashboard"))
        elif role == "student":
            return redirect(url_for("student.dashboard"))
        elif role == "examination_officer":
            return redirect(url_for("examination_officer.dashboard"))
        elif role == "industry_mentor":
            return redirect(url_for("industry_mentor.dashboard"))
        elif role == "internal_verifier":
            return redirect(url_for("internal_verifier.dashboard"))
        elif role == "registrar":
            return redirect(url_for("admin_oversight.registrar_dashboard"))
        elif role == "deputy_principal":
            return redirect(url_for("admin_oversight.deputy_principal_dashboard"))
        elif role == "quality_assurance_officer":
            return redirect(url_for("admin_oversight.quality_assurance_dashboard"))
        elif role in ("library_hod", "sports_hod", "service_clearance_officer"):
            return redirect(url_for("service_dept.dashboard"))
        elif role in ("environment_hod", "dean_students", "finance_officer"):
            return redirect(url_for("clearance.approver_dashboard"))
        elif role == "liaison_officer":
            return redirect(url_for("liaison_officer.dashboard"))
        elif role == "cdacc_verifier":
            return redirect(url_for("cdacc_verifier.dashboard"))
        elif role == "workshop_technician":
            return redirect(url_for("workshop_technician.dashboard"))
        return redirect(url_for("auth.profile"))

    if request.method == "POST":
        login_type = request.form.get("login_type")  # "staff" or "student"
        origin = request.form.get("origin", "")
        
        if login_type == "staff":
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            
            if not email or not password:
                flash("Email and password are required", "error")
                return render_template("auth/login.html", departments=departments)
            
            profile = authenticate_staff(email, password)
            
            if profile:
                # Session tokens are already attached by authenticate_staff — no second call needed
                sb_session = profile.pop("_session", None)
                
                if sb_session:
                    session.clear()
                    session.permanent = True
                    session[SESSION_USER] = session_safe_profile(profile)
                    session[SESSION_ACCESS] = sb_session.access_token
                    session[SESSION_REFRESH] = sb_session.refresh_token
                    
                    write_audit_log("login", target=f"user:{profile['id']}")
                    
                    # Redirect based on role
                    role = profile.get("role")
                    if role == "super_admin":
                        return redirect(url_for("super_admin.dashboard"))
                    elif role == "dept_admin":
                        return redirect(url_for("dept_admin.dashboard"))
                    elif role == "trainer":
                        return redirect(url_for("trainer.dashboard"))
                    elif role == "examination_officer":
                        return redirect(url_for("examination_officer.dashboard"))
                    elif role == "industry_mentor":
                        return redirect(url_for("industry_mentor.dashboard"))
                    elif role == "internal_verifier":
                        return redirect(url_for("internal_verifier.dashboard"))
                    elif role in ("registrar",):
                        return redirect(url_for("admin_oversight.registrar_dashboard"))
                    elif role == "deputy_principal":
                        return redirect(url_for("admin_oversight.deputy_principal_dashboard"))
                    elif role == "quality_assurance_officer":
                        return redirect(url_for("admin_oversight.quality_assurance_dashboard"))
                    elif role in ("library_hod", "sports_hod", "service_clearance_officer"):
                        return redirect(url_for("service_dept.dashboard"))
                    elif role in ("environment_hod", "dean_students", "finance_officer"):
                        return redirect(url_for("clearance.approver_dashboard"))
                    elif role == "liaison_officer":
                        return redirect(url_for("liaison_officer.dashboard"))
                    elif role == "cdacc_verifier":
                        return redirect(url_for("cdacc_verifier.dashboard"))
                    elif role == "workshop_technician":
                        return redirect(url_for("workshop_technician.dashboard"))

                    flash("Login successful", "success")
                    return redirect(url_for("auth.profile"))
            
            flash("Invalid email or password", "error")
            return render_template("auth/login.html", departments=departments)
            
        elif login_type == "student":
            admission_no = request.form.get("admission_no", "").strip()
            password = request.form.get("password", "")
            
            if not admission_no or not password:
                flash("Admission number and password are required", "error")
                return render_template("auth/login.html", departments=departments)
            
            profile = authenticate_student(admission_no, password)
            
            if profile:
                session.clear()
                session.permanent = True
                session[SESSION_USER] = session_safe_profile(profile)
                # Students don't get JWT tokens, just session
                
                write_audit_log("login", target=f"student:{profile['id']}")
                
                if profile.get("must_change_password"):
                    flash("Please set a new password to continue.", "warning")
                    return redirect(url_for("auth.change_password"))
                flash("Login successful", "success")
                return redirect(url_for("student.dashboard"))
            
            flash("Invalid admission number or password", "error")
    
    return render_template("auth/login.html", departments=departments)


# ─────────────────────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/logout")
def logout():
    user = current_user()
    if user:
        write_audit_log("logout", target=f"user:{user['id']}")
    
    # Clear Supabase Auth session if exists
    if SESSION_ACCESS in session:
        try:
            from db import get_anon_client
            client = get_anon_client()
            client.auth.sign_out()
        except Exception:
            pass
    
    # Clear all session data
    session.clear()
    
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("main.index"))


# ─────────────────────────────────────────────────────────────
# FORGOT PASSWORD (trainees must contact admin — no self-reset)
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def forgot_password():
    """
    Public self-service password reset is disabled for security.
    Admission-number-only resets previously allowed account takeover.
    """
    info = None
    if request.method == "POST":
        # Always show the same message (no account enumeration / no password reset).
        info = (
            "Password reset is handled by your department administrator or Super Admin. "
            "Visit the campus office with your admission number and a valid ID."
        )
        write_audit_log(
            "password_reset_request_denied",
            target=f"admission:{(request.form.get('admission_no') or '').strip()[:40]}",
        )

    return render_template(
        "auth/forgot_password.html",
        generated_password=None,
        trainee_name=None,
        error=None,
        info=info,
    )


# ─────────────────────────────────────────────────────────────
# CHANGE PASSWORD (for students)
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if not is_authenticated():
        return redirect(url_for("auth.login"))
    
    user = current_user()
    
    if request.method == "POST":
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if not current_password or not new_password or not confirm_password:
            flash("All fields are required", "error")
            return render_template("auth/change_password.html")
        
        if new_password != confirm_password:
            flash("New passwords do not match", "error")
            return render_template("auth/change_password.html")
        
        if len(new_password) < 8:
            flash("Password must be at least 8 characters", "error")
            return render_template("auth/change_password.html")
        
        # Verify current password
        if user.get("role") == "student":
            from werkzeug.security import check_password_hash, generate_password_hash
            svc = get_service_client()
            row = (svc.table("user_profiles")
                   .select("password_hash")
                   .eq("id", user["id"])
                   .limit(1)
                   .execute().data or [None])[0]
            stored = (row or {}).get("password_hash") or ""
            if not stored or not check_password_hash(stored, current_password):
                flash("Current password is incorrect", "error")
                return render_template("auth/change_password.html")
            
            # Update password
            svc.table("user_profiles").update({
                "password_hash": generate_password_hash(new_password),
                "must_change_password": False
            }).eq("id", user["id"]).execute()

            # Refresh session flag without secrets
            safe = session_safe_profile(dict(user)) or {}
            safe["must_change_password"] = False
            session[SESSION_USER] = safe
            
            write_audit_log("password_change", target=f"user:{user['id']}")
            flash("Password changed successfully", "success")
            return redirect(url_for("student.dashboard"))
        else:
            # Staff use Supabase Auth / admin credential reset
            flash("Staff password changes are handled by Super Admin (Credentials).", "info")
            return render_template("auth/change_password.html")
    
    return render_template("auth/change_password.html")


# ─────────────────────────────────────────────────────────────
# STUDENT REGISTRATION (if enabled)
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/student/register", methods=["GET", "POST"])
@limiter.limit("3 per minute", methods=["POST"])
def student_register():
    """Student self-registration (disabled unless ALLOW_STUDENT_SELF_REGISTER=true)."""
    import os
    from flask import abort
    if os.environ.get("ALLOW_STUDENT_SELF_REGISTER", "").lower() not in ("1", "true", "yes"):
        abort(404)

    if request.method == "POST":
        admission_no = request.form.get("admission_no", "").strip()
        email = request.form.get("email", "").strip()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        
        if not all([admission_no, email, full_name, password, confirm_password]):
            flash("All fields are required", "error")
            return render_template("auth/student_register.html")
        
        if password != confirm_password:
            flash("Passwords do not match", "error")
            return render_template("auth/student_register.html")
        
        if len(password) < 8:
            flash("Password must be at least 8 characters", "error")
            return render_template("auth/student_register.html")
        
        # Check if admission number already exists
        svc = get_service_client()
        try:
            res = svc.table("user_profiles").select("id").eq("admission_no", admission_no).limit(1).execute()
            if res.data:
                flash("Admission number already registered", "error")
                return render_template("auth/student_register.html")
            
            # Check if email already exists
            res = svc.table("user_profiles").select("id").eq("email", email).limit(1).execute()
            if res.data:
                flash("Email already registered", "error")
                return render_template("auth/student_register.html")
            
            # Create inactive until admin approval (no race with is_active=True)
            create_student_auth_user(
                admission_no=admission_no,
                password=password,
                email=email,
                full_name=full_name,
                department_id=None,
                class_id=None,
                is_active=False,
            )
            
            flash("Registration successful. Please wait for admin approval before logging in.", "success")
            return redirect(url_for("auth.login"))
            
        except Exception as exc:
            print(f"[auth] student_register error: {exc}")
            flash("Registration failed. Please try again.", "error")
    
    return render_template("auth/student_register.html")


# ─────────────────────────────────────────────────────────────
# UNIFIED USER PROFILE AND PASSWORD MANAGEMENT
# ─────────────────────────────────────────────────────────────
import uuid
from werkzeug.security import generate_password_hash
from auth_utils import login_required

def _get_base_template(role: str) -> str:
    mapping = {
        "super_admin": "super_admin/base.html",
        "dept_admin": "dept_admin/base.html",
        "trainer": "trainer/base.html",
        "student": "student/base.html",
        "examination_officer": "examination_officer/base.html",
        "industry_mentor": "industry_mentor/base.html",
        "internal_verifier": "internal_verifier/base.html",
        "registrar": "admin_oversight/base.html",
        "deputy_principal": "admin_oversight/base.html",
        "quality_assurance_officer": "admin_oversight/base.html"
    }
    if role in ("library_hod", "sports_hod", "service_clearance_officer"):
        return "service_dept/base.html"
    if role in ("environment_hod", "dean_students", "finance_officer",
                "registrar", "deputy_principal", "quality_assurance_officer"):
        return "admin_oversight/base.html"
    return mapping.get(role, "dept_admin/base.html")


@auth_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    db = get_service_client()
    user = current_user()
    user_id = user["id"]
    
    if request.method == "POST":
        form_action = request.form.get("form_action")
        
        if form_action == "details":
            mobile_number = request.form.get("mobile_number", "").strip()
            full_name = request.form.get("full_name", "").strip()
            try:
                db.table("user_profiles").update({
                    "mobile_number": mobile_number,
                    "full_name": full_name
                }).eq("id", user_id).execute()
                
                # Refresh session user
                user["mobile_number"] = mobile_number
                user["full_name"] = full_name
                session[SESSION_USER] = session_safe_profile(user)
                
                write_audit_log("update_profile_details", target=f"user:{user_id}")
                flash("Profile details updated successfully.", "success")
            except Exception as e:
                flash(f"Error updating profile: {e}", "danger")
                
        elif form_action == "passport":
            if 'passport' not in request.files:
                flash('No file selected.', 'danger')
                return redirect(url_for("auth.profile"))
            
            file = request.files['passport']
            if file.filename == '':
                flash('No file selected.', 'danger')
                return redirect(url_for("auth.profile"))
            
            ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
            if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                flash('Invalid file type. Use JPG, JPEG, PNG, or WEBP.', 'danger')
                return redirect(url_for("auth.profile"))
            
            try:
                from security_utils import allowed_upload
                file_bytes = file.read()
                ok_up, err_up = allowed_upload(
                    file.filename, file_bytes,
                    allowed_ext=("jpg", "jpeg", "png", "webp"),
                    max_bytes=2 * 1024 * 1024,
                )
                if not ok_up:
                    flash(err_up, "danger")
                    return redirect(url_for("auth.profile"))
                filename = f"passports/{user_id}_{uuid.uuid4().hex}.{ext}"
                storage_client = db.storage
                storage_client.from_("assessment-evidence").upload(
                    filename,
                    file_bytes,
                    {"content-type": f"image/{ext}" if ext != 'jpg' else 'image/jpeg'}
                )
                
                # Store storage path (not a permanent public URL)
                db.table("user_profiles").update({
                    "passport_file_path": filename,
                    "passport_file_name": file.filename
                }).eq("id", user_id).execute()
                
                # Refresh session user
                user["passport_file_path"] = filename
                user["passport_file_name"] = file.filename
                session[SESSION_USER] = session_safe_profile(user)
                
                write_audit_log("upload_passport", target=f"user:{user_id}")
                flash('Passport photo uploaded successfully.', 'success')
            except Exception as e:
                flash(f'Error uploading passport: {e}', 'danger')
                
        elif form_action == "password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            
            if len(new_password) < 8 or not any(c.isdigit() for c in new_password) or not any(c in "!@#$" for c in new_password):
                flash("Password must be at least 8 characters with at least one number and one symbol (!@#$).", "danger")
                return redirect(url_for("auth.profile"))
                
            if new_password != confirm_password:
                flash("Passwords do not match.", "danger")
                return redirect(url_for("auth.profile"))

            if not current_password:
                flash("Current password is required.", "danger")
                return redirect(url_for("auth.profile"))
                
            try:
                if user.get("role") == "student":
                    from werkzeug.security import check_password_hash
                    row = (db.table("user_profiles")
                           .select("password_hash")
                           .eq("id", user_id)
                           .limit(1)
                           .execute().data or [None])[0]
                    stored = (row or {}).get("password_hash") or ""
                    if not stored or not check_password_hash(stored, current_password):
                        flash("Current password is incorrect.", "danger")
                        return redirect(url_for("auth.profile"))
                    db.table("user_profiles").update({
                        "password_hash": generate_password_hash(new_password),
                        "must_change_password": False,
                    }).eq("id", user_id).execute()
                else:
                    # Staff: require current password via Supabase sign-in
                    from db import get_anon_client
                    email = user.get("email") or ""
                    try:
                        get_anon_client().auth.sign_in_with_password({
                            "email": email,
                            "password": current_password,
                        })
                    except Exception:
                        flash("Current password is incorrect.", "danger")
                        return redirect(url_for("auth.profile"))
                    db.auth.admin.update_user_by_id(user_id, {"password": new_password})
                    
                write_audit_log("change_password", target=f"user:{user_id}")
                flash("Password changed successfully.", "success")
            except Exception:
                flash("Error changing password.", "danger")
                
            return redirect(url_for("auth.profile"))
            
    # Fetch updated user profile (never select password_hash into templates)
    student = (db.table("user_profiles")
               .select("id, full_name, email, role, admission_no, staff_no, mobile_number, "
                       "department_id, is_active, must_change_password, passport_file_path, "
                       "passport_file_name, departments(name)")
               .eq("id", user_id).single().execute().data)
    base_template = _get_base_template(user.get("role"))
    
    return render_template("auth/profile.html", student=student, base_template=base_template)
