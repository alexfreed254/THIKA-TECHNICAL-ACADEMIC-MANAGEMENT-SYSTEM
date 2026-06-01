"""
Clearance Blueprint for TVET Online Trainee Clearance System
Manages multi-layer institutional clearance with department, institutional, and central authority workflows
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from datetime import datetime
from auth_utils import login_required, student_required, current_user, write_audit_log
from db import get_service_client
from notifications import create_notification

clearance_bp = Blueprint('clearance', __name__)


# ── Student Clearance Dashboard ─────────────────────────────────────────────

@clearance_bp.route("/")
@login_required
@student_required
def dashboard():
    """Student clearance dashboard showing clearance status."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get student's active clearance request
    clearance_request = (db.table("clearance_requests")
                       .select("*, courses(name, code), departments(name)")
                       .eq("student_id", student_id)
                       .order("initiated_at", desc=True)
                       .limit(1)
                       .execute().data)
    
    # Get student's enrollments via classes → courses (no direct FK to courses)
    enrollments = (db.table("enrollments")
                  .select("*, classes(course_id, courses(name, code))")
                  .eq("student_id", student_id)
                  .execute().data or [])

    if not clearance_request:
        return render_template("clearance/student_dashboard.html", 
                              clearance_request=None,
                              has_request=False,
                              enrollments=enrollments)
    
    clearance_request = clearance_request[0]
    
    # Get all approvals for this request
    approvals = (db.table("clearance_approvals")
                .select("*, clearance_stages(stage_name, approver_role, clearance_departments(name, clearance_type)), user_profiles(full_name)")
                .eq("clearance_request_id", clearance_request["id"])
                .order("created_at")
                .execute().data or [])
    
    # Flatten the clearance_departments nested relationship in Python
    for a in approvals:
        stage = a.get("clearance_stages") or {}
        a["clearance_departments"] = stage.get("clearance_departments") or {}
    
    # Group approvals by department type
    department_approvals = [a for a in approvals if a.get("clearance_departments", {}).get("clearance_type") == "department"]
    institutional_approvals = [a for a in approvals if a.get("clearance_departments", {}).get("clearance_type") == "institutional"]
    central_approvals = [a for a in approvals if a.get("clearance_departments", {}).get("clearance_type") == "central"]
    
    return render_template("clearance/student_dashboard.html",
                          clearance_request=clearance_request,
                          has_request=True,
                          department_approvals=department_approvals,
                          institutional_approvals=institutional_approvals,
                          central_approvals=central_approvals,
                          enrollments=enrollments)


