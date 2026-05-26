"""
routes/main.py — Public landing page.
"""

from flask import Blueprint, render_template, redirect, url_for
from auth_utils import current_user, is_authenticated

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    # If already logged in, redirect to the correct dashboard
    if is_authenticated():
        user = current_user()
        role = user.get("role", "")
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
        elif role in ("sports_hod", "environment_hod", "dean_students", "library_hod", "finance_officer"):
            return redirect(url_for("clearance.approver_dashboard"))
    return render_template("main/index.html")
