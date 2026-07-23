"""
Shared Unit Attendance Register (landscape) — all weeks taught for a class/unit.

Used by Trainer, Dept Admin (HOD), and Super Admin.
Columns are sessions that actually have attendance, each showing the real
date/time attendance was taken.
"""

from __future__ import annotations

from collections import defaultdict, OrderedDict
from datetime import datetime


def _norm_lesson(lesson) -> str:
    s = str(lesson or "").strip()
    return f"L{s}" if s in ("1", "2", "3", "4") else s


def _parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except Exception:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value)[:19], fmt)
            except Exception:
                continue
    return None


def _fmt_session_time(dt: datetime | None) -> dict:
    if not dt:
        return {"date_label": "—", "time_label": "", "full": ""}
    # Prefer local-looking wall clock from stored timestamp
    return {
        "date_label": dt.strftime("%d %b"),
        "time_label": dt.strftime("%H:%M"),
        "full": dt.strftime("%d %b %Y %H:%M"),
    }


def build_unit_attendance_register(
    db,
    *,
    class_id: str,
    unit_id: str,
    year: int,
    term: int,
    trainer_id: str | None = None,
) -> dict | None:
    """
    Build register data for landscape PDF/HTML.

    If trainer_id is set, only that trainer's attendance rows are included
    (trainer portal). HOD / Super Admin pass trainer_id=None for all trainers.
    Returns None when there are no attendance rows.
    """
    cls = (db.table("classes").select("name, department_id")
             .eq("id", class_id).single().execute().data or {})
    unit = (db.table("units").select("code, name")
              .eq("id", unit_id).single().execute().data or {})

    dept = {}
    dept_id = cls.get("department_id")
    if dept_id:
        dept = (db.table("departments").select("name, code")
                  .eq("id", dept_id).single().execute().data or {})

    trainer_name = ""
    try:
        cu_q = (db.table("class_units")
                  .select("trainer_id, user_profiles!class_units_trainer_id_fkey(full_name)")
                  .eq("class_id", class_id)
                  .eq("unit_id", unit_id))
        if trainer_id:
            cu_q = cu_q.eq("trainer_id", trainer_id)
        cu = cu_q.limit(1).execute().data or []
        if cu:
            trainer_name = (cu[0].get("user_profiles") or {}).get("full_name", "") or ""
            if not trainer_id:
                trainer_id_resolved = cu[0].get("trainer_id")
            else:
                trainer_id_resolved = trainer_id
        else:
            trainer_id_resolved = trainer_id
    except Exception:
        trainer_id_resolved = trainer_id

    if trainer_id and not trainer_name:
        try:
            tp = (db.table("user_profiles").select("full_name")
                    .eq("id", trainer_id).limit(1).execute().data or [])
            if tp:
                trainer_name = tp[0].get("full_name") or ""
        except Exception:
            pass

    q = (db.table("attendance")
           .select("student_id, week, lesson, status, attendance_date, trainer_id, "
                   "user_profiles:student_id(full_name, admission_no)")
           .eq("unit_id", unit_id)
           .eq("year", int(year))
           .eq("term", int(term)))
    if trainer_id:
        q = q.eq("trainer_id", trainer_id)

    att_rows = q.execute().data or []
    if not att_rows:
        return None

    # Session columns = only weeks/lessons that were actually taught/marked
    session_times: dict[tuple, list] = defaultdict(list)
    matrix = defaultdict(dict)
    students = OrderedDict()

    for r in att_rows:
        if r.get("week") is None or not r.get("lesson"):
            continue
        key = (int(r["week"]), _norm_lesson(r["lesson"]))
        st = (r.get("status") or "").lower()
        sid = r.get("student_id")
        if not sid:
            continue
        matrix[sid][key] = st
        ts = _parse_ts(r.get("attendance_date"))
        if ts:
            session_times[key].append(ts)
        if sid not in students:
            p = r.get("user_profiles") or {}
            students[sid] = {
                "id": sid,
                "full_name": p.get("full_name") or "—",
                "admission_no": p.get("admission_no") or "—",
            }

    # Full class roll so unmarked trainees still appear
    enrolled = (db.table("enrollments")
                  .select("student_id, user_profiles(id, full_name, admission_no)")
                  .eq("class_id", class_id)
                  .execute().data or [])
    for e in enrolled:
        sid = e.get("student_id")
        if not sid:
            continue
        p = e.get("user_profiles") or {}
        if sid not in students:
            students[sid] = {
                "id": sid,
                "full_name": p.get("full_name") or "—",
                "admission_no": p.get("admission_no") or "—",
            }

    session_keys = sorted(session_times.keys()) or sorted({
        (int(r["week"]), _norm_lesson(r["lesson"]))
        for r in att_rows if r.get("week") is not None and r.get("lesson")
    })

    session_cols = []
    for w, les in session_keys:
        times = session_times.get((w, les)) or []
        # Earliest mark time ≈ when the session attendance was taken
        taken = min(times) if times else None
        labels = _fmt_session_time(taken)
        session_cols.append({
            "week": w,
            "lesson": les,
            "label": f"W{w}-{les}",
            "date_label": labels["date_label"],
            "time_label": labels["time_label"],
            "taken_full": labels["full"],
        })

    student_rows = []
    for sid, stu in sorted(
        students.items(),
        key=lambda x: ((x[1].get("full_name") or "").lower(), x[1].get("admission_no") or ""),
    ):
        cells = []
        present = absent = late = 0
        for key in session_keys:
            st = matrix.get(sid, {}).get(key, "")
            if st == "present":
                present += 1
                mark = "P"
            elif st == "late":
                late += 1
                present += 1
                mark = "L"
            elif st == "absent":
                absent += 1
                mark = "A"
            else:
                mark = "—"
            cells.append({"status": st or "none", "mark": mark})
        marked = sum(1 for c in cells if c["mark"] != "—")
        rate = round((present / marked) * 100, 1) if marked else 0
        student_rows.append({
            **stu,
            "cells": cells,
            "present": present,
            "absent": absent,
            "late": late,
            "marked": marked,
            "rate": rate,
        })

    generated = datetime.now().strftime("%d %B %Y %H:%M")
    unit_code = (unit.get("code") or "UNIT").upper().replace(" ", "")[:16]
    ref_code = f"ATT/{unit_code}/T{term}/{year}"

    return {
        "cls": cls,
        "unit": unit,
        "dept": dept,
        "year": year,
        "term": term,
        "session_cols": session_cols,
        "student_rows": student_rows,
        "trainer": {"name": trainer_name or "—", "id": trainer_id_resolved},
        "generated": generated,
        "ref_code": ref_code,
        "session_count": len(session_cols),
        "student_count": len(student_rows),
    }
