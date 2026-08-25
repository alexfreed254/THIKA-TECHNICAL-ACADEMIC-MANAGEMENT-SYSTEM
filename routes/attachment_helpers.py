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


# ── Completion certificate helpers ────────────────────────────────────────────

COMPANY_CERT_LABELS = {
    "pending_company_stamp": "Pending Company Stamp",
    "company_stamped": "Company Stamped",
    "verified": "Verified",
}

INSTITUTION_NAME = "Thika Technical Training Institute"


def company_cert_label(status: str) -> str:
    return COMPANY_CERT_LABELS.get(
        status or "pending_company_stamp",
        (status or "").replace("_", " ").title(),
    )


def certificates_table_ok(db) -> bool:
    return _table_ok(db, "attachment_certificates")


def get_student_programme_dept(db, student_id: str) -> tuple[str, str]:
    """Return (programme_name, department_name) from enrollment → class → course."""
    programme = ""
    department = ""
    try:
        rows = (db.table("enrollments")
                .select(
                    "classes(name, department_id, "
                    "courses(name), departments(name))"
                )
                .eq("student_id", student_id)
                .limit(1)
                .execute().data or [])
        if rows:
            cls = rows[0].get("classes") or {}
            course = cls.get("courses") or {}
            dept = cls.get("departments") or {}
            programme = course.get("name") or cls.get("name") or ""
            department = dept.get("name") or ""
    except Exception:
        pass
    if not department:
        try:
            prof = (db.table("user_profiles")
                    .select("departments(name)")
                    .eq("id", student_id)
                    .limit(1)
                    .execute().data or [])
            if prof:
                department = ((prof[0].get("departments") or {}).get("name")) or ""
        except Exception:
            pass
    return programme, department


def attachment_completion_readiness(db, attachment_id: str) -> dict:
    """
    Evaluate prerequisites for issuing a completion certificate.

    Company stamp/signature is physical (off-portal). Industry supervisors are not
    required to confirm via the mentor portal — the trainee prints the certificate
    and presents it for manual stamp.
    """
    checks = []
    att = None
    try:
        att_rows = (db.table("industrial_attachments")
                    .select("id, status, start_date, end_date, student_id")
                    .eq("id", attachment_id)
                    .limit(1)
                    .execute().data or [])
        att = att_rows[0] if att_rows else None
    except Exception:
        att = None

    if not att:
        return {"ok": False, "checks": [], "blocking": ["Attachment not found."]}

    status = (att.get("status") or "").lower()

    status_ok = status in ("active", "completed", "approved")
    checks.append({
        "key": "attachment_status",
        "label": "Attachment in progress / ready for completion",
        "ok": status_ok,
        "detail": f"Current status: {(status or 'unknown').replace('_', ' ').title()}",
    })

    log_rows = []
    try:
        log_rows = (db.table("digital_logbook")
                    .select("id, mentor_approval_status")
                    .eq("attachment_id", attachment_id)
                    .execute().data or [])
    except Exception:
        log_rows = []
    pending_logs = [r for r in log_rows
                    if (r.get("mentor_approval_status") or "pending") != "approved"]
    has_logs = len(log_rows) > 0
    logs_ok = has_logs and len(pending_logs) == 0
    checks.append({
        "key": "logbooks",
        "label": "All required logbook entries completed & approved",
        "ok": logs_ok,
        "detail": (
            f"{len(log_rows)} entries, {len(pending_logs)} pending/rejected"
            if has_logs else "No logbook entries found"
        ),
    })

    comps = []
    try:
        comps = (db.table("competency_tracking")
                 .select("id, competency_status")
                 .eq("attachment_id", attachment_id)
                 .execute().data or [])
    except Exception:
        comps = []
    if comps:
        nyc = [c for c in comps if (c.get("competency_status") or "NYC") == "NYC"]
        comps_ok = len(nyc) == 0
        detail = f"{len(comps)} competencies recorded; {len(nyc)} still NYC"
    else:
        # Physical company stamp covers workplace sign-off; competencies optional in portal
        comps_ok = True
        detail = "No portal competency rows — company stamp on printed certificate is the workplace sign-off"
    checks.append({
        "key": "competencies",
        "label": "Workplace competencies cleared (or none recorded in portal)",
        "ok": comps_ok,
        "detail": detail,
    })

    checks.append({
        "key": "company_stamp_note",
        "label": "Company stamp is manual (print → present to industrial supervisor)",
        "ok": True,
        "detail": "Supervisor has no portal access; stamp/signature is done on the printed PDF",
    })

    blocking = [c["label"] for c in checks if not c["ok"]]
    return {
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "blocking": blocking,
        "attachment": att,
    }


