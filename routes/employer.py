"""
routes/employer.py — Employer blueprint (Job Portal System).

Employer portal for job postings, applications, and trainee verifications.
"""

from flask import (Blueprint, render_template, request,
                   redirect, url_for, flash, abort)
from auth_utils import (employer_required, write_audit_log, current_user)
from notifications import get_user_notifications
from db import get_service_client
from datetime import datetime

employer_bp = Blueprint("employer", __name__)


def _employer_row() -> dict:
    """Return the employers table row for the current user, or abort 403."""
    user = current_user()
    db = get_service_client()
    try:
        rows = (db.table("employers")
                  .select("*")
                  .eq("profile_id", user["id"])
                  .limit(1)
                  .execute().data or [])
        if not rows:
            abort(403)
        return rows[0]
    except Exception:
        abort(403)


# ── Employer Registration ─────────────────────────────────────────────────────

@employer_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user() and current_user().get("role") == "employer":
        return redirect(url_for("employer.dashboard"))

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        industry = request.form.get("industry", "").strip()

        errors = []
        if not company_name:
            errors.append("Company name is required.")
        if not email:
            errors.append("Official email is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("employer/register.html", form_data=request.form)

        try:
            from auth_utils import create_staff_auth_user
            user_id = create_staff_auth_user(
                email=email,
                password=password,
                full_name=company_name,
                role="employer"
            )
            
            # Create employer record
            db = get_service_client()
            db.table("employers").insert({
                "profile_id": user_id,
                "company_name": company_name,
                "official_email": email,
                "phone": phone or None,
                "location": location or None,
                "industry": industry or None,
            }).execute()
            
            write_audit_log("employer_register", target=f"user:{user_id}")
            flash("Registration submitted! Your account is pending verification by the administrator. "
                  "You will receive login access once approved.", "info")
            return redirect(url_for("auth.login"))
            
        except Exception as e:
            err = str(e)
            if "already registered" in err or "already exists" in err:
                flash("An account with this email already exists.", "danger")
            else:
                flash(f"Registration failed: {err[:120]}", "danger")

    return render_template("employer/register.html", form_data={})


@employer_bp.route("/login")
def login():
    if current_user() and current_user().get("role") == "employer":
        return redirect(url_for("employer.dashboard"))
    return render_template("employer/login.html")


# ── Employer Dashboard ───────────────────────────────────────────────────────

@employer_bp.route("/dashboard")
@employer_required
def dashboard():
    user = current_user()
    db = get_service_client()
    employer = _employer_row()
    employer_id = employer["id"]

    unread_notifications = []
    try:
        # Statistics - Calculated efficiently at DB level
        stats = {}
        stats["total"]    = db.table("employer_verifications").select("id", count="exact").eq("employer_id", employer_id).execute().count or 0
        stats["approved"] = db.table("employer_verifications").select("id", count="exact").eq("employer_id", employer_id).eq("status", "approved").execute().count or 0
        stats["pending"]  = db.table("employer_verifications").select("id", count="exact").eq("employer_id", employer_id).eq("status", "pending").execute().count or 0
        stats["jobs"]     = db.table("job_postings").select("id", count="exact").eq("employer_id", employer_id).execute().count or 0

        # Fetch unread notifications for the profile_id (user_id)
        unread_notifications = get_user_notifications(user["id"], unread_only=True, limit=3)

        # Recent Verifications (limited to 10 for dashboard performance)
        my_verifications = (db.table("employer_verifications")
            .select("*, user_profiles!employer_verifications_trainee_id_fkey(full_name, admission_no), departments(name), courses(name)")
            .eq("employer_id", employer_id)
            .order("submitted_at", desc=True)
            .limit(10).execute().data or [])

        my_jobs = db.table("job_postings").select("*").eq(
            "employer_id", employer_id
        ).order("created_at", desc=True).limit(5).execute().data or []

    except Exception as e:
        flash(f"Error loading dashboard: {e}", "danger")
        my_verifications = []
        stats = {"total": 0, "approved": 0, "pending": 0}
        my_jobs = []

    return render_template("employer/dashboard.html",
                          user=user,
                          employer=employer,
                          verifications=my_verifications,
                          stats=stats,
                          jobs=my_jobs,
                          unread_notifications=unread_notifications)


# ── Job Postings Management ───────────────────────────────────────────────────

@employer_bp.route("/jobs", methods=["GET", "POST"])
@employer_required
def jobs():
    user = current_user()
    db = get_service_client()
    employer = _employer_row()
    employer_id = employer["id"]

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "create":
            title = request.form.get("title", "").strip()
            job_type = request.form.get("type", "job")
            description = request.form.get("description", "").strip()
            requirements = request.form.get("requirements", "").strip()
            skills_raw = request.form.get("skills_required", "")
            skills = [s.strip() for s in skills_raw.split(",") if s.strip()]
            location = request.form.get("location", "").strip()
            salary_range = request.form.get("salary_range", "").strip()
            deadline = request.form.get("deadline", "") or None
            slots = request.form.get("slots", "1")
            dept_pref = request.form.get("department_preference", "").strip()

            if not title or not description:
                flash("Title and description are required.", "danger")
            else:
                try:
                    db.table("job_postings").insert({
                        "employer_id": employer_id,
                        "title": title,
                        "type": job_type,
                        "description": description,
                        "requirements": requirements or None,
                        "skills_required": skills,
                        "department_preference": dept_pref or None,
                        "location": location or None,
                        "salary_range": salary_range or None,
                        "deadline": deadline,
                        "slots": int(slots) if slots.isdigit() else 1,
                        "is_active": True,
                    }).execute()
                    write_audit_log("create_job_posting", target=f"employer:{employer_id}")
                    flash("Job posting published successfully!", "success")
                    return redirect(url_for("employer.jobs"))
                except Exception as e:
                    flash(f"Failed to post job: {str(e)[:100]}", "danger")
        
        elif action == "toggle":
            job_id = request.form.get("job_id")
            try:
                rows = db.table("job_postings").select("is_active, employer_id").eq("id", job_id).execute().data or []
                if not rows or rows[0].get("employer_id") != employer_id:
                    flash("Not found or permission denied.", "danger")
                else:
                    new_state = not rows[0]["is_active"]
                    db.table("job_postings").update({"is_active": new_state}).eq("id", job_id).execute()
                    write_audit_log("toggle_job_posting", target=f"job:{job_id}")
                    flash(f'Posting {"activated" if new_state else "deactivated"}.', "success")
            except Exception:
                flash("Action failed.", "danger")
            return redirect(url_for("employer.jobs"))
        
        elif action == "delete":
            job_id = request.form.get("job_id")
            try:
                rows = db.table("job_postings").select("employer_id").eq("id", job_id).execute().data or []
                if not rows or rows[0].get("employer_id") != employer_id:
                    flash("Not found or permission denied.", "danger")
                else:
                    db.table("job_postings").delete().eq("id", job_id).execute()
                    write_audit_log("delete_job_posting", target=f"job:{job_id}")
                    flash("Posting deleted.", "success")
            except Exception:
                flash("Delete failed.", "danger")
            return redirect(url_for("employer.jobs"))

    my_jobs = db.table("job_postings").select("*").eq(
        "employer_id", employer_id
    ).order("created_at", desc=True).execute().data or []

    departments = db.table("departments").select("id, name").execute().data or []

    return render_template("employer/jobs.html",
                          user=user,
                          employer=employer,
                          jobs=my_jobs,
                          departments=departments)


# ── Job Applications Management ───────────────────────────────────────────────

@employer_bp.route("/applications")
@employer_required
def applications():
    user = current_user()
    db = get_service_client()
    employer = _employer_row()
    employer_id = employer["id"]

    job_filter = request.args.get("job", "")
    status_filter = request.args.get("status", "")

    apps = []
    my_jobs = []

    try:
        my_jobs = db.table("job_postings").select("id, title").eq(
            "employer_id", employer_id
        ).order("created_at", desc=True).execute().data or []

        job_ids = [j["id"] for j in my_jobs]

        if job_ids:
            query = db.table("job_applications").select(
                "*, job_postings(title, type), "
                "user_profiles(full_name, admission_no, mobile_number), "
                "departments(name), courses(name)"
            ).in_("job_id", job_ids)

            if job_filter:
                query = query.eq("job_id", job_filter)
            if status_filter:
                query = query.eq("status", status_filter)

            apps = query.order("applied_at", desc=True).execute().data or []

    except Exception as e:
        flash(f"Error loading applications: {str(e)[:80]}", "danger")

    return render_template("employer/applications.html",
                          user=user,
                          employer=employer,
                          apps=apps,
                          my_jobs=my_jobs,
                          job_filter=job_filter,
                          status_filter=status_filter)


@employer_bp.route("/applications/<app_id>/update", methods=["POST"])
@employer_required
def update_application(app_id):
    user = current_user()
    db = get_service_client()
    employer = _employer_row()
    employer_id = employer["id"]
    new_status = request.form.get("status", "reviewed")

    valid_statuses = ("pending", "reviewed", "shortlisted", "rejected", "accepted")
    if new_status not in valid_statuses:
        flash("Invalid status.", "danger")
        return redirect(url_for("employer.applications"))

    try:
        # Verify the application belongs to this employer's job
        app_rows = db.table("job_applications").select(
            "id, job_id"
        ).eq("id", app_id).execute().data or []

        if not app_rows:
            flash("Application not found.", "danger")
            return redirect(url_for("employer.applications"))

        job_rows = db.table("job_postings").select("employer_id").eq(
            "id", app_rows[0]["job_id"]
        ).execute().data or []

        if not job_rows or job_rows[0].get("employer_id") != employer_id:
            flash("Permission denied.", "danger")
            return redirect(url_for("employer.applications"))

        db.table("job_applications").update({
            "status": new_status,
            "updated_at": datetime.now().isoformat(),
        }).eq("id", app_id).execute()

        write_audit_log("update_application", target=f"application:{app_id}")
        flash(f'Application status updated to "{new_status}".', "success")

    except Exception as e:
        flash(f"Update failed: {str(e)[:80]}", "danger")

    return redirect(request.referrer or url_for("employer.applications"))


# ── Trainee Search & Verification ─────────────────────────────────────────────

@employer_bp.route("/search", methods=["GET", "POST"])
@employer_required
def search():
    user = current_user()
    db = get_service_client()

    results = []
    query_str = ""

    if request.method == "POST" or request.args.get("q"):
        query_str = (request.form.get("query") or request.args.get("q", "")).strip()

        if query_str:
            try:
                all_students = db.table("user_profiles").select(
                    "*, departments(name), courses(name)"
                ).eq("role", "student").execute().data or []

                q = query_str.lower()
                results = [
                    t for t in all_students
                    if q in t.get("full_name", "").lower()
                    or q in t.get("admission_no", "").lower()
                    or q in t.get("email", "").lower()
                ]
            except Exception as e:
                flash(f"Search error: {str(e)[:80]}", "danger")

    return render_template("employer/search.html",
                          user=user,
                          results=results,
                          query=query_str)


@employer_bp.route("/recommend/<student_id>", methods=["GET", "POST"])
@employer_required
def recommend(student_id):
    user = current_user()
    db = get_service_client()
    employer = _employer_row()

    try:
        rows = db.table("user_profiles").select(
            "*, departments(name), courses(name)"
        ).eq("id", student_id).eq("role", "student").execute().data or []
        student = rows[0] if rows else None
    except Exception:
        student = None

    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("employer.search"))

    if request.method == "POST":
        verification_type = request.form.get("verification_type", "employment")
        comments = request.form.get("comments", "").strip()
        status = request.form.get("status", "approved")

        if not comments:
            flash("Please provide a comment or recommendation.", "danger")
            return render_template("employer/recommend.html", user=user, student=student, employer=employer)

        try:
            db.table("employer_verifications").insert({
                "trainee_id": student_id,
                "employer_id": employer["id"],
                "verification_type": verification_type,
                "status": status,
                "review_note": comments,
                "reviewed_at": datetime.now().isoformat() if status == "approved" else None,
            }).execute()

            write_audit_log("submit_verification", target=f"student:{student_id}")
            flash("Recommendation submitted successfully!", "success")
            return redirect(url_for("employer.dashboard"))

        except Exception as e:
            flash(f"Submission failed: {str(e)[:100]}", "danger")

    return render_template("employer/recommend.html", user=user, student=student, employer=employer)


