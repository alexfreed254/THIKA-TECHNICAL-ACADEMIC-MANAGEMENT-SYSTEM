"""
routes/main.py — Public landing page & course applications.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from auth_utils import current_user, is_authenticated
from db import get_service_client
import os, uuid

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


@main_bp.route("/apply", methods=["GET", "POST"])
def apply_course():
    db = get_service_client()
    departments = db.table("departments").select("*").order("name").execute().data or []

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        department_id = request.form.get("department_id", "").strip()
        course_name = request.form.get("course_name", "").strip()

        errors = []
        if not full_name: errors.append("Full name is required.")
        if not email: errors.append("Email is required.")
        if not department_id: errors.append("Department is required.")
        if not course_name: errors.append("Course name is required.")

        document_paths = []
        if errors:
            for e in errors:
                flash(e, "error")
            return redirect("/auth/login?apply=1")

        # Handle file uploads
        uploaded_files = request.files.getlist("documents")
        svc = get_service_client()
        for f in uploaded_files:
            if f and f.filename:
                ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
                unique_name = f"{uuid.uuid4()}.{ext}" if ext else uuid.uuid4().hex
                storage_path = f"course_applications/{unique_name}"
                file_bytes = f.read()
                if len(file_bytes) > 5 * 1024 * 1024:
                    flash(f"File {f.filename} exceeds 5MB limit.", "error")
                    return redirect("/auth/login?apply=1")
                try:
                    svc.storage.from_("application-documents").upload(
                        path=storage_path,
                        file=file_bytes,
                        file_options={"content-type": f.content_type or "application/octet-stream"}
                    )
                    public_url = f"{os.environ.get('SUPABASE_URL', '').strip()}/storage/v1/object/public/application-documents/{storage_path}"
                    document_paths.append(public_url)
                except Exception as e:
                    flash(f"Error uploading {f.filename}: {e}", "error")
                    return redirect("/auth/login?apply=1")

        try:
            db.table("course_applications").insert({
                "full_name": full_name,
                "email": email,
                "phone": phone,
                "department_id": department_id,
                "course_name": course_name,
                "document_paths": document_paths,
            }).execute()
            flash("Your application has been submitted successfully. You will be contacted soon.", "success")
            return redirect("/auth/login?apply=1")
        except Exception as e:
            flash(f"Error submitting application: {e}", "error")

    return render_template("main/apply.html", departments=departments)
