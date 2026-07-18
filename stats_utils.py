"""
stats_utils.py — Accurate realtime dashboard count helpers.

Uses Supabase PostgREST count="exact" so KPIs are not silently capped
by the default ~1000-row select limit.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional


def exact_count(query) -> int:
    """Execute a query built with select(..., count='exact') and return count."""
    try:
        return query.execute().count or 0
    except Exception:
        return 0


def count_table(db, table: str, **eq_filters) -> int:
    """Exact row count with optional equality filters."""
    q = db.table(table).select("id", count="exact")
    for col, val in eq_filters.items():
        if val is None:
            continue
        q = q.eq(col, val)
    return exact_count(q)


def count_in(db, table: str, column: str, values: Iterable[Any], **eq_filters) -> int:
    """Exact count where column IN values (chunked to avoid URL limits)."""
    vals = [v for v in values if v is not None]
    if not vals:
        return 0
    total = 0
    chunk_size = 100
    for i in range(0, len(vals), chunk_size):
        chunk = vals[i : i + chunk_size]
        q = db.table(table).select("id", count="exact").in_(column, chunk)
        for col, val in eq_filters.items():
            if val is None:
                continue
            q = q.eq(col, val)
        total += exact_count(q)
    return total


def count_status_map(
    db,
    table: str,
    statuses: Iterable[str],
    *,
    department_id: Optional[str] = None,
    extra_eq: Optional[dict] = None,
) -> dict:
    """Return {status: exact_count} for each status."""
    out = {}
    for status in statuses:
        q = db.table(table).select("id", count="exact").eq("status", status)
        if department_id:
            q = q.eq("department_id", department_id)
        if extra_eq:
            for col, val in extra_eq.items():
                q = q.eq(col, val)
        out[status] = exact_count(q)
    return out


def clearance_kpi(db, department_id: Optional[str] = None) -> dict:
    """
    Map clearance_requests statuses to dashboard labels:
      pending  = pending + in_progress + returned
      approved = completed   (template label 'Approved/Completed')
      rejected = rejected
    """
    base = {}
    for status in ("pending", "in_progress", "returned", "completed", "rejected"):
        q = db.table("clearance_requests").select("id", count="exact").eq("status", status)
        if department_id:
            q = q.eq("department_id", department_id)
        base[status] = exact_count(q)

    pending = base["pending"] + base["in_progress"] + base["returned"]
    return {
        "pending": pending,
        "approved": base["completed"],  # templates use 'approved' for completed
        "completed": base["completed"],
        "rejected": base["rejected"],
        "returned": base["returned"],
        "in_progress": base["in_progress"],
        "total": pending + base["completed"] + base["rejected"],
    }


def role_counts(db, roles: Iterable[str], department_id: Optional[str] = None) -> dict:
    """Exact user_profiles counts by role."""
    out = {}
    for role in roles:
        q = db.table("user_profiles").select("id", count="exact").eq("role", role)
        if department_id:
            q = q.eq("department_id", department_id)
        out[role] = exact_count(q)
    return out


def attachment_status_counts(db, student_ids: list) -> dict:
    """Count industrial_attachments by status for a set of students (chunked)."""
    statuses = ("pending", "approved", "active", "completed", "rejected", "terminated")
    result = {s: 0 for s in statuses}
    if not student_ids:
        return result
    chunk_size = 80
    for i in range(0, len(student_ids), chunk_size):
        chunk = student_ids[i : i + chunk_size]
        rows = (
            db.table("industrial_attachments")
            .select("status")
            .in_("student_id", chunk)
            .execute()
            .data
            or []
        )
        for r in rows:
            s = r.get("status") or "pending"
            if s in result:
                result[s] += 1
            else:
                result[s] = result.get(s, 0) + 1
    return result