# ── Public Job Board ─────────────────────────────────────────────────────────

@employer_bp.route("/job-board")
def job_board():
    """Public job board — no login required."""
    db = get_service_client()
    user = current_user()

    type_filter = request.args.get("type", "")
    dept_filter = request.args.get("department", "")

    try:
        query = db.table("job_postings").select(
            "*, employers(company_name, location, industry, official_email)"
        ).eq("is_active", True)

        if type_filter:
            query = query.eq("type", type_filter)

        jobs = query.order("created_at", desc=True).execute().data or []

        if dept_filter:
            jobs = [j for j in jobs if (j.get("department_preference") or "") == dept_filter]

        departments = db.table("departments").select("id, name").execute().data or []

        # If logged-in student, fetch their existing applications
        applied_job_ids = set()
        if user and user.get("role") == "student":
            apps = db.table("job_applications").select("job_id").eq(
                "student_id", user["id"]
            ).execute().data or []
            applied_job_ids = {a["job_id"] for a in apps}

    except Exception:
        jobs = []
        departments = []
        applied_job_ids = set()

    return render_template("employer/job_board.html",
                          user=user,
                          jobs=jobs,
                          departments=departments,
                          type_filter=type_filter,
                          dept_filter=dept_filter,
                          applied_job_ids=applied_job_ids)


