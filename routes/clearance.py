"""
Clearance Blueprint for TVET Online Trainee Clearance System
Manages multi-layer institutional clearance with department, institutional, and central authority workflows
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort
from datetime import datetime
from auth_utils import login_required, student_required, current_user, write_audit_log
from db import get_service_client
from notifications import create_notification

clearance_bp = Blueprint('clearance', __name__, url_prefix='/clearance')


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
    
    if not clearance_request:
        return render_template("clearance/student_dashboard.html", 
                              clearance_request=None,
                              has_request=False)
    
    clearance_request = clearance_request[0]
    
    # Get all approvals for this request
    approvals = (db.table("clearance_approvals")
                .select("*, clearance_stages(stage_name, approver_role), clearance_departments(name, clearance_type), user_profiles(full_name)")
                .eq("clearance_request_id", clearance_request["id"])
                .order("created_at")
                .execute().data or [])
    
    # Group approvals by department type
    department_approvals = [a for a in approvals if a.get("clearance_departments", {}).get("clearance_type") == "department"]
    institutional_approvals = [a for a in approvals if a.get("clearance_departments", {}).get("clearance_type") == "institutional"]
    central_approvals = [a for a in approvals if a.get("clearance_departments", {}).get("clearance_type") == "central"]
    
    return render_template("clearance/student_dashboard.html",
                          clearance_request=clearance_request,
                          has_request=True,
                          department_approvals=department_approvals,
                          institutional_approvals=institutional_approvals,
                          central_approvals=central_approvals)


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
    """Approver dashboard showing pending approvals."""
    db = get_service_client()
    user = current_user()
    user_role = user["role"]
    
    # Get pending approvals for this approver's role
    pending_approvals = (db.table("clearance_approvals")
                        .select("*, clearance_requests(student_id), clearance_stages(stage_name, approver_role), clearance_departments(name), user_profiles(full_name, admission_no)")
                        .eq("status", "pending")
                        .execute().data or [])
    
    # Filter by approver role
    my_approvals = [a for a in pending_approvals if a.get("clearance_stages", {}).get("approver_role") == user_role]
    
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
                recipient_id=student_id,
                title=f"Clearance Approved: {stage_name}",
                message=f"Your clearance stage '{stage_name}' has been approved. Continue to the next stage.",
                notification_type="clearance",
                metadata={"clearance_request_id": approval["clearance_requests"]["id"]}
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
                recipient_id=student_id,
                title=f"Clearance Rejected: {stage_name}",
                message=f"Your clearance stage '{stage_name}' has been rejected. Comments: {comments}",
                notification_type="clearance",
                metadata={"clearance_request_id": approval["clearance_requests"]["id"]}
            )
        
        write_audit_log("reject_clearance", target=f"approval:{approval_id}")
        flash("Clearance rejected.", "warning")
    except Exception as e:
        flash(f"Error rejecting clearance: {e}", "error")
    
    return redirect(url_for("clearance.approver_dashboard"))


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
                recipient_id=student_id,
                title="Clearance Completed!",
                message="Congratulations! Your course clearance is complete. You can now collect your certificate.",
                notification_type="clearance",
                metadata={"clearance_request_id": request_id}
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
            recipient_id=request_data["student_id"],
            title="Certificate Issued!",
            message="Your certificate has been issued and is ready for collection.",
            notification_type="clearance",
            metadata={"clearance_request_id": request_id}
        )
        
        write_audit_log("issue_certificate", target=f"request:{request_id}")
        flash("Certificate issued successfully.", "success")
    except Exception as e:
        flash(f"Error issuing certificate: {e}", "error")
    
    return redirect(url_for("clearance.dashboard"))
