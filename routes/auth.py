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
        elif role == "employer":
            return redirect(url_for("employer.dashboard"))
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
        return redirect(url_for("main.index"))

    if request.method == "POST":
        login_type = request.form.get("login_type")  # "staff" or "student"
        origin = request.form.get("origin", "")
        
        if login_type == "staff":
            email = request.form.get("email", "").strip()
            password = request.form.get("password", "")
            
            if not email or not password:
                flash("Email and password are required", "error")
                return render_template("auth/login.html")
            
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
                    elif role == "employer":
                        return redirect(url_for("employer.dashboard"))
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
                    
                    flash("Login successful", "success")
                    return redirect(url_for("main.index"))
            
            flash("Invalid email or password", "error")
            return render_template("auth/login.html")
            
        elif login_type == "student":
            admission_no = request.form.get("admission_no", "").strip()
            password = request.form.get("password", "")
            
            if not admission_no or not password:
                flash("Admission number and password are required", "error")
                return render_template("auth/login.html")
            
            profile = authenticate_student(admission_no, password)
            
            if profile:
                session[SESSION_USER] = profile
                # Students don't get JWT tokens, just session
                
                write_audit_log("login", target=f"student:{profile['id']}")
                
                flash("Login successful", "success")
                return redirect(url_for("student.dashboard"))
            
            flash("Invalid admission number or password", "error")
    
    return render_template("auth/login.html")


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
    
    flash("You have been logged out", "info")
    return redirect(url_for("main.index"))


# ─────────────────────────────────────────────────────────────
# FORGOT PASSWORD (staff only)
# ─────────────────────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        
        if not email:
            flash("Email is required", "error")
            return render_template("auth/forgot_password.html")
        
        # Check if user exists
        svc = get_service_client()
        try:
            res = svc.table("user_profiles").select("*").eq("email", email).limit(1).execute()
            if res.data:
                # Send password reset email via Supabase Auth
                from db import get_anon_client
                client = get_anon_client()
                client.auth.reset_password_for_email(email)
                flash("Password reset email sent. Check your inbox.", "success")
            else:
                flash("If an account exists with this email, a reset link has been sent.", "info")
        except Exception as exc:
            print(f"[auth] forgot_password error: {exc}")
            flash("Error sending reset email. Please try again.", "error")
    
    return render_template("auth/forgot_password.html")


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