def next_certificate_number(db, year: int = None) -> str:
    """Allocate TTTI-IA-YYYY-NNNNNN using sequence table when available."""
    year = int(year or datetime.now().year)
    if _table_ok(db, "attachment_certificate_sequences"):
        try:
            rows = (db.table("attachment_certificate_sequences")
                    .select("year, last_value")
                    .eq("year", year)
                    .limit(1)
                    .execute().data or [])
            if rows:
                nxt = int(rows[0].get("last_value") or 0) + 1
                db.table("attachment_certificate_sequences").update(
                    {"last_value": nxt}
                ).eq("year", year).execute()
            else:
                nxt = 1
                db.table("attachment_certificate_sequences").insert(
                    {"year": year, "last_value": nxt}
                ).execute()
            return f"TTTI-IA-{year}-{nxt:06d}"
        except Exception:
            pass

    # Fallback: scan existing numbers
    max_n = 0
    prefix = f"TTTI-IA-{year}-"
    try:
        existing = (db.table("attachment_certificates")
                    .select("certificate_number")
                    .like("certificate_number", f"{prefix}%")
                    .execute().data or [])
        for row in existing:
            try:
                max_n = max(max_n, int(str(row["certificate_number"]).rsplit("-", 1)[-1]))
            except (TypeError, ValueError, IndexError):
                continue
    except Exception:
        pass
    return f"{prefix}{max_n + 1:06d}"


def get_certificate_for_attachment(db, attachment_id: str):
    if not certificates_table_ok(db):
        return None
    try:
        rows = (db.table("attachment_certificates")
                .select("*")
                .eq("attachment_id", attachment_id)
                .limit(1)
                .execute().data or [])
        return rows[0] if rows else None
    except Exception:
        return None


def get_certificate_by_number(db, certificate_number: str):
    if not certificates_table_ok(db):
        return None
    num = (certificate_number or "").strip().upper()
    if not num:
        return None
    try:
        rows = (db.table("attachment_certificates")
                .select("*")
                .eq("certificate_number", num)
                .limit(1)
                .execute().data or [])
        return rows[0] if rows else None
    except Exception:
        return None


def issue_completion_certificate(db, attachment_id: str, issued_by: str,
                                 liaison_name: str = None) -> dict:
    """
    Mark attachment completed and create certificate row.
    Raises ValueError with a user-facing message on failure.
    """
    if not certificates_table_ok(db):
        raise ValueError("Certificate module unavailable.")

    readiness = attachment_completion_readiness(db, attachment_id)
    if not readiness["ok"]:
        raise ValueError(
            "Cannot issue certificate yet: " + "; ".join(readiness["blocking"])
        )

    existing = get_certificate_for_attachment(db, attachment_id)
    if existing:
        return existing

    att = (db.table("industrial_attachments")
           .select(
               "*, companies(name, contact_person, company_department), "
               "user_profiles!industrial_attachments_student_id_fkey"
               "(full_name, admission_no, department_id)"
           )
           .eq("id", attachment_id)
           .limit(1)
           .execute().data or [])
    if not att:
        raise ValueError("Attachment not found.")
    att = att[0]
    student = att.get("user_profiles") or {}
    company = att.get("companies") or {}
    student_id = att.get("student_id")
    programme, department = get_student_programme_dept(db, student_id)

    placement = att.get("placement_details") if isinstance(att.get("placement_details"), dict) else {}
    co_dept = (
        att.get("company_department")
        or company.get("company_department")
        or (placement or {}).get("company_department")
        or ""
    )

    year = None
    try:
        if att.get("end_date"):
            year = int(str(att["end_date"])[:4])
    except (TypeError, ValueError):
        year = None

    cert_no = next_certificate_number(db, year)
    payload = {
        "attachment_id": attachment_id,
        "certificate_number": cert_no,
        "trainee_name": student.get("full_name") or "Trainee",
        "admission_no": student.get("admission_no") or "",
        "programme": programme or "",
        "department_name": department or "",
        "institution_name": INSTITUTION_NAME,
        "company_name": company.get("name") or "Host Company",
        "company_department": co_dept or "",
        "attachment_start": att.get("start_date"),
        "attachment_end": att.get("end_date"),
        "supervisor_name": company.get("contact_person") or "",
        "liaison_officer_name": liaison_name or "",
        "system_status": "attachment_completed",
        "company_certification_status": "pending_company_stamp",
        "issued_at": datetime.utcnow().isoformat(),
        "issued_by": issued_by,
    }

    # Mark attachment completed (system status)
    db.table("industrial_attachments").update({
        "status": "completed",
    }).eq("id", attachment_id).execute()

    inserted = db.table("attachment_certificates").insert(payload).execute().data
    cert = (inserted or [payload])[0]
    if not cert.get("id"):
        # re-fetch
        cert = get_certificate_for_attachment(db, attachment_id) or payload
    return cert


def format_cert_date(value) -> str:
    if not value:
        return "—"
    s = str(value)[:10]
    try:
        d = datetime.strptime(s, "%Y-%m-%d")
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return s