@employer_bp.route("/job-board/<job_id>/apply", methods=["POST"])
def apply_job(job_id):
    """Student submits an application for a job posting."""
    user = current_user()
    if not user:
        flash("Please log in to apply for jobs.", "warning")
        return redirect(url_for("auth.login"))
    if user.get("role") != "student":
        flash("Only students can apply for jobs.", "warning")
        return redirect(url_for("employer.job_board"))

    db = get_service_client()
    student_id = user["id"]
    cover_note = request.form.get("cover_note", "").strip()

    try:
        # Verify the job exists and is active
        job_rows = db.table("job_postings").select(
            "id, title, is_active, employers(company_name)"
        ).eq("id", job_id).execute().data or []

        if not job_rows:
            flash("Job posting not found.", "danger")
            return redirect(url_for("employer.job_board"))

        job = job_rows[0]
        if not job.get("is_active"):
            flash("This job posting is no longer active.", "warning")
            return redirect(url_for("employer.job_board"))

        # Check for duplicate application
        existing = db.table("job_applications").select("id").eq(
            "job_id", job_id
        ).eq("student_id", student_id).execute().data or []

        if existing:
            flash("You have already applied for this position.", "info")
            return redirect(url_for("employer.job_board"))

        # Insert application
        db.table("job_applications").insert({
            "job_id": job_id,
            "student_id": student_id,
            "cover_note": cover_note or None,
            "status": "pending",
        }).execute()

        emp = job.get("employers") or {}
        flash(
            f'Application submitted for "{job["title"]}" at '
            f'{emp.get("company_name", "the employer")}. Good luck!',
            "success"
        )
        write_audit_log("apply_job", target=f"job:{job_id}")

    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "unique" in err.lower():
            flash("You have already applied for this position.", "info")
        else:
            flash(f"Application failed: {err[:120]}", "danger")

    return redirect(url_for("employer.job_board"))


