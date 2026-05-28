"""
Admission Blueprint for Trainee Admission Document Management
Manages document upload, HOD review, and departmental admission approval form generation
"""

from flask import Blueprint, render_template, request, flash, redirect, url_for, abort, send_file
from datetime import datetime
from auth_utils import login_required, student_required, dept_admin_required, current_user, write_audit_log
from db import get_service_client
import os
import uuid
from werkzeug.utils import secure_filename

admission_bp = Blueprint('admission', __name__)

# Required document types for admission
REQUIRED_DOCUMENTS = [
    'birth_certificate',
    'national_id',
    'kcse_certificate',
    'academic_transcripts',
    'medical_report',
    'passport_photo',
    'recommendation_letter',
    'fee_payment_receipt'
]

# ── Student Admission Document Upload ─────────────────────────────────────

@admission_bp.route("/")
@login_required
@student_required
def dashboard():
    """Student admission dashboard showing document upload status."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Get student's admission request
    admission_request = (db.table("admission_requests")
                       .select("*, courses(name, code), departments(name)")
                       .eq("student_id", student_id)
                       .order("submitted_at", desc=True)
                       .limit(1)
                       .execute().data or [])
    
    # Get student's enrollments for the course selector
    enrollments = (db.table("enrollments")
                  .select("*, courses(name, code)")
                  .eq("student_id", student_id)
                  .execute().data or [])

    if not admission_request:
        return render_template("admission/student_dashboard.html",
                              admission_request=None,
                              has_request=False,
                              required_documents=REQUIRED_DOCUMENTS,
                              enrollments=enrollments)
    
    admission_request = admission_request[0]
    
    # Get uploaded documents for this request
    documents = (db.table("admission_documents")
                .select("*")
                .eq("admission_request_id", admission_request["id"])
                .execute().data or [])
    
    # Check which required documents are uploaded
    uploaded_types = {doc["document_type"] for doc in documents}
    missing_documents = [doc_type for doc_type in REQUIRED_DOCUMENTS if doc_type not in uploaded_types]
    
    # Check if all documents are uploaded
    all_uploaded = len(missing_documents) == 0
    
    return render_template("admission/student_dashboard.html",
                          admission_request=admission_request,
                          has_request=True,
                          documents=documents,
                          required_documents=REQUIRED_DOCUMENTS,
                          uploaded_types=uploaded_types,
                          missing_documents=missing_documents,
                          all_uploaded=all_uploaded,
                          enrollments=enrollments)


@admission_bp.route("/initiate", methods=["POST"])
@login_required
@student_required
def initiate_admission():
    """Initiate admission request for a course."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    course_id = request.form.get("course_id")
    
    if not course_id:
        flash("Course is required.", "error")
        return redirect(url_for("admission.dashboard"))
    
    try:
        # Get course and department info
        course = (db.table("courses")
                 .select("*, departments(id, name)")
                 .eq("id", course_id)
                 .single()
                 .execute().data)
        
        if not course:
            flash("Course not found.", "error")
            return redirect(url_for("admission.dashboard"))
        
        # Check if student has active admission request
        existing = (db.table("admission_requests")
                   .select("*")
                   .eq("student_id", student_id)
                   .in_("status", ["pending"])
                   .execute().data)
        
        if existing:
            flash("You already have an active admission request.", "warning")
            return redirect(url_for("admission.dashboard"))
        
        # Create admission request
        db.table("admission_requests").insert({
            "student_id": student_id,
            "course_id": course_id,
            "department_id": course["departments"]["id"],
            "status": "pending"
        }).execute()
        
        write_audit_log("initiate_admission", target=f"course:{course_id}")
        flash("Admission request initiated. Please upload the required documents.", "success")
    except Exception as e:
        flash(f"Error initiating admission: {e}", "error")
    
    return redirect(url_for("admission.dashboard"))


