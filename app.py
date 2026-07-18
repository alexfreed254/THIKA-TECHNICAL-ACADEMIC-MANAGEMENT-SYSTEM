"""
app.py — Unified Flask application entry point.
Combines Attendance Management + E-Portfolio Management
Hosted on Render. Database + Auth via Supabase.
"""

import os
import traceback
from datetime import timedelta, datetime
from flask import Flask, render_template
from dotenv import load_dotenv
from werkzeug.middleware.proxy_fix import ProxyFix

load_dotenv()

app = Flask(__name__)
# Fallback secret key for local dev — always set SECRET_KEY in production
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

# ── Session / Cookie config ───────────────────────────────────────────────────
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"   # "None" requires HTTPS everywhere
app.config["SESSION_COOKIE_SECURE"] = False    # Set True when behind HTTPS on Render
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=1)

# ── Reverse-proxy support (Render sits behind a load balancer) ────────────────
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# ── Refresh JWT before every request ─────────────────────────────────────────
from auth_utils import refresh_session_if_needed

@app.before_request
def before_request():
    try:
        refresh_session_if_needed()
    except Exception:
        pass  # never block a request due to token refresh failure

# ── Blueprints ────────────────────────────────────────────────────────────────
from routes.auth import auth_bp
from routes.super_admin import super_admin_bp
from routes.dept_admin import dept_admin_bp
from routes.trainer import trainer_bp
from routes.student import student_bp
from routes.examination_officer import examination_officer_bp
from routes.industry_mentor import industry_mentor_bp
from routes.internal_verifier import internal_verifier_bp
from routes.clearance import clearance_bp
from routes.admin_oversight import admin_oversight_bp
from routes.notifications import notifications_bp
from routes.main import main_bp
from routes.liaison_officer import liaison_officer_bp
from routes.cdacc_verifier import cdacc_verifier_bp
from routes.workshop_technician import workshop_technician_bp
from routes.biometric_attendance import biometric_bp
from routes.ai import ai_bp
from routes.service_dept import service_dept_bp
from routes.academic_trips import academic_trips_bp
from routes.summative import summative_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(super_admin_bp, url_prefix="/super-admin")
app.register_blueprint(dept_admin_bp, url_prefix="/dept-admin")
app.register_blueprint(trainer_bp, url_prefix="/trainer")
app.register_blueprint(student_bp, url_prefix="/student")
app.register_blueprint(examination_officer_bp, url_prefix="/examination-officer")
app.register_blueprint(industry_mentor_bp, url_prefix="/industry-mentor")
app.register_blueprint(internal_verifier_bp, url_prefix="/internal-verifier")
app.register_blueprint(clearance_bp, url_prefix="/clearance")
app.register_blueprint(admin_oversight_bp, url_prefix="/admin-oversight")
app.register_blueprint(notifications_bp, url_prefix="/notifications")
app.register_blueprint(liaison_officer_bp, url_prefix="/liaison-officer")
app.register_blueprint(cdacc_verifier_bp, url_prefix="/cdacc-verifier")
app.register_blueprint(workshop_technician_bp, url_prefix="/workshop-technician")
app.register_blueprint(biometric_bp, url_prefix="/biometric")
app.register_blueprint(ai_bp)
app.register_blueprint(service_dept_bp, url_prefix="/service-dept")
app.register_blueprint(academic_trips_bp)
app.register_blueprint(summative_bp)

