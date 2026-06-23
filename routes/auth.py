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
        elif role in ("library_hod", "sports_hod"):
            return redirect(url_for("clearance.service_dept_dashboard"))
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
                    session[SESSION_USER] = profile
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
                    elif role in ("library_hod", "sports_hod"):
                        return redirect(url_for("clearance.service_dept_dashboard"))
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
                session[SESSION_USER] = profile
                # Students don't get JWT tokens, just session
                
                write_audit_log("login", target=f"student:{profile['id']}")
                
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
# FORGOT PASSWORD (trainee — generates system password shown on screen)
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    generated_password = None
    trainee_name = None
    error = None

    if request.method == "POST":
        admission_no = request.form.get("admission_no", "").strip()

        if not admission_no:
            error = "Admission number is required."
        else:
            svc = get_service_client()
            try:
                res = svc.table("user_profiles").select("id, full_name, role").eq("admission_no", admission_no).limit(1).execute()
                trainee = res.data[0] if res.data else None

                if not trainee or trainee.get("role") != "student":
                    error = "No trainee account found with that admission number."
                else:
                    import random, string
                    from werkzeug.security import generate_password_hash
                    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits
                    new_password = ''.join(random.choices(chars, k=10))
                    svc.table("user_profiles").update({
                        "password_hash": generate_password_hash(new_password),
                        "must_change_password": True
                    }).eq("id", trainee["id"]).execute()
                    write_audit_log("password_reset_generated", target=f"student:{trainee['id']}")
                    generated_password = new_password
                    trainee_name = trainee.get("full_name", "Trainee")
            except Exception as exc:
                print(f"[auth] forgot_password error: {exc}")
                error = "An error occurred. Please try again."

    return render_template("auth/forgot_password.html",
                           generated_password=generated_password,
                           trainee_name=trainee_name,
                           error=error)


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
            if not check_password_hash(user.get("password_hash", ""), current_password):
                flash("Current password is incorrect", "error")
                return render_template("auth/change_password.html")
            
            # Update password
            svc = get_service_client()
            svc.table("user_profiles").update({
                "password_hash": generate_password_hash(new_password),
                "must_change_password": False
            }).eq("id", user["id"]).execute()
            
            write_audit_log("password_change", target=f"user:{user['id']}")
            flash("Password changed successfully", "success")
            return redirect(url_for("student.dashboard"))
        else:
            # Staff use Supabase Auth
            flash("Staff should use the forgot password feature", "info")
            return render_template("auth/change_password.html")
    
    return render_template("auth/change_password.html")


# ─────────────────────────────────────────────────────────────
# STUDENT REGISTRATION (if enabled)
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/student/register", methods=["GET", "POST"])
def student_register():
    """Student self-registration (if enabled by admin)."""
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
            res = svc.table("user_profiles").select("*").eq("admission_no", admission_no).limit(1).execute()
            if res.data:
                flash("Admission number already registered", "error")
                return render_template("auth/student_register.html")
            
            # Check if email already exists
            res = svc.table("user_profiles").select("*").eq("email", email).limit(1).execute()
            if res.data:
                flash("Email already registered", "error")
                return render_template("auth/student_register.html")
            
            # Create student user
            user_id = create_student_auth_user(
                admission_no=admission_no,
                password=password,
                email=email,
                full_name=full_name,
                department_id=None,  # Will be assigned by admin
                class_id=None
            )
            
            flash("Registration successful. Please wait for admin approval.", "success")
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
    if role in ("sports_hod", "environment_hod", "dean_students", "library_hod", "finance_officer"):
        return "clearance_approver/base.html"
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
                session[SESSION_USER] = user
                
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
                filename = f"passports/{user_id}_{uuid.uuid4().hex}.{ext}"
                storage_client = db.storage
                storage_client.from_("assessment-evidence").upload(
                    filename,
                    file.read(),
                    {"content-type": f"image/{ext}" if ext != 'jpg' else 'image/jpeg'}
                )
                
                public_url = storage_client.from_("assessment-evidence").get_public_url(filename)
                
                db.table("user_profiles").update({
                    "passport_file_path": public_url,
                    "passport_file_name": file.filename
                }).eq("id", user_id).execute()
                
                # Refresh session user
                user["passport_file_path"] = public_url
                user["passport_file_name"] = file.filename
                session[SESSION_USER] = user
                
                write_audit_log("upload_passport", target=f"user:{user_id}")
                flash('Passport photo uploaded successfully.', 'success')
            except Exception as e:
                flash(f'Error uploading passport: {e}', 'danger')
                
        elif form_action == "password":
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")
            
            if len(new_password) < 8 or not any(c.isdigit() for c in new_password) or not any(c in "!@#$" for c in new_password):
                flash("Password must be at least 8 characters with at least one number and one symbol (!@#$).", "danger")
                return redirect(url_for("auth.profile"))
                
            if new_password != confirm_password:
                flash("Passwords do not match.", "danger")
                return redirect(url_for("auth.profile"))
                
            try:
                if user.get("role") == "student":
                    # Students: password hash
                    db.table("user_profiles").update({
                        "password_hash": generate_password_hash(new_password)
                    }).eq("id", user_id).execute()
                else:
                    # Staff: Supabase Auth
                    db.auth.admin.update_user_by_id(user_id, {"password": new_password})
                    
                write_audit_log("change_password", target=f"user:{user_id}")
                flash("Password changed successfully.", "success")
            except Exception as e:
                flash(f"Error changing password: {e}", "danger")
                
            return redirect(url_for("auth.profile"))
            
    # Fetch updated user profile
    student = db.table("user_profiles").select("*, departments(name)").eq("id", user_id).single().execute().data
    base_template = _get_base_template(user.get("role"))
    
    return render_template("auth/profile.html", student=student, base_template=base_template)
