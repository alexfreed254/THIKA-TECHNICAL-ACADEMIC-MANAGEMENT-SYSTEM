"""
notifications.py — In-App Notification System

Utility functions for creating, fetching, and managing notifications.
"""

from datetime import datetime
from db import get_service_client


def create_notification(user_id, title, message, notification_type='info', action_url=None):
    """
    Create a new notification for a user.
    
    Args:
        user_id: UUID of the user to notify
        title: Notification title
        message: Notification message
        notification_type: 'info', 'success', 'warning', or 'error'
        action_url: Optional URL to link to when notification is clicked
    """
    try:
        db = get_service_client()
        db.table("notifications").insert({
            "user_id": user_id,
            "title": title,
            "message": message,
            "type": notification_type,
            "action_url": action_url,
            "is_read": False,
            "created_at": datetime.now().isoformat()
        }).execute()
    except Exception as e:
        print(f"[notifications] Failed to create notification: {e}")


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
                       action_url=None, class_id=None):
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
                action_url=action_url or "/notifications"
            )
        return len(students)
    except Exception as e:
        print(f"[notifications] Failed to send dept notice: {e}")
        return 0
