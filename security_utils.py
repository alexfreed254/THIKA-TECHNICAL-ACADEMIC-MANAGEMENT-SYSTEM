"""
security_utils.py — Shared helpers for auth session hygiene, search sanitization,
safe redirects, and upload validation.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Optional
from urllib.parse import urlparse

from flask import request

# Fields safe to keep in the Flask session cookie (never password_hash / secrets).
SESSION_SAFE_KEYS = (
    "id",
    "role",
    "full_name",
    "email",
    "admission_no",
    "staff_no",
    "department_id",
    "is_active",
    "must_change_password",
    "mobile_number",
    "passport_url",
    "passport_file_path",
    "biometric_id",
)

# Service clearance categories → roles allowed to claim / approve when unassigned
# or when re-claiming is permitted for that service desk.
SERVICE_DEPT_ROLES = {
    "svc_library": {"library_hod", "service_clearance_officer"},
    "svc_ict": {"service_clearance_officer"},
    "svc_games": {"sports_hod", "service_clearance_officer"},
    "svc_kitchen": {"service_clearance_officer"},
    "svc_store": {"service_clearance_officer"},
    "ext_knls": {"library_hod", "service_clearance_officer"},
    "ext_community": {"library_hod", "service_clearance_officer"},
}

DEFAULT_UPLOAD_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_UPLOAD_EXTENSIONS = frozenset({"pdf", "jpg", "jpeg", "png", "webp"})


def session_safe_profile(profile: Optional[dict]) -> Optional[dict]:
    """Strip secrets (e.g. password_hash) before storing a profile in session."""
    if not profile:
        return None
    safe = {k: profile.get(k) for k in SESSION_SAFE_KEYS}
    # Preserve private auth-only keys used briefly during login (never cookie-bound).
    if "_session" in profile:
        safe["_session"] = profile["_session"]
    if profile.get("_unverified_employer"):
        safe["_unverified_employer"] = True
    return safe


def sanitize_search_query(q: str, max_len: int = 80) -> str:
    """Remove PostgREST .or_() metacharacters and LIKE wildcards from user search."""
    if not q:
        return ""
    cleaned = re.sub(r"[%,.()\"'\\]", " ", str(q))
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def safe_redirect_url(fallback: str) -> str:
    """Only redirect to same-host URLs (blocks open redirects via Referer)."""
    ref = request.referrer
    if not ref:
        return fallback
    try:
        parsed = urlparse(ref)
        if parsed.netloc and parsed.netloc != request.host:
            return fallback
        if parsed.scheme and parsed.scheme not in ("http", "https"):
            return fallback
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return path
    except Exception:
        return fallback


def allowed_upload(
    filename: str,
    data: bytes,
    *,
    allowed_ext: Optional[Iterable[str]] = None,
    max_bytes: int = DEFAULT_UPLOAD_MAX_BYTES,
) -> tuple[bool, str]:
    """Return (ok, error_message)."""
    allowed = frozenset(x.lower() for x in (allowed_ext or DEFAULT_UPLOAD_EXTENSIONS))
    if not filename or "." not in filename:
        return False, "Invalid file name."
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in allowed:
        return False, f"File type '.{ext}' is not allowed."
    if data is None:
        return False, "Empty file."
    if len(data) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        return False, f"File exceeds the {mb} MB size limit."
    return True, ""


def is_production() -> bool:
    return (
        os.environ.get("FLASK_ENV", "").lower() == "production"
        or bool(os.environ.get("RENDER"))
        or os.environ.get("ENV", "").lower() == "production"
    )


def can_approve_service_clearance(role: str, category: str, approver_id, uid: str) -> bool:
    """
    Service desks may claim unassigned rows, or act on rows assigned to them.
    Super admin always allowed. Wrong role → deny.
    """
    if role == "super_admin":
        return True
    allowed = SERVICE_DEPT_ROLES.get(category, set())
    if role not in allowed:
        return False
    if approver_id in (None, "", uid):
        return True
    return False
