"""
auth_utils_unified.py — Unified Authentication helpers and RBAC decorators.

Combines both systems:
- Staff (super_admin, dept_admin, trainer): Supabase Auth (JWT)
- Students: Password hash in user_profiles table

All role checks are enforced here in Python (backend), in addition to
Supabase RLS. Never rely on frontend-only checks.
"""

import traceback
from functools import wraps
from typing import Optional
from flask import session, redirect, url_for, abort, request
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_service_client, get_anon_client
from security_utils import session_safe_profile


# ── Session keys ──────────────────────────────────────────────────────────────
SESSION_USER    = "sb_user"
SESSION_ACCESS  = "sb_access_token"
SESSION_REFRESH = "sb_refresh_token"


# ── Role definitions ────────────────────────────────────────────────────────────
STAFF_ROLES = frozenset({
    'super_admin', 'dept_admin', 'trainer', 'employer',
    'examination_officer', 'industry_mentor', 'internal_verifier',
    'sports_hod', 'environment_hod', 'dean_students', 'library_hod',
    'finance_officer', 'registrar', 'deputy_principal',
    'quality_assurance_officer',
    # New roles
    'workshop_technician', 'liaison_officer', 'cdacc_verifier',
    'service_clearance_officer',
})
ALL_ROLES = frozenset({
    'super_admin', 'dept_admin', 'trainer', 'student', 'employer',
    'examination_officer', 'industry_mentor', 'internal_verifier',
    'sports_hod', 'environment_hod', 'dean_students', 'library_hod',
    'finance_officer', 'registrar', 'deputy_principal',
    'quality_assurance_officer',
    # New roles
    'workshop_technician', 'liaison_officer', 'cdacc_verifier',
    'service_clearance_officer',
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def current_user() -> Optional[dict]:
    return session.get(SESSION_USER)


def is_authenticated() -> bool:
    user = session.get(SESSION_USER)
    # Field in user_profiles is "is_active", not "active"
    return bool(user and user.get("is_active", False))


def load_user_profile(user_id: str) -> Optional[dict]:
    """Fetch user_profiles row using the service client (bypasses RLS)."""
    try:
        svc = get_service_client()
        res = svc.table("user_profiles").select("*").eq("id", user_id).limit(1).execute()
        if res.data and len(res.data) > 0:
            return res.data[0]
        return None
    except Exception as exc:
        print(f"[auth_utils] load_user_profile error for {user_id}: {exc}")
        return None


def refresh_session_if_needed():
    """
    Called before each request. Attempts to refresh the JWT using the
    stored refresh token. Silently skips on any error.
    """
    if SESSION_REFRESH not in session or SESSION_ACCESS not in session:
        return
    try:
        client = get_anon_client()
        resp = client.auth.refresh_session(session[SESSION_REFRESH])
        if resp and resp.session:
            session[SESSION_ACCESS]  = resp.session.access_token
            session[SESSION_REFRESH] = resp.session.refresh_token
    except Exception:
        # Token may be expired — user will be redirected to login on next
        # protected route access. Do not crash here.
        pass


def write_audit_log(action: str, target: str = None, detail: dict = None):
    """Write to system_logs using the service client. Never raises."""
    user = current_user()
    try:
        svc = get_service_client()
        svc.table("system_logs").insert({
            "actor_id":   user["id"]   if user else None,
            "actor_role": user["role"] if user else None,
            "action":     action,
            "target":     target,
            "detail":     detail,
            "ip_address": request.remote_addr,
        }).execute()
    except Exception:
        pass  # logging must never break the main flow


# ── Authentication Functions ───────────────────────────────────────────────────

def authenticate_staff(email: str, password: str) -> Optional[dict]:
    """
    Staff login: Supabase Auth only.
    Returns User profile dict (with '_session' key holding the Supabase session)
    or None on failure.

    Special rules:
    - Employers must be verified (employers.is_verified = True) to log in.
    - All other staff must have is_active = True.
    """
    import logging
    log = logging.getLogger(__name__)

    email = email.strip().lower()

    try:
        svc = get_service_client()
        profile_res = svc.table("user_profiles").select("*").eq("email", email).limit(1).execute()

        if not profile_res.data:
            return None

        profile = profile_res.data[0]

        if profile["role"] not in STAFF_ROLES:
            return None

        # Block inactive accounts
        if not profile.get("is_active", False):
            return None

        # Employers must be verified by super admin before they can log in
        if profile["role"] == "employer":
            emp_res = svc.table("employers").select("is_verified").eq("profile_id", profile["id"]).limit(1).execute()
            if not emp_res.data or not emp_res.data[0].get("is_verified", False):
                # Return a special sentinel so the login route can show the right message
                profile["_unverified_employer"] = True
                return session_safe_profile(profile)

        # Authenticate via Supabase Auth
        client = get_anon_client()
        result = client.auth.sign_in_with_password({
            'email': email,
            'password': password,
        })

        if result and result.user and result.session:
            safe = session_safe_profile(profile) or {}
            safe["_session"] = result.session
            return safe

        return None
    except Exception as exc:
        err = str(exc).lower()
        if any(k in err for k in ('invalid', 'credentials', 'wrong', 'incorrect',
                                   'email not confirmed', 'invalid login')):
            log.warning('Supabase Auth rejected login for %s: %s', email, exc)
            return None
        log.warning('Supabase Auth error for %s (%s)', email, exc)
        return None


def authenticate_student(admission_no: str, password: str) -> Optional[dict]:
    """
    Student login: Admission number + password hash.
    Returns User profile or None.
    """
    try:
        svc = get_service_client()
        res = svc.table("user_profiles").select("*").eq("admission_no", admission_no).eq("role", "student").limit(1).execute()
        
        if not res.data or len(res.data) == 0:
            return None
            
        profile = res.data[0]

        if not profile.get("is_active", False):
            return None
        
        if not profile.get("password_hash"):
            return None
            
        if check_password_hash(profile["password_hash"], password):
            return session_safe_profile(profile)
            
        return None
    except Exception as exc:
        print(f"[auth_utils] authenticate_student error: {exc}")
        return None


def create_student_auth_user(admission_no: str, password: str, email: str, full_name: str,
                             department_id: str, class_id: str,
                             mobile_number: str = None) -> str:
    """
    Create a student user with password hash.
    Returns the user UUID.
    """
    import uuid

    # Generate UUID for the user
    user_id = str(uuid.uuid4())

    # Create in Supabase Auth (for consistency, but student won't use it)
    try:
        svc = get_service_client()
        response = svc.auth.admin.create_user({
            'email': email,
            'password': password,
            'email_confirm': True,
            'user_metadata': {'admission_no': admission_no}
        })
        if response and response.user:
            user_id = str(response.user.id)
    except Exception as exc:
        print(f"[auth_utils] Warning: Could not create Supabase Auth user for student: {exc}")
        # Continue with local UUID
    
    # Create user profile
    profile = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "role": "student",
        "admission_no": admission_no,
        "department_id": department_id,
        "password_hash": generate_password_hash(password),
        "is_active": True,
    }
    if mobile_number:
        profile["mobile_number"] = mobile_number
    svc = get_service_client()
    svc.table("user_profiles").insert(profile).execute()
    return user_id


def create_staff_auth_user(email: str, password: str, full_name: str, role: str,
                           department_id: str = None, staff_no: str = None,
                           mobile_number: str = None) -> str:
    """
    Create staff user in Supabase Auth.
    Returns the auth user UUID.
    """
    svc = get_service_client()
    response = svc.auth.admin.create_user({
        'email': email,
        'password': password,
        'email_confirm': True,
        'user_metadata': {'full_name': full_name, 'role': role}
    })

    if not response or not response.user:
        raise RuntimeError('Supabase Auth did not return a user.')

    user_id = str(response.user.id)

    profile = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "role": role,
        "department_id": department_id,
        "is_active": True,
    }
    if staff_no:
        profile["staff_no"] = staff_no
    if mobile_number:
        profile["mobile_number"] = mobile_number

    svc.table("user_profiles").insert(profile).execute()
    return user_id