@clearance_bp.route("/initiate", methods=["POST"])
@login_required
@student_required
def initiate_clearance():
    """Initiate clearance request for course completion."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    course_id = request.form.get("course_id")
    
    if not course_id:
        flash("Course is required.", "error")
        return redirect(url_for("clearance.dashboard"))
    
    try:
        # Get course and department info
        course = (db.table("courses")
                 .select("*, departments(id, name)")
                 .eq("id", course_id)
                 .single()
                 .execute().data)
        
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("clearance.dashboard"))
        
        # Check if student has active clearance request
        existing = (db.table("clearance_requests")
                   .select("*")
                   .eq("student_id", student_id)
                   .in_("status", ["pending", "in_progress"])
                   .execute().data)
        
        if existing:
            flash("You already have an active clearance request.", "warning")
            return redirect(url_for("clearance.dashboard"))
        
        # Create clearance request
        request_id = db.table("clearance_requests").insert({
            "student_id": student_id,
            "course_id": course_id,
            "department_id": course["departments"]["id"],
            "status": "in_progress",
            "created_by": user["id"]
        }).execute().data[0]["id"]
        
        # Get all clearance stages and create approval records
        stages = (db.table("clearance_stages")
                 .select("*")
                 .execute().data or [])
        
        for stage in stages:
            db.table("clearance_approvals").insert({
                "clearance_request_id": request_id,
                "clearance_stage_id": stage["id"],
                "status": "pending"
            }).execute()
        
        write_audit_log("initiate_clearance", target=f"request:{request_id}")
        flash("Clearance request initiated successfully.", "success")
    except Exception as e:
        flash(f"Error initiating clearance: {e}", "error")
    
    return redirect(url_for("clearance.dashboard"))


# ── Approver Dashboard ─────────────────────────────────────────────────────

@clearance_bp.route("/approver")
@login_required
def approver_dashboard():
    """Approver dashboard — for trainers, filters to taught trainees only."""
    db = get_service_client()
    user = current_user()
    user_role = user["role"]

    # Fetch all pending approvals with student and stage info
    pending_approvals = (
        db.table("clearance_approvals")
          .select(
              "*, "
              "clearance_requests(id, student_id, "
              "  user_profiles:user_profiles!clearance_requests_student_id_fkey"
              "  (full_name, admission_no)), "
              "clearance_stages(stage_name, approver_role, "
              "  clearance_departments(name))"
          )
          .eq("status", "pending")
          .execute().data or []
    )

    # Flatten nested relations for template use
    for a in pending_approvals:
        req   = a.get("clearance_requests") or {}
        stage = a.get("clearance_stages")   or {}
        a["user_profiles"]        = req.get("user_profiles") or {}
        a["clearance_departments"] = stage.get("clearance_departments") or {}

    # Keep only approvals whose stage targets this user's role.
    # For trainers: also exclude any stage whose name contains "technician"
    # (those belong exclusively to the Workshop Technician dashboard).
    TECHNICIAN_KEYWORDS = ("technician", "workshop technician", "workshop")

    def is_trainer_stage(approval):
        stage = approval.get("clearance_stages") or {}
        if stage.get("approver_role") != user_role:
            return False
        if user_role == "trainer":
            stage_name = (stage.get("stage_name") or "").lower()
            if any(kw in stage_name for kw in TECHNICIAN_KEYWORDS):
                return False
        return True

    my_approvals = [a for a in pending_approvals if is_trainer_stage(a)]

    # ── Trainer-specific filtering ──────────────────────────────────────────
    # A trainer should only see clearance requests from trainees they have
    # actually taught — verified through the attendance table.
    trainer_trainee_units = {}   # {student_id: [{"name":..,"code":..}, ...]}
    stats = {}                   # extra context for the trainer template

    if user_role == "trainer":
        # All attendance rows where this trainer delivered the session
        att_rows = (
            db.table("attendance")
              .select("student_id, unit_id, units(name, code)")
              .eq("trainer_id", user["id"])
              .execute().data or []
        )

        # Build: student_id → deduplicated list of taught units
        seen = {}   # student_id → {unit_id}
        for r in att_rows:
            sid = r["student_id"]
            uid = r["unit_id"]
            u   = r.get("units") or {}
            if sid not in seen:
                seen[sid] = set()
                trainer_trainee_units[sid] = []
            if uid not in seen[sid]:
                seen[sid].add(uid)
                if u.get("code"):
                    trainer_trainee_units[sid].append(u)

        taught_student_ids = set(trainer_trainee_units.keys())

        # Filter to only trainees this trainer has taught
        my_approvals = [
            a for a in my_approvals
            if (a.get("clearance_requests") or {}).get("student_id")
               in taught_student_ids
        ]

        # Attach the list of taught units to each approval for display
        for a in my_approvals:
            sid = (a.get("clearance_requests") or {}).get("student_id", "")
            a["taught_units"] = trainer_trainee_units.get(sid, [])

        stats = {
            "total":   len(my_approvals),
            "taught":  len(taught_student_ids),
        }

        return render_template(
            "trainer/clearance_approvals.html",
            my_approvals=my_approvals,
            stats=stats,
        )
    # ── End trainer branch ──────────────────────────────────────────────────

    return render_template("clearance/approver_dashboard.html",
                           my_approvals=my_approvals,
                           user_role=user_role)


@clearance_bp.route("/approve/<approval_id>", methods=["POST"])
@login_required
def approve_clearance(approval_id):
    """Approve a clearance stage."""
    db = get_service_client()
    user = current_user()
    user_role = user["role"]
    
    comments = request.form.get("comments", "")
    
    try:
        # Get approval record
        approval = (db.table("clearance_approvals")
                   .select("*, clearance_stages(approver_role), clearance_requests(id, status)")
                   .eq("id", approval_id)
                   .single()
                   .execute().data)
        
        if not approval:
            flash("Approval record not found.", "error")
            return redirect(url_for("clearance.approver_dashboard"))
        
        # Verify approver role matches
        if approval.get("clearance_stages", {}).get("approver_role") != user_role:
            abort(403)
        
        # Update approval
        db.table("clearance_approvals").update({
            "status": "approved",
            "approver_id": user["id"],
            "comments": comments,
            "approved_at": datetime.now().isoformat()
        }).eq("id", approval_id).execute()
        
        # Check if all approvals are complete for this request
        check_clearance_completion(approval["clearance_requests"]["id"])
        
        # Send notification to student
        student_id = approval.get("clearance_requests", {}).get("student_id")
        if student_id:
            stage_name = approval.get("clearance_stages", {}).get("stage_name", "Clearance Stage")
            create_notification(
                user_id=student_id,
                title=f"Clearance Approved: {stage_name}",
                message=f"Your clearance stage '{stage_name}' has been approved. Continue to the next stage.",
                notification_type="success",
                action_url="/clearance"
            )
        
        write_audit_log("approve_clearance", target=f"approval:{approval_id}")
        flash("Clearance approved successfully.", "success")
    except Exception as e:
        flash(f"Error approving clearance: {e}", "error")
    
    return redirect(url_for("clearance.approver_dashboard"))


@clearance_bp.route("/reject/<approval_id>", methods=["POST"])
@login_required
def reject_clearance(approval_id):
    """Reject a clearance stage."""
    db = get_service_client()
    user = current_user()
    user_role = user["role"]
    
    comments = request.form.get("comments", "")
    
    if not comments:
        flash("Comments are required for rejection.", "error")
        return redirect(url_for("clearance.approver_dashboard"))
    
    try:
        # Get approval record
        approval = (db.table("clearance_approvals")
                   .select("*, clearance_stages(approver_role), clearance_requests(id)")
                   .eq("id", approval_id)
                   .single()
                   .execute().data)
        
        if not approval:
            flash("Approval record not found.", "error")
            return redirect(url_for("clearance.approver_dashboard"))
        
        # Verify approver role matches
        if approval.get("clearance_stages", {}).get("approver_role") != user_role:
            abort(403)
        
        # Update approval
        db.table("clearance_approvals").update({
            "status": "rejected",
            "approver_id": user["id"],
            "comments": comments,
            "approved_at": datetime.now().isoformat()
        }).eq("id", approval_id).execute()
        
        # Mark request as rejected
        db.table("clearance_requests").update({
            "status": "rejected"
        }).eq("id", approval["clearance_requests"]["id"]).execute()
        
        # Send notification to student
        student_id = approval.get("clearance_requests", {}).get("student_id")
        if student_id:
            stage_name = approval.get("clearance_stages", {}).get("stage_name", "Clearance Stage")
            create_notification(
                user_id=student_id,
                title=f"Clearance Rejected: {stage_name}",
                message=f"Your clearance stage '{stage_name}' has been rejected. Comments: {comments}",
                notification_type="warning",
                action_url="/clearance"
            )
        
        write_audit_log("reject_clearance", target=f"approval:{approval_id}")
        flash("Clearance rejected.", "warning")
    except Exception as e:
        flash(f"Error rejecting clearance: {e}", "error")
    
    return redirect(url_for("clearance.approver_dashboard"))


@clearance_bp.route("/clearance-form/<request_id>")
@login_required
@student_required
def clearance_form(request_id):
    """Generate printable Student Clearance Form (TTTI/ADM/CLEAR/F1)."""
    db = get_service_client()
    user = current_user()

    clearance_request_res = (db.table("clearance_requests")
                             .select("*, courses(name, code), departments(name)")
                             .eq("id", request_id)
                             .limit(1)
                             .execute().data)
    if not clearance_request_res:
        flash("Clearance request not found.", "error")
        return redirect(url_for("clearance.dashboard"))

    clearance_request = clearance_request_res[0]

    # Students can only view their own
    if user["role"] == "student" and clearance_request["student_id"] != user["id"]:
        from flask import abort
        abort(403)

    student = db.table("user_profiles").select("*").eq("id", clearance_request["student_id"]).single().execute().data or {}

    return render_template("clearance/clearance_form_pdf.html",
                           clearance_request=clearance_request,
                           student=student)


def check_clearance_completion(request_id):
    """Check if all approvals are complete and update request status."""
    db = get_service_client()
    
    # Get all approvals for this request
    approvals = (db.table("clearance_approvals")
                .select("*, clearance_requests(student_id)")
                .eq("clearance_request_id", request_id)
                .execute().data or [])
    
    # Check if all are approved
    all_approved = all(a["status"] == "approved" for a in approvals)
    any_rejected = any(a["status"] == "rejected" for a in approvals)
    
    if any_rejected:
        db.table("clearance_requests").update({
            "status": "rejected"
        }).eq("id", request_id).execute()
    elif all_approved:
        db.table("clearance_requests").update({
            "status": "completed",
            "completed_at": datetime.now().isoformat()
        }).eq("id", request_id).execute()
        
        # Send notification to student that clearance is complete
        if approvals and approvals[0].get("clearance_requests", {}).get("student_id"):
            student_id = approvals[0]["clearance_requests"]["student_id"]
            create_notification(
                user_id=student_id,
                title="Clearance Completed!",
                message="Congratulations! Your course clearance is complete. You can now collect your certificate.",
                notification_type="success",
                action_url="/clearance"
            )


# ── Certificate Issuance ─────────────────────────────────────────────────────

@clearance_bp.route("/issue-certificate/<request_id>", methods=["POST"])
@login_required
def issue_certificate(request_id):
    """Issue certificate for completed clearance."""
    db = get_service_client()
    user = current_user()
    
    try:
        # Verify request is completed
        request_data = (db.table("clearance_requests")
                       .select("*")
                       .eq("id", request_id)
                       .eq("status", "completed")
                       .single()
                       .execute().data)
        
        if not request_data:
            flash("Clearance request not completed.", "error")
            return redirect(url_for("clearance.dashboard"))
        
        # Update certificate issuance
        db.table("clearance_requests").update({
            "certificate_issued": True,
            "certificate_issued_at": datetime.now().isoformat()
        }).eq("id", request_id).execute()
        
        # Send notification to student that certificate is issued
        create_notification(
            user_id=request_data["student_id"],
            title="Certificate Issued!",
            message="Your certificate has been issued and is ready for collection.",
            notification_type="success",
            action_url="/clearance"
        )
        
        write_audit_log("issue_certificate", target=f"request:{request_id}")
        flash("Certificate issued successfully.", "success")
    except Exception as e:
        flash(f"Error issuing certificate: {e}", "error")
    
    return redirect(url_for("clearance.dashboard"))
