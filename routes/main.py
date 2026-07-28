"""
routes/main.py — Public landing page & course applications.
"""

from flask import Blueprint, render_template, redirect, url_for, request, flash
from auth_utils import current_user, is_authenticated, role_home_url
from db import get_service_client
import os, uuid

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    # If already logged in, redirect to the correct dashboard
    if is_authenticated():
        return redirect(role_home_url(current_user().get("role")))
    return redirect(url_for("auth.login"))


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
