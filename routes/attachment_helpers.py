"""
Shared helpers for the placement-first industrial attachment workflow.
Gracefully degrades when optional migration tables/columns are not yet applied.
"""

import os
import re
import uuid
from datetime import date, datetime

from db import get_service_client

ALLOWED_DOC_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
DEFAULT_GRADING_WEIGHTS = {
    "weight_gps_attendance": 10,
    "weight_logbook": 20,
    "weight_mentor_eval": 30,
    "weight_trainer_assessment": 30,
    "weight_final_report": 10,
}

MENTOR_CRITERIA = [
    ("mentor_practical_skills", "Practical Skills", 20),
    ("mentor_theory_application", "Theory Application", 20),
    ("mentor_problem_solving", "Problem Solving", 15),
    ("mentor_safety", "Safety", 15),
    ("mentor_communication", "Communication", 10),
    ("mentor_attendance", "Attendance", 10),
    ("mentor_professionalism", "Professionalism", 10),
]


def _slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", str(text or "").strip())
    text = re.sub(r"[\s]+", "_", text)
    return text.strip("_-") or "file"


def upload_placement_document(file, student_id: str, label: str) -> tuple[str, str]:
    if not file or not getattr(file, "filename", ""):
        raise ValueError(f"Please upload the {label}.")

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise ValueError(f"{label} must be PDF, JPG, JPEG, or PNG.")

    storage_path = (
        f"industrial_attachment_letters/{student_id}/"
        f"{uuid.uuid4()}_{_slug(label)}.{ext}"
    )
    raw = file.read()
    if not raw:
        raise ValueError(f"The {label} file appears to be empty.")

    bucket = "assessment-scripts"
    get_service_client().storage.from_(bucket).upload(
        path=storage_path,
        file=raw,
        file_options={
            "content-type": file.content_type or "application/octet-stream",
            "content-disposition": "inline",
        },
    )
    base_url = os.environ.get("SUPABASE_URL", "").strip()
    return f"{base_url}/storage/v1/object/public/{bucket}/{storage_path}", storage_path


def _table_ok(db, table: str) -> bool:
    try:
        db.table(table).select("id").limit(1).execute()
        return True
    except Exception:
        return False


def attachment_periods_exist(db) -> bool:
    return _table_ok(db, "attachment_periods")


def get_open_period(db, term: str = None, year: int = None):
    if not _table_ok(db, "attachment_periods"):
        return None
    try:
        q = db.table("attachment_periods").select("*").eq("is_open", True)
        if term:
            q = q.eq("term", term)
        if year:
            q = q.eq("year", year)
        rows = q.order("application_closes", desc=True).limit(1).execute().data or []
        if not rows:
            return None
        period = rows[0]
        today = date.today().isoformat()
        if period.get("application_opens") and str(period["application_opens"]) > today:
            return None
        if period.get("application_closes") and str(period["application_closes"]) < today:
            return None
        return period
    except Exception:
        return None


def list_periods(db):
    if not _table_ok(db, "attachment_periods"):
        return []
    try:
        return db.table("attachment_periods").select("*").order("year", desc=True).order("term").execute().data or []
    except Exception:
        return []


def is_student_eligible(db, student_id: str, period_id: str) -> bool:
    if not period_id or not _table_ok(db, "attachment_period_eligibility"):
        return True
    try:
        rows = (db.table("attachment_period_eligibility")
                .select("is_eligible")
                .eq("period_id", period_id)
                .eq("student_id", student_id)
                .limit(1)
                .execute().data or [])
        if not rows:
            return False
        return bool(rows[0].get("is_eligible"))
    except Exception:
        return True


def student_can_submit_placement(db, student_id: str, term: str, year: int) -> tuple[bool, str, dict]:
    """Return (allowed, message, context dict with period info)."""
    period = get_open_period(db, term, int(year) if year else None)
    if period:
        if not is_student_eligible(db, student_id, period["id"]):
            return False, (
                "You are not on the eligible list for this attachment period. "
                "Contact the Industrial Liaison Officer."
            ), {"period": period}
        return True, "", {"period": period}

    if _table_ok(db, "attachment_periods"):
        return False, (
            "No attachment application window is open for the selected term and year. "
            "Wait for the liaison officer to open the period and approve eligible trainees."
        ), {}
    return True, "", {}


def placement_status_label(status: str) -> str:
    return {
        "pending_verification": "Pending Verification",
        "needs_info": "More Information Required",
        "verified": "Verified",
        "rejected": "Rejected",
    }.get(status or "pending_verification", (status or "").replace("_", " ").title())


def compute_weighted_grade(scores: dict, weights: dict) -> float:
    """
    Sum raw section marks (each capped at its weight) into an overall mark
    out of 100. Sections are NOT percentages — e.g. GPS is marked /10,
    Logbook /20, Mentor /30, Trainer /30, Final Report /10.
    The returned total IS the overall percentage out of 100.
    """
    total = 0.0
    for key, weight in weights.items():
        score_key = key.replace("weight_", "score_")
        try:
            val = float(scores.get(score_key) or 0)
        except (TypeError, ValueError):
            val = 0.0
        max_w = float(weight or 0)
        if max_w > 0:
            total += min(max(val, 0.0), max_w)
    return round(total, 2)


def section_max(weights: dict, score_key: str) -> float:
    """Max marks for a section given its score_* key (e.g. score_gps_attendance → 10)."""
    wkey = score_key.replace("score_", "weight_")
    try:
        return float(weights.get(wkey) or DEFAULT_GRADING_WEIGHTS.get(wkey) or 0)
    except (TypeError, ValueError):
        return 0.0


def score_to_cdacc(total: float) -> str:
    if total >= 80:
        return "M"
    if total >= 65:
        return "P"
    if total >= 50:
        return "C"
    return "NYC"


def get_grading_config(db, department_id=None):
    if not _table_ok(db, "attachment_grading_config"):
        return dict(DEFAULT_GRADING_WEIGHTS)
    try:
        if department_id:
            rows = (db.table("attachment_grading_config")
                    .select("*")
                    .eq("department_id", department_id)
                    .eq("is_active", True)
                    .limit(1)
                    .execute().data or [])
            if rows:
                return rows[0]
        rows = (db.table("attachment_grading_config")
                .select("*")
                .is_("department_id", "null")
                .eq("is_active", True)
                .limit(1)
                .execute().data or [])
        return rows[0] if rows else dict(DEFAULT_GRADING_WEIGHTS)
    except Exception:
        return dict(DEFAULT_GRADING_WEIGHTS)


def notify_liaison_officers(db, title: str, message: str, action_url: str):
    try:
        from notifications import create_notification
        officers = (db.table("user_profiles")
                    .select("id")
                    .eq("role", "liaison_officer")
                    .execute().data or [])
        for officer in officers:
            create_notification(
                user_id=officer["id"],
                title=title,
                message=message,
                notification_type="info",
                action_url=action_url,
            )
    except Exception:
        pass


def week_bounds(d: date):
    """Monday–Sunday week containing date d."""
    start = d - __import__("datetime").timedelta(days=d.weekday())
    end = start + __import__("datetime").timedelta(days=6)
    return start, end