# ── Password management (admin credential tools) ───────────────────────────────

def generate_temp_password(length: int = 8) -> str:
    """Generate a readable temporary password (no ambiguous chars)."""
    import secrets
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def reset_user_password(user_id: str, new_password: str) -> tuple[bool, str]:
    """
    Reset/set a user's password, choosing the correct backend by role:
      - Students → Werkzeug hash in user_profiles.password_hash
      - Staff    → Supabase Auth (auth.admin.update_user_by_id)
    Also flags must_change_password so the user is prompted to change it.
    Returns (success, message). Never raises.
    """
    if not user_id or not new_password:
        return False, "Missing user or password."
    try:
        svc = get_service_client()
        profile = load_user_profile(user_id)
        if not profile:
            return False, "User not found."
        role = profile.get("role")

        if role == "student":
            svc.table("user_profiles").update({
                "password_hash": generate_password_hash(new_password),
                "must_change_password": True,
            }).eq("id", user_id).execute()
        else:
            # Staff live in Supabase Auth — update the auth password there.
            try:
                svc.auth.admin.update_user_by_id(user_id, {"password": new_password})
            except Exception as exc:
                return False, f"Could not update staff password: {exc}"
            # Best-effort flag; column exists on user_profiles.
            try:
                svc.table("user_profiles").update(
                    {"must_change_password": True}
                ).eq("id", user_id).execute()
            except Exception:
                pass

        write_audit_log("password_reset", target=f"{role}:{user_id}")
        return True, "Password updated successfully."
    except Exception as exc:
        return False, f"Error updating password: {exc}"