# ── Industry/Employer Supervisor Dashboard for Log Verification ─────────────

@employer_bp.route("/supervisor")
@employer_required
def supervisor_dashboard():
    """Industry/Employer Supervisor dashboard for trainee log verification."""
    user = current_user()
    db = get_service_client()
    employer = _employer_row()
    employer_id = employer["id"]

    # Get company associated with this employer
    company = None
    try:
        company_rows = db.table("companies").select("*").eq("created_by", user["id"]).execute().data or []
        if company_rows:
            company = company_rows[0]
    except Exception:
        pass

    # Get active attachments for this company
    attachments = []
    if company:
        try:
            attachments = (db.table("industrial_attachments")
                          .select("*, user_profiles(full_name, admission_no), units(name, code), companies(name)")
                          .eq("company_id", company["id"])
                          .in_("status", ["active", "approved"])
                          .order("created_at", desc=True)
                          .execute().data or [])
        except Exception as e:
            flash(f"Error loading attachments: {e}", "danger")

    # Get recent logbook entries for verification
    recent_logs = []
    if company:
        try:
            attachment_ids = [a["id"] for a in attachments]
            if attachment_ids:
                recent_logs = (db.table("digital_logbook")
                             .select("*, user_profiles(full_name, admission_no), units(name, code)")
                             .in_("attachment_id", attachment_ids)
                             .eq("mentor_approval_status", "pending")
                             .order("log_date", desc=True)
                             .limit(20)
                             .execute().data or [])
        except Exception as e:
            flash(f"Error loading logs: {e}", "danger")

    return render_template("employer/supervisor_dashboard.html",
                          user=user,
                          employer=employer,
                          company=company,
                          attachments=attachments,
                          recent_logs=recent_logs)