# ── Template globals ──────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    from auth_utils import current_user
    from notifications import get_unread_count

    user = current_user()
    unread_count = 0
    dept_name = None

    if user:
        unread_count = get_unread_count(user["id"])

        # Fetch department name if user is associated with a department
        if user.get("department_id"):
            try:
                from db import get_service_client

                svc = get_service_client()
                dept_row = (
                    svc.table("departments")
                    .select("name")
                    .eq("id", user["department_id"])
                    .single()
                    .execute()
                    .data
                )
                if dept_row:
                    dept_name = dept_row.get("name")
            except Exception:
                pass

    # Helper to map notification types to Tailwind alert classes
    def get_alert_classes(ntype):
        mapping = {
            "success": "bg-green-50 border-green-200 text-green-800",
            "warning": "bg-yellow-50 border-yellow-200 text-yellow-800",
            "error": "bg-red-50 border-red-200 text-red-800",
            "info": "bg-blue-50 border-blue-200 text-blue-800",
        }
        return mapping.get(ntype, mapping["info"])

    supabase_url = os.environ.get("SUPABASE_URL", "").strip()

    def storage_url(bucket, path):
        if not path:
            return ""
        return f"{supabase_url}/storage/v1/object/public/{bucket}/{path}"

    def get_file_icon_class(url):
        if not url:
            return ''
        ext = str(url).split('.')[-1].lower()
        if ext == 'pdf': return 'pdf'
        if ext in {'mp4', 'mkv', 'avi', 'mov'}: return 'video'
        if ext in {'jpg', 'jpeg', 'png', 'gif', 'webp'}: return 'image'
        if ext in {'mp3', 'wav', 'ogg'}: return 'audio'
        return ''

    def get_filename_from_url(url):
        if not url: return 'Unknown'
        return str(url).split('/')[-1].split('?')[0]

    return {
        "LOGO_URL":      "/static/assets/THIKATTILOGO.jpg",
        "GOVT_LOGO_URL": "/static/assets/KENYACOATOFARMS.png",
        "current_user": user,
        "department_name": dept_name,
        "unread_notification_count": unread_count,
        "get_alert_classes": get_alert_classes,
        "get_file_icon_class": get_file_icon_class,
        "get_filename_from_url": get_filename_from_url,
        "TAILWIND_CDN": "https://cdn.tailwindcss.com",
        "now": datetime.now,
        "storage_url": storage_url,
        "SUPABASE_URL": supabase_url,
        "BUCKET_SCRIPTS": "assessment-scripts",
        "BUCKET_EVIDENCE": "assessment-evidence",
    }

# ── Jinja2 filter: convert UTC ISO string → EAT display string ───────────────
import pytz
from datetime import datetime as _dt

_EAT = pytz.timezone("Africa/Nairobi")


@app.template_filter("from_json")
def from_json_filter(value):
    """Parse a JSON string into a Python object for use in Jinja2 templates."""
    import json as _json
    if not value:
        return []
    try:
        return _json.loads(value)
    except Exception:
        return []


@app.template_filter("to_eat")
def to_eat_filter(value, fmt="%d %b %Y %H:%M"):
    """Convert a UTC ISO datetime string (from Supabase) to EAT.

    Returns '—' if value is falsy or unparseable.
    """
    if not value:
        return "—"

    try:
        # Handle both 'Z' suffix and '+00:00' offset
        s = str(value).replace("Z", "+00:00")

        # Try with microseconds first, then without
        for fmt_parse in (
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S%z",
        ):
            try:
                utc_dt = _dt.strptime(s, fmt_parse)
                eat_dt = utc_dt.astimezone(_EAT)
                return eat_dt.strftime(fmt)
            except ValueError:
                continue

        return str(value)[:16].replace("T", " ")
    except Exception:
        return str(value)[:16].replace("T", " ")

# ── Error handlers ────────────────────────────────────────────────────────────
@app.errorhandler(400)
def bad_request(e):
    return render_template("errors/400.html"), 400


@app.errorhandler(403)
def forbidden(e):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("errors/404.html"), 404


@app.errorhandler(500)
def server_error(e):
    traceback.print_exc()
    return render_template("errors/500.html", error=str(e)), 500


@app.errorhandler(Exception)
def unhandled_exception(e):
    traceback.print_exc()
    return render_template("errors/500.html", error=str(e)), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)