# ── RBAC Decorators ───────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_authenticated():
            return redirect(url_for("auth.login"))
        user = current_user()
        if user and user.get("must_change_password"):
            endpoint = (request.endpoint or "")
            allowed = {
                "auth.change_password",
                "auth.logout",
                "api_v1.api_logout",
                "api_v1.api_me",
                "api_v1.api_csrf_token",
            }
            if endpoint not in allowed and not str(endpoint).startswith("static"):
                from flask import flash
                flash("You must change your temporary password before continuing.", "warning")
                return redirect(url_for("auth.change_password"))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    """
    Enforce one or more allowed roles.
    Usage:  @role_required('super_admin')
            @role_required('super_admin', 'dept_admin')
    """
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not is_authenticated():
                return redirect(url_for("auth.login"))
            user = current_user()
            if not user or user.get("role") not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated
    return decorator


def super_admin_required(f):
    return role_required("super_admin")(f)


def dept_admin_required(f):
    # super_admin can also access dept_admin pages
    return role_required("super_admin", "dept_admin")(f)


def trainer_required(f):
    return role_required("trainer")(f)


def student_required(f):
    return role_required("student")(f)


def employer_required(f):
    return role_required("employer")(f)


def examination_officer_required(f):
    return role_required("examination_officer")(f)


def industry_mentor_required(f):
    return role_required("industry_mentor")(f)


def internal_verifier_required(f):
    return role_required("internal_verifier")(f)


def sports_hod_required(f):
    return role_required("sports_hod")(f)


def environment_hod_required(f):
    return role_required("environment_hod")(f)


def dean_students_required(f):
    return role_required("dean_students")(f)


def library_hod_required(f):
    return role_required("library_hod")(f)


def finance_officer_required(f):
    return role_required("finance_officer")(f)


def registrar_required(f):
    return role_required("registrar")(f)


def deputy_principal_required(f):
    return role_required("deputy_principal")(f)


def quality_assurance_officer_required(f):
    return role_required("quality_assurance_officer")(f)


def workshop_technician_required(f):
    return role_required("workshop_technician")(f)


def liaison_officer_required(f):
    return role_required("liaison_officer")(f)


def cdacc_verifier_required(f):
    return role_required("cdacc_verifier")(f)


def dept_isolation_check(department_id: str) -> bool:
    """
    Returns True if the current user may access the given department.
    super_admin can access any dept; others only their own.
    """
    user = current_user()
    if not user:
        return False
    if user["role"] == "super_admin":
        return True
    return user.get("department_id") == department_id
