"""
routes/notifications.py — Notification display routes

Endpoints for viewing and managing notifications.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from auth_utils import login_required
from notifications import get_user_notifications, get_unread_count, mark_notification_as_read, mark_all_as_read

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("/")
@login_required
def index():
    """View all notifications for the current user."""
    from auth_utils import current_user
    user = current_user()
    
    notifications = get_user_notifications(user["id"], limit=50)
    unread_count = get_unread_count(user["id"])
    
    return render_template("notifications/index.html",
                          user=user,
                          notifications=notifications,
                          unread_count=unread_count)


@notifications_bp.route("/unread")
@login_required
def unread():
    """View only unread notifications."""
    from auth_utils import current_user
    user = current_user()
    
    notifications = get_user_notifications(user["id"], limit=50, unread_only=True)
    unread_count = get_unread_count(user["id"])
    
    return render_template("notifications/index.html",
                          user=user,
                          notifications=notifications,
                          unread_count=unread_count,
                          unread_only=True)


@notifications_bp.route("/<notification_id>/read", methods=["POST"])
@login_required
def mark_read(notification_id):
    """Mark a specific notification as read."""
    from auth_utils import current_user
    user = current_user()
    
    mark_notification_as_read(notification_id, user["id"])
    
    if request.headers.get("Content-Type") == "application/json":
        return jsonify({"success": True})
    
    return redirect(request.referrer or "/notifications")


@notifications_bp.route("/mark-all-read", methods=["POST"])
@login_required
def mark_all_read():
    """Mark all notifications as read for the current user."""
    from auth_utils import current_user
    user = current_user()
    
    mark_all_as_read(user["id"])
    
    if request.headers.get("Content-Type") == "application/json":
        return jsonify({"success": True})
    
    return redirect(request.referrer or "/notifications")


@notifications_bp.route("/count")
@login_required
def count():
    """API endpoint to get unread notification count."""
    from auth_utils import current_user
    user = current_user()

    count = get_unread_count(user["id"])
    return jsonify({"count": count})


@notifications_bp.route("/recent")
@login_required
def recent():
    """API endpoint returning the 7 most recent notifications for the dropdown panel."""
    from auth_utils import current_user
    user = current_user()

    notifications = get_user_notifications(user["id"], limit=7)
    unread_count = get_unread_count(user["id"])

    return jsonify({"notifications": notifications, "unread_count": unread_count})
