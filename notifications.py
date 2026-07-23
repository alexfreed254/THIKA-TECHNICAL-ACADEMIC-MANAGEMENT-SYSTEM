"""
notifications.py — In-App Notification System

Utility functions for creating, fetching, and managing notifications.
"""

from datetime import datetime
from db import get_service_client


def create_notification(user_id, title, message, notification_type='info',
                        action_url=None, sender_id=None, notice_id=None):
    """
    Create a new notification for a user.
    
    Args:
        user_id: UUID of the user to notify
        title: Notification title
        message: Notification message
        notification_type: 'info', 'success', 'warning', or 'error'
        action_url: Optional URL to link to when notification is clicked
        sender_id: Optional UUID of the user who sent the notice (for recall/delete)
        notice_id: Optional UUID of the dept_notices row this was created from
    """
    try:
        db = get_service_client()
        row = {
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "action_url": action_url,
            "is_read": False,
            "created_at": datetime.now().isoformat()
        }
        if sender_id:
            row["sender_id"] = sender_id
        if notice_id:
            row["notice_id"] = notice_id
        try:
            db.table("notifications").insert(row).execute()
        except Exception:
            # Columns may not exist yet — retry without optional sender fields
            row.pop("sender_id", None)
            row.pop("notice_id", None)
            db.table("notifications").insert(row).execute()
    except Exception as e:
        print(f"[notifications] Failed to create notification: {e}")


def delete_notifications_for_notice(notice_id=None, title=None, message=None, sender_id=None):
    """
    Recall/delete recipient notifications for a sent notice.
    Prefer notice_id; fall back to title+message (+ optional sender_id).
    Returns number of rows deleted (best-effort).
    """
    deleted = 0
    try:
        db = get_service_client()
        if notice_id:
            try:
                before = (db.table("notifications").select("id", count="exact")
                            .eq("notice_id", notice_id).execute())
                count = before.count or 0
                db.table("notifications").delete().eq("notice_id", notice_id).execute()
                deleted = max(deleted, count)
            except Exception:
                pass
        if title and message:
            q = (db.table("notifications").select("id", count="exact")
                   .eq("title", title).eq("message", message))
            if sender_id:
                try:
                    q = q.eq("sender_id", sender_id)
                except Exception:
                    pass
            before = q.execute()
            count = before.count or 0
            dq = (db.table("notifications").delete()
                    .eq("title", title).eq("message", message))
            if sender_id:
                try:
                    dq = dq.eq("sender_id", sender_id)
                except Exception:
                    pass
            dq.execute()
            deleted = max(deleted, count)
    except Exception as e:
        print(f"[notifications] Failed to delete notice notifications: {e}")
    return deleted


def delete_user_notification(notification_id, user_id):
    """Recipient deletes one of their own inbox notifications."""
    try:
        db = get_service_client()
        db.table("notifications").delete().eq("id", notification_id).eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"[notifications] Failed to delete user notification: {e}")
        return False


def get_user_notifications(user_id, limit=20, unread_only=False):
    """
    Fetch notifications for a user.
    
    Args:
        user_id: UUID of the user
        limit: Maximum number of notifications to return
        unread_only: If True, only return unread notifications
    
    Returns:
        List of notification dictionaries
    """
    try:
        db = get_service_client()
        query = db.table("notifications").select("*").eq("user_id", user_id)
        
        if unread_only:
            query = query.eq("is_read", False)
        
        notifications = query.order("created_at", desc=True).limit(limit).execute().data
        return notifications
    except Exception as e:
        print(f"[notifications] Failed to fetch notifications: {e}")
        return []


def get_unread_count(user_id):
    """
    Get the count of unread notifications for a user.
    
    Args:
        user_id: UUID of the user
    
    Returns:
        Integer count of unread notifications
    """
    try:
        db = get_service_client()
        result = db.table("notifications").select("id", count="exact").eq(
            "user_id", user_id
        ).eq("is_read", False).execute()
        return result.count or 0
    except Exception as e:
        print(f"[notifications] Failed to get unread count: {e}")
        return 0