@employer_bp.route("/supervisor/search-trainee", methods=["GET", "POST"])
@employer_required
def search_trainee():
    """Search trainee by name or admission number for log verification."""
    user = current_user()
    db = get_service_client()
    employer = _employer_row()

    query_str = request.form.get("query", "").strip() if request.method == "POST" else request.args.get("q", "").strip()
    trainee = None
    attachments = []
    logs = []

    if query_str:
        try:
            # Search for trainee
            trainee_rows = db.table("user_profiles").select(
                "*, departments(name), courses(name)"
            ).eq("role", "student").or_(f"full_name.ilike.%{query_str}%,admission_no.ilike.%{query_str}%").execute().data or []

            if trainee_rows:
                trainee = trainee_rows[0]

                # Get attachments for this trainee
                attachments = (db.table("industrial_attachments")
                              .select("*, companies(name, address), units(name, code)")
                              .eq("student_id", trainee["id"])
                              .order("created_at", desc=True)
                              .execute().data or [])

                # Get logbook entries
                if attachments:
                    attachment_ids = [a["id"] for a in attachments]
                    logs = (db.table("digital_logbook")
                           .select("*")
                           .in_("attachment_id", attachment_ids)
                           .order("log_date", desc=True)
                           .execute().data or [])

        except Exception as e:
            flash(f"Search error: {e}", "danger")

    return render_template("employer/supervisor_search.html",
                          user=user,
                          employer=employer,
                          query=query_str,
                          trainee=trainee,
                          attachments=attachments,
                          logs=logs)


@employer_bp.route("/supervisor/logs/<log_id>/approve", methods=["POST"])
@employer_required
def approve_log(log_id):
    """Approve a trainee logbook entry."""
    user = current_user()
    db = get_service_client()
    employer = _employer_row()

    try:
        # Get log entry
        log = db.table("digital_logbook").select("*").eq("id", log_id).single().execute().data

        if not log:
            flash("Log entry not found.", "danger")
            return redirect(url_for("employer.supervisor_dashboard"))

        # Verify the trainee is attached to this employer's company
        attachment = db.table("industrial_attachments").select("*").eq("id", log["attachment_id"]).single().execute().data
        company = db.table("companies").select("*").eq("created_by", user["id"]).execute().data or []

        if not company or (attachment and attachment.get("company_id") != company[0]["id"]):
            flash("Permission denied.", "danger")
            return redirect(url_for("employer.supervisor_dashboard"))

        # Update log approval status
        db.table("digital_logbook").update({
            "mentor_approval_status": "approved",
            "mentor_approved_at": datetime.now().isoformat(),
            "mentor_comments": request.form.get("comments", "")
        }).eq("id", log_id).execute()

        # Send notification to trainee
        from notifications import create_notification
        create_notification(
            user_id=log["student_id"],
            title="Logbook Entry Approved",
            message=f"Your logbook entry for {log['log_date']} has been approved by your supervisor.",
            notification_type="success",
            action_url="/student/logbook"
        )

        write_audit_log("approve_trainee_log", target=f"log:{log_id}")
        flash("Logbook entry approved.", "success")

    except Exception as e:
        flash(f"Error approving log: {e}", "danger")

    return redirect(url_for("employer.supervisor_dashboard"))


@employer_bp.route("/supervisor/logs/<log_id>/reject", methods=["POST"])
@employer_required
def reject_log(log_id):
    """Reject a trainee logbook entry."""
    user = current_user()
    db = get_service_client()
    employer = _employer_row()

    try:
        # Get log entry
        log = db.table("digital_logbook").select("*").eq("id", log_id).single().execute().data

        if not log:
            flash("Log entry not found.", "danger")
            return redirect(url_for("employer.supervisor_dashboard"))

        # Verify the trainee is attached to this employer's company
        attachment = db.table("industrial_attachments").select("*").eq("id", log["attachment_id"]).single().execute().data
        company = db.table("companies").select("*").eq("created_by", user["id"]).execute().data or []

        if not company or (attachment and attachment.get("company_id") != company[0]["id"]):
            flash("Permission denied.", "danger")
            return redirect(url_for("employer.supervisor_dashboard"))

        # Update log approval status
        db.table("digital_logbook").update({
            "mentor_approval_status": "rejected",
            "mentor_approved_at": datetime.now().isoformat(),
            "mentor_comments": request.form.get("comments", "")
        }).eq("id", log_id).execute()

        # Send notification to trainee
        from notifications import create_notification
        create_notification(
            user_id=log["student_id"],
            title="Logbook Entry Rejected",
            message=f"Your logbook entry for {log['log_date']} has been rejected. Please review and resubmit.",
            notification_type="warning",
            action_url="/student/logbook"
        )

        write_audit_log("reject_trainee_log", target=f"log:{log_id}")
        flash("Logbook entry rejected.", "warning")

    except Exception as e:
        flash(f"Error rejecting log: {e}", "danger")

    return redirect(url_for("employer.supervisor_dashboard"))
