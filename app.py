"""
app_unified.py — Unified Flask application entry point.
Combines Attendance Management + E-Portfolio Management
Hosted on Render. Database + Auth via Supabase.
"""

import os
import traceback
from datetime import timedelta
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
from routes.employer import employer_bp
from routes.examination_officer import examination_officer_bp
from routes.industry_mentor import industry_mentor_bp
from routes.internal_verifier import internal_verifier_bp
from routes.clearance import clearance_bp
from routes.admission import admission_bp
from routes.admin_oversight import admin_oversight_bp
from routes.notifications import notifications_bp
from routes.main import main_bp

app.register_blueprint(main_bp)
app.register_blueprint(auth_bp, url_prefix="/auth")
app.register_blueprint(super_admin_bp, url_prefix="/super-admin")
app.register_blueprint(dept_admin_bp, url_prefix="/dept-admin")
app.register_blueprint(trainer_bp, url_prefix="/trainer")
app.register_blueprint(student_bp, url_prefix="/student")
app.register_blueprint(employer_bp, url_prefix="/employer")
app.register_blueprint(examination_officer_bp, url_prefix="/examination-officer")
app.register_blueprint(industry_mentor_bp, url_prefix="/industry-mentor")
app.register_blueprint(internal_verifier_bp, url_prefix="/internal-verifier")
app.register_blueprint(clearance_bp, url_prefix="/clearance")
app.register_blueprint(admission_bp, url_prefix="/admission")
app.register_blueprint(admin_oversight_bp, url_prefix="/admin-oversight")
app.register_blueprint(notifications_bp, url_prefix="/notifications")

# ── Template globals ──────────────────────────────────────────────────────────
@app.context_processor
def inject_globals():
    return {
        "current_user": session.get("user"),
        "LOGO_URL": os.getenv("LOGO_URL", "/static/images/logo.png"),
        "APP_NAME": os.getenv("APP_NAME", "TTTI Academic Management"),
        "format_datetime": format_datetime,
        "format_currency": format_currency,
        "now": datetime.now,
        "unread_count": get_user_unread_notifications(
            session.get("user", {}).get("id")
        ) if session.get("user") else 0
    }
        return mapping.get(ntype, mapping['info'])

    return {
        "LOGO_URL": "/static/assets/THIKATTILOGO.jpg",
        "current_user": user,
        "department_name": dept_name,
        "unread_notification_count": unread_count,
        "pending_employers_count": pending_employers,
        "get_alert_classes": get_alert_classes,
        "TAILWIND_CDN": "https://cdn.tailwindcss.com"
    }

# ── Jinja2 filter: convert UTC ISO string → EAT display string ───────────────
import pytz
from datetime import datetime as _dt

_EAT = pytz.timezone('Africa/Nairobi')

@app.template_filter('to_eat')
def to_eat_filter(value, fmt='%d %b %Y %H:%M'):
    """
    Convert a UTC ISO datetime string (from Supabase) to EAT (Africa/Nairobi).
    Usage in templates:  {{ r.attendance_date | to_eat }}
                         {{ r.created_at | to_eat('%d %b %Y') }}
    Returns '—' if value is falsy or unparseable.
    """
    if not value:
        return '—'
    try:
        # Handle both 'Z' suffix and '+00:00' offset
        s = str(value).replace('Z', '+00:00')
        # Try with microseconds first, then without
        for fmt_parse in ('%Y-%m-%dT%H:%M:%S.%f%z', '%Y-%m-%dT%H:%M:%S%z',
                          '%Y-%m-%d %H:%M:%S.%f%z', '%Y-%m-%d %H:%M:%S%z'):
            try:
                utc_dt = _dt.strptime(s, fmt_parse)
                eat_dt = utc_dt.astimezone(_EAT)
                return eat_dt.strftime(fmt)
            except ValueError:
                continue
        # Fallback: treat as naive local, just slice
        return str(value)[:16].replace('T', ' ')
    except Exception:
        return str(value)[:16].replace('T', ' ')

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
    # Print full traceback to Render logs
    traceback.print_exc()
    return render_template("errors/500.html", error=str(e)), 500

@app.errorhandler(Exception)
def unhandled_exception(e):
    traceback.print_exc()
    return render_template("errors/500.html", error=str(e)), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