def mark_notification_as_read(notification_id, user_id):
    """
    Mark a notification as read.
    
    Args:
        notification_id: UUID of the notification
        user_id: UUID of the user (for verification)
    """
    try:
        db = get_service_client()
        db.table("notifications").update({
            "is_read": True
        }).eq("id", notification_id).eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[notifications] Failed to mark notification as read: {e}")


def mark_all_as_read(user_id):
    """
    Mark all notifications for a user as read.
    
    Args:
        user_id: UUID of the user
    """
    try:
        db = get_service_client()
        db.table("notifications").update({
            "is_read": True
        }).eq("user_id", user_id).execute()
    except Exception as e:
        print(f"[notifications] Failed to mark all as read: {e}")


def notify_new_student(student_id, department_name, class_name):
    """Notify dept admin when a new student is registered."""
    try:
        db = get_service_client()
        # Get dept admin for the student's department
        student = db.table("user_profiles").select(
            "*, departments(name)"
        ).eq("id", student_id).execute().data
        
        if student:
            dept_id = student[0].get("department_id")
            if dept_id:
                dept_admins = db.table("user_profiles").select("*").eq(
                    "role", "dept_admin"
                ).eq("department_id", dept_id).execute().data
                
                for admin in dept_admins:
                    create_notification(
                        user_id=admin["id"],
                        title="New Student Registered",
                        message=f"A new student {student[0]['full_name']} has been registered in {class_name}.",
                        notification_type="info",
                        action_url=f"/dept-admin/students"
                    )
    except Exception as e:
        print(f"[notifications] Failed to notify new student: {e}")


def notify_assessment_submitted(student_id, assessment_title, trainer_id):
    """Notify trainer when a student submits an assessment."""
    create_notification(
        user_id=trainer_id,
        title="Assessment Submitted",
        message=f"A student has submitted assessment: {assessment_title}",
        notification_type="info",
        action_url="/trainer/assessments"
    )


def notify_assessment_reviewed(student_id, assessment_title, status):
    """Notify student when their assessment is reviewed."""
    status_text = "approved" if status == "approved" else "rejected"
    create_notification(
        user_id=student_id,
        title=f"Assessment {status_text}",
        message=f"Your assessment '{assessment_title}' has been {status_text}.",
        notification_type="success" if status == "approved" else "warning",
        action_url="/student/assessments"
    )


def notify_job_application(student_id, job_title, employer_id):
    """Notify employer when a student applies for a job."""
    create_notification(
        user_id=employer_id,
        title="New Job Application",
        message=f"A student has applied for: {job_title}",
        notification_type="info",
        action_url="/employer/applications"
    )


def notify_application_status(student_id, job_title, status):
    """Notify student when their job application status changes."""
    create_notification(
        user_id=student_id,
        title=f"Application {status}",
        message=f"Your application for '{job_title}' is now {status}.",
        notification_type="success" if status in ("accepted", "shortlisted") else "info",
        action_url="/student/jobs"
    )


def notify_dept_notice(department_id, title, message, notice_type='info',
                       action_url=None, class_id=None, sender_id=None, notice_id=None):
    """
    Send an official notice/memo from dept admin to all trainees in a department.
    Optionally restrict to a specific class_id.
    Returns the count of trainees notified.
    """
    try:
        db = get_service_client()
        query = (db.table("user_profiles")
                   .select("id")
                   .eq("role", "student")
                   .eq("department_id", department_id))
        if class_id:
            # Filter students enrolled in the given class
            enrolled = (db.table("enrollments")
                          .select("student_id")
                          .eq("class_id", class_id)
                          .execute().data or [])
            ids = [e["student_id"] for e in enrolled if e.get("student_id")]
            if not ids:
                return 0
            query = (db.table("user_profiles")
                       .select("id")
                       .eq("role", "student")
                       .in_("id", ids))
        students = query.execute().data or []
        for s in students:
            create_notification(
                user_id=s["id"],
                title=title,
                message=message,
                notification_type=notice_type,
                action_url=action_url or "/notifications",
                sender_id=sender_id,
                notice_id=notice_id,
            )
        return len(students)
    except Exception as e:
        print(f"[notifications] Failed to send dept notice: {e}")
        return 0