@admission_bp.route("/upload/<request_id>", methods=["POST"])
@login_required
@student_required
def upload_document(request_id):
    """Upload admission document."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Verify request belongs to student
    admission_request = (db.table("admission_requests")
                       .select("*")
                       .eq("id", request_id)
                       .eq("student_id", student_id)
                       .single()
                       .execute().data)
    
    if not admission_request:
        flash("Admission request not found.", "error")
        return redirect(url_for("admission.dashboard"))
    
    if 'document' not in request.files:
        flash("No file selected.", "error")
        return redirect(url_for("admission.dashboard"))
    
    file = request.files['document']
    document_type = request.form.get("document_type")
    
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(url_for("admission.dashboard"))
    
    if document_type not in REQUIRED_DOCUMENTS:
        flash("Invalid document type.", "error")
        return redirect(url_for("admission.dashboard"))
    
    try:
        # Secure filename and save
        filename = secure_filename(file.filename)
        unique_filename = f"{uuid.uuid4()}_{filename}"
        
        # Create upload directory if it doesn't exist
        upload_dir = os.path.join("static", "uploads", "admission")
        os.makedirs(upload_dir, exist_ok=True)
        
        file_path = os.path.join(upload_dir, unique_filename)
        file.save(file_path)
        
        # Get file size
        file_size = os.path.getsize(file_path)
        
        # Save document record
        db.table("admission_documents").insert({
            "admission_request_id": request_id,
            "document_type": document_type,
            "file_path": file_path,
            "file_name": filename,
            "file_size": file_size
        }).execute()
        
        write_audit_log("upload_admission_document", target=f"request:{request_id}")
        flash(f"{document_type.replace('_', ' ').title()} uploaded successfully.", "success")
    except Exception as e:
        flash(f"Error uploading document: {e}", "error")
    
    return redirect(url_for("admission.dashboard"))


@admission_bp.route("/submit/<request_id>", methods=["POST"])
@login_required
@student_required
def submit_admission(request_id):
    """Submit admission request for HOD review."""
    db = get_service_client()
    user = current_user()
    student_id = user["id"]
    
    # Verify request belongs to student
    admission_request = (db.table("admission_requests")
                       .select("*")
                       .eq("id", request_id)
                       .eq("student_id", student_id)
                       .single()
                       .execute().data)
    
    if not admission_request:
        flash("Admission request not found.", "error")
        return redirect(url_for("admission.dashboard"))
    
    # Check if all required documents are uploaded
    documents = (db.table("admission_documents")
                .select("*")
                .eq("admission_request_id", request_id)
                .execute().data or [])
    
    uploaded_types = {doc["document_type"] for doc in documents}
    missing_documents = [doc_type for doc_type in REQUIRED_DOCUMENTS if doc_type not in uploaded_types]
    
    if missing_documents:
        flash(f"Please upload all required documents: {', '.join(missing_documents)}", "error")
        return redirect(url_for("admission.dashboard"))
    
    try:
        # Update request status to submitted
        db.table("admission_requests").update({
            "status": "pending",
            "submitted_at": datetime.now().isoformat()
        }).eq("id", request_id).execute()
        
        # Send notification to HOD
        from notifications import create_notification
        hod_users = (db.table("user_profiles")
                    .select("id")
                    .eq("role", "dept_admin")
                    .eq("department_id", admission_request["department_id"])
                    .execute().data or [])
        
        for hod in hod_users:
            create_notification(
                user_id=hod["id"],
                title="New Admission Request",
                message="A new admission request has been submitted for review.",
                notification_type="info",
                action_url="/admission/hod"
            )
        
        write_audit_log("submit_admission", target=f"request:{request_id}")
        flash("Admission request submitted for HOD review.", "success")
    except Exception as e:
        flash(f"Error submitting admission: {e}", "error")
    
    return redirect(url_for("admission.dashboard"))


# ── HOD Admission Review ─────────────────────────────────────────────────────

@admission_bp.route("/hod")
@login_required
@dept_admin_required
def hod_dashboard():
    """HOD dashboard showing pending, approved, and rejected admission requests."""
    db = get_service_client()
    user = current_user()
    department_id = user.get("department_id")
    
    status_filter = request.args.get("status", "pending")
    if status_filter not in ("pending", "approved", "rejected", "all"):
        status_filter = "pending"
    
    # Get admission requests for HOD's department
    query = (db.table("admission_requests")
                       .select("*, courses(name, code), departments(name), student:user_profiles!admission_requests_student_id_fkey(full_name, admission_no, email), reviewer:user_profiles!admission_requests_reviewed_by_fkey(full_name)")
                       .eq("department_id", department_id))
    
    if status_filter != "all":
        query = query.eq("status", status_filter)
        
    requests = query.order("submitted_at", desc=True).execute().data or []
    
    # Get documents for each request
    for req in requests:
        req["documents"] = (db.table("admission_documents")
                          .select("*")
                          .eq("admission_request_id", req["id"])
                          .execute().data or [])
    
    return render_template("admission/hod_dashboard.html",
                           requests=requests, status_filter=status_filter)


@admission_bp.route("/hod/review/<request_id>")
@login_required
@dept_admin_required
def review_request(request_id):
    """HOD review page for admission request."""
    db = get_service_client()
    user = current_user()
    department_id = user.get("department_id")
    
    # Get admission request
    admission_request_res = (db.table("admission_requests")
                       .select("*, courses(name, code), departments(name), user_profiles:user_profiles!admission_requests_student_id_fkey(full_name, admission_no, email, mobile_number)")
                       .eq("id", request_id)
                       .eq("department_id", department_id)
                       .limit(1)
                       .execute().data)
    
    if not admission_request_res:
        flash("Admission request not found.", "error")
        return redirect(url_for("admission.hod_dashboard"))
        
    admission_request = admission_request_res[0]
    user_prof = admission_request.get("user_profiles") or {}
    user_prof["phone"] = user_prof.get("mobile_number") or "N/A"
    
    # Get documents for this request
    documents = (db.table("admission_documents")
                .select("*")
                .eq("admission_request_id", request_id)
                .execute().data or [])
    
    return render_template("admission/hod_review.html",
                          admission_request=admission_request,
                          documents=documents,
                          required_documents=REQUIRED_DOCUMENTS)


@admission_bp.route("/hod/verify-document/<document_id>", methods=["POST"])
@login_required
@dept_admin_required
def verify_document(document_id):
    """Verify an admission document."""
    db = get_service_client()
    user = current_user()
    
    try:
        # Get document
        document = (db.table("admission_documents")
                   .select("*, admission_requests(department_id)")
                   .eq("id", document_id)
                   .single()
                   .execute().data)
        
        if not document:
            flash("Document not found.", "error")
            return redirect(url_for("admission.hod_dashboard"))
        
        # Verify HOD has access to this request
        if document.get("admission_requests", {}).get("department_id") != user.get("department_id"):
            abort(403)
        
        # Update document verification
        db.table("admission_documents").update({
            "verified": True,
            "verified_at": datetime.now().isoformat(),
            "verified_by": user["id"]
        }).eq("id", document_id).execute()
        
        write_audit_log("verify_admission_document", target=f"document:{document_id}")
        flash("Document verified.", "success")
    except Exception as e:
        flash(f"Error verifying document: {e}", "error")
    
    return redirect(url_for("admission.review_request", request_id=document["admission_request_id"]))


@admission_bp.route("/hod/approve/<request_id>", methods=["POST"])
@login_required
@dept_admin_required
def approve_request(request_id):
    """Approve admission request and generate approval form."""
    db = get_service_client()
    user = current_user()
    department_id = user.get("department_id")
    
    comments = request.form.get("comments", "")
    
    try:
        # Get admission request
        admission_request = (db.table("admission_requests")
                           .select("*, student_id")
                           .eq("id", request_id)
                           .eq("department_id", department_id)
                           .single()
                           .execute().data)
        
        if not admission_request:
            flash("Admission request not found.", "error")
            return redirect(url_for("admission.hod_dashboard"))
        
        # Check if all documents are verified
        documents = (db.table("admission_documents")
                    .select("*")
                    .eq("admission_request_id", request_id)
                    .execute().data or [])
        
        all_verified = all(doc["verified"] for doc in documents)
        
        if not all_verified:
            flash("Please verify all documents before approving.", "error")
            return redirect(url_for("admission.review_request", request_id=request_id))
        
        # Update request status
        db.table("admission_requests").update({
            "status": "approved",
            "reviewed_at": datetime.now().isoformat(),
            "reviewed_by": user["id"],
            "comments": comments
        }).eq("id", request_id).execute()
        
        # Send notification to student
        from notifications import create_notification
        create_notification(
            user_id=admission_request["student_id"],
            title="Admission Approved!",
            message="Your admission request has been approved. You can now download your departmental admission approval form.",
            notification_type="success",
            action_url="/admission"
        )
        
        write_audit_log("approve_admission", target=f"request:{request_id}")
        flash("Admission request approved.", "success")
    except Exception as e:
        flash(f"Error approving admission: {e}", "error")
    
    return redirect(url_for("admission.hod_dashboard"))


@admission_bp.route("/hod/reject/<request_id>", methods=["POST"])
@login_required
@dept_admin_required
def reject_request(request_id):
    """Reject admission request."""
    db = get_service_client()
    user = current_user()
    department_id = user.get("department_id")
    
    comments = request.form.get("comments", "")
    
    if not comments:
        flash("Comments are required for rejection.", "error")
        return redirect(url_for("admission.review_request", request_id=request_id))
    
    try:
        # Get admission request
        admission_request = (db.table("admission_requests")
                           .select("*, student_id")
                           .eq("id", request_id)
                           .eq("department_id", department_id)
                           .single()
                           .execute().data)
        
        if not admission_request:
            flash("Admission request not found.", "error")
            return redirect(url_for("admission.hod_dashboard"))
        
        # Update request status
        db.table("admission_requests").update({
            "status": "rejected",
            "reviewed_at": datetime.now().isoformat(),
            "reviewed_by": user["id"],
            "comments": comments
        }).eq("id", request_id).execute()
        
        # Send notification to student
        from notifications import create_notification
        create_notification(
            user_id=admission_request["student_id"],
            title="Admission Rejected",
            message=f"Your admission request has been rejected. Comments: {comments}",
            notification_type="warning",
            action_url="/admission"
        )
        
        write_audit_log("reject_admission", target=f"request:{request_id}")
        flash("Admission request rejected.", "warning")
    except Exception as e:
        flash(f"Error rejecting admission: {e}", "error")
    
    return redirect(url_for("admission.hod_dashboard"))


@admission_bp.route("/departmental-checklist/<request_id>")
@login_required
def departmental_checklist(request_id):
    """Generate printable Departmental Checklist (intake admission checklist)."""
    db = get_service_client()
    user = current_user()

    admission_request_res = (db.table("admission_requests")
                             .select("*, courses(name, code), departments(name), user_profiles:user_profiles!admission_requests_student_id_fkey(full_name, admission_no, email, mobile_number)")
                             .eq("id", request_id)
                             .limit(1)
                             .execute().data)
    if not admission_request_res:
        flash("Admission request not found.", "error")
        return redirect(url_for("admission.dashboard"))

    admission_request = admission_request_res[0]

    # Access control
    if user["role"] == "student" and admission_request["student_id"] != user["id"]:
        abort(403)
    if user["role"] == "dept_admin" and admission_request["department_id"] != user.get("department_id"):
        abort(403)

    # Get uploaded documents
    documents = (db.table("admission_documents")
                 .select("*")
                 .eq("admission_request_id", request_id)
                 .execute().data or [])
    uploaded_types = {doc["document_type"] for doc in documents}

    # Build intake label from reviewed_at or submitted_at
    from datetime import datetime as _dt
    intake_label = None
    date_str = admission_request.get("reviewed_at") or admission_request.get("submitted_at")
    if date_str:
        try:
            dt = _dt.fromisoformat(date_str.replace("Z", "+00:00"))
            intake_label = dt.strftime("%B %Y").upper() + " INTAKE"
        except Exception:
            pass

    return render_template("admission/departmental_checklist.html",
                           admission_request=admission_request,
                           documents=documents,
                           uploaded_types=uploaded_types,
                           intake_label=intake_label)


@admission_bp.route("/approval-form/<request_id>")
@login_required
def approval_form(request_id):
    """Generate and view departmental admission approval form."""
    db = get_service_client()
    user = current_user()
    
    # Get admission request
    admission_request_res = (db.table("admission_requests")
                       .select("*, courses(name, code), departments(name), user_profiles:user_profiles!admission_requests_student_id_fkey(full_name, admission_no, email, mobile_number)")
                       .eq("id", request_id)
                       .limit(1)
                       .execute().data)
    
    if not admission_request_res:
        flash("Admission request not found.", "error")
        return redirect(url_for("admission.dashboard"))
        
    admission_request = admission_request_res[0]
    user_prof = admission_request.get("user_profiles") or {}
    user_prof["phone"] = user_prof.get("mobile_number") or "N/A"
    user_prof["gender"] = "N/A"
    user_prof["date_of_birth"] = "N/A"
    
    # Check access permissions
    if user["role"] == "student" and admission_request["student_id"] != user["id"]:
        abort(403)
    if user["role"] == "dept_admin" and admission_request["department_id"] != user.get("department_id"):
        abort(403)
    
    # Get documents
    documents = (db.table("admission_documents")
                .select("*")
                .eq("admission_request_id", request_id)
                .execute().data or [])
    
    return render_template("admission/approval_form.html",
                          admission_request=admission_request,
                          documents=documents)
