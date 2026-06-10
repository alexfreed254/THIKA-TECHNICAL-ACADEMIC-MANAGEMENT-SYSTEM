"""
routes/biometric.py — Biometric Attendance Module

Adds fingerprint-based attendance on top of the existing manual system.

Two sections:
  1. Trainer UI  — /trainer/biometric/* (requires browser login)
  2. Device API  — /api/biometric/scan   (called by BioEntry W device)

DB additions required (run biometric_migration.sql in Supabase):
  - biometric_sessions table
  - user_profiles.biometric_id column
"""

import os
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, jsonify, abort)
from auth_utils import trainer_required, write_audit_log, current_user
from db import get_service_client

biometric_bp = Blueprint("biometric", __name__)

# Shared secret the BioEntry W device sends in X-Device-Token header.
# Set BIOMETRIC_DEVICE_SECRET in your .env / Render environment.
# If blank, the endpoint accepts all requests (development only).
_DEVICE_SECRET = os.environ.get("BIOMETRIC_DEVICE_SECRET", "")


# ─────────────────────────────────────────────────────────────────────────────
# TRAINER UI
# ─────────────────────────────────────────────────────────────────────────────

@biometric_bp.route("/trainer/biometric")
@trainer_required
def biometric_home():
    """Setup page — trainer selects class/unit/week/lesson and starts a session."""
    db   = get_service_client()
    user = current_user()

    # Trainer's classes
    cu_rows = (db.table("class_units")
                 .select("class_id, classes(id, name)")
                 .eq("trainer_id", user["id"])
                 .execute().data or [])
    seen = set()
    class_list = []
    for r in cu_rows:
        c = r.get("classes") or {}
        if c.get("id") and c["id"] not in seen:
            seen.add(c["id"])
            class_list.append(c)
    class_list.sort(key=lambda x: x.get("name", ""))

    class_id = request.args.get("class_id", "")
    unit_id  = request.args.get("unit_id", "")

    units_list = []
    if class_id:
        units_list = (db.table("class_units")
                        .select("unit_id, units(id, code, name)")
                        .eq("class_id", class_id)
                        .eq("trainer_id", user["id"])
                        .execute().data or [])

    # Any open session by this trainer
    open_sessions = (db.table("biometric_sessions")
                       .select("*")
                       .eq("trainer_id", user["id"])
                       .eq("status", "open")
                       .order("created_at", desc=True)
                       .execute().data or [])

    return render_template("trainer/biometric_attendance.html",
                           class_list=class_list,
                           class_id=class_id,
                           units_list=units_list,
                           unit_id=unit_id,
                           open_sessions=open_sessions,
                           year=datetime.now().year)


@biometric_bp.route("/trainer/biometric/start", methods=["POST"])
@trainer_required
def biometric_start():
    """Create a new biometric attendance session."""
    db   = get_service_client()
    user = current_user()

    class_id  = request.form.get("class_id", "").strip()
    unit_id   = request.form.get("unit_id", "").strip()
    week      = request.form.get("week", "1").strip()
    lesson    = request.form.get("lesson", "1").strip()
    year      = request.form.get("year", str(datetime.now().year)).strip()
    term      = request.form.get("term", "1").strip()
    device_ip = request.form.get("device_ip", "").strip()

    if not all([class_id, unit_id, week, lesson]):
        flash("Class, Unit, Week and Lesson are all required.", "error")
        return redirect(url_for("biometric.biometric_home"))

    # Resolve unit_code
    unit_row = (db.table("units").select("code, name")
                  .eq("id", unit_id).limit(1).execute().data or [{}])[0]
    unit_code = unit_row.get("code", "")

    # Guard: no duplicate open session for same class/unit/week/lesson
    dup = (db.table("biometric_sessions")
             .select("id")
             .eq("trainer_id", user["id"])
             .eq("unit_id", unit_id)
             .eq("week", int(week))
             .eq("lesson", lesson)
             .eq("year", int(year))
             .eq("term", int(term))
             .eq("status", "open")
             .execute().data or [])
    if dup:
        flash("A session for this unit/week/lesson is already open.", "warning")
        return redirect(url_for("biometric.biometric_session", session_id=dup[0]["id"]))

    res = db.table("biometric_sessions").insert({
        "trainer_id": user["id"],
        "class_id":   class_id,
        "unit_id":    unit_id,
        "unit_code":  unit_code,
        "week":       int(week),
        "lesson":     lesson,
        "year":       int(year),
        "term":       int(term),
        "status":     "open",
        "device_ip":  device_ip,
    }).execute()

    session_id = res.data[0]["id"] if res.data else None
    if not session_id:
        flash("Failed to create session.", "error")
        return redirect(url_for("biometric.biometric_home"))

    write_audit_log("biometric_session_start",
                    target=f"unit:{unit_id},week:{week},lesson:{lesson}")
    return redirect(url_for("biometric.biometric_session", session_id=session_id))


@biometric_bp.route("/trainer/biometric/session/<session_id>")
@trainer_required
def biometric_session(session_id):
    """Live session view — polls every 3 s for new scans."""
    db   = get_service_client()
    user = current_user()

    sess = (db.table("biometric_sessions")
              .select("*")
              .eq("id", session_id)
              .eq("trainer_id", user["id"])
              .limit(1)
              .execute().data or [])
    if not sess:
        abort(404)
    sess = sess[0]

    # All enrolled students for this class
    enrolled = (db.table("enrollments")
                  .select("student_id, user_profiles!enrollments_student_id_fkey(full_name, admission_no, biometric_id)")
                  .eq("class_id", sess["class_id"])
                  .execute().data or [])

    # Who has already been marked present this session
    scanned = (db.table("attendance")
                 .select("student_id")
                 .eq("unit_id", sess["unit_id"])
                 .eq("trainer_id", user["id"])
                 .eq("week", sess["week"])
                 .eq("lesson", sess["lesson"])
                 .eq("year", sess["year"])
                 .eq("term", sess["term"])
                 .eq("status", "present")
                 .execute().data or [])
    scanned_ids = {r["student_id"] for r in scanned}

    students = []
    for e in enrolled:
        p = e.get("user_profiles") or {}
        students.append({
            "id":           e["student_id"],
            "full_name":    p.get("full_name", "—"),
            "admission_no": p.get("admission_no", "—"),
            "biometric_id": p.get("biometric_id", ""),
            "scanned":      e["student_id"] in scanned_ids,
        })
    students.sort(key=lambda x: x["full_name"])

    # Resolve unit name
    unit_row = (db.table("units").select("code, name")
                  .eq("id", sess["unit_id"]).limit(1).execute().data or [{}])[0]
    class_row = (db.table("classes").select("name")
                   .eq("id", sess["class_id"]).limit(1).execute().data or [{}])[0]

    return render_template("trainer/biometric_session.html",
                           sess=sess,
                           students=students,
                           scanned_count=len(scanned_ids),
                           total_count=len(students),
                           unit=unit_row,
                           cls=class_row,
                           scan_url=request.host_url.rstrip("/") + "/api/biometric/scan")


@biometric_bp.route("/trainer/biometric/session/<session_id>/status")
@trainer_required
def biometric_session_status(session_id):
    """AJAX endpoint — returns current scan status as JSON for live polling."""
    db   = get_service_client()
    user = current_user()

    sess = (db.table("biometric_sessions")
              .select("status")
              .eq("id", session_id)
              .eq("trainer_id", user["id"])
              .limit(1)
              .execute().data or [])
    if not sess:
        return jsonify({"error": "not found"}), 404

    enrolled = (db.table("enrollments")
                  .select("student_id, user_profiles!enrollments_student_id_fkey(full_name, admission_no)")
                  .eq("class_id", request.args.get("class_id", ""))
                  .execute().data or [])

    # Re-fetch from the session row
    full_sess = (db.table("biometric_sessions")
                   .select("*")
                   .eq("id", session_id)
                   .single()
                   .execute().data or {})

    scanned = (db.table("attendance")
                 .select("student_id, user_profiles!attendance_student_id_fkey(full_name, admission_no)")
                 .eq("unit_id", full_sess.get("unit_id", ""))
                 .eq("trainer_id", user["id"])
                 .eq("week", full_sess.get("week", 0))
                 .eq("lesson", full_sess.get("lesson", ""))
                 .eq("year", full_sess.get("year", 0))
                 .eq("term", full_sess.get("term", 0))
                 .eq("status", "present")
                 .execute().data or [])

    return jsonify({
        "session_status": full_sess.get("status", "open"),
        "scanned_count": len(scanned),
        "scanned": [
            {
                "id":           r["student_id"],
                "full_name":    (r.get("user_profiles") or {}).get("full_name", "—"),
                "admission_no": (r.get("user_profiles") or {}).get("admission_no", "—"),
            }
            for r in scanned
        ]
    })


@biometric_bp.route("/trainer/biometric/session/<session_id>/close", methods=["POST"])
@trainer_required
def biometric_close(session_id):
    """Close session — marks all un-scanned students absent."""
    db   = get_service_client()
    user = current_user()

    sess_rows = (db.table("biometric_sessions")
                   .select("*")
                   .eq("id", session_id)
                   .eq("trainer_id", user["id"])
                   .limit(1)
                   .execute().data or [])
    if not sess_rows:
        abort(404)
    sess = sess_rows[0]

    if sess["status"] != "open":
        flash("Session is already closed.", "info")
        return redirect(url_for("biometric.biometric_home"))

    # Enrolled students
    enrolled = (db.table("enrollments")
                  .select("student_id")
                  .eq("class_id", sess["class_id"])
                  .execute().data or [])

    # Already recorded (present)
    already = (db.table("attendance")
                 .select("student_id")
                 .eq("unit_id", sess["unit_id"])
                 .eq("trainer_id", user["id"])
                 .eq("week", sess["week"])
                 .eq("lesson", sess["lesson"])
                 .eq("year", sess["year"])
                 .eq("term", sess["term"])
                 .execute().data or [])
    already_ids = {r["student_id"] for r in already}

    # Mark absent for everyone not yet recorded
    absent_rows = []
    for e in enrolled:
        sid = e["student_id"]
        if sid not in already_ids:
            absent_rows.append({
                "student_id": sid,
                "unit_id":    sess["unit_id"],
                "unit_code":  sess.get("unit_code", ""),
                "trainer_id": user["id"],
                "lesson":     sess["lesson"],
                "week":       sess["week"],
                "year":       sess["year"],
                "term":       sess["term"],
                "status":     "absent",
            })
    if absent_rows:
        db.table("attendance").insert(absent_rows).execute()

    # Close the session
    db.table("biometric_sessions").update({
        "status":    "closed",
        "closed_at": datetime.utcnow().isoformat(),
    }).eq("id", session_id).execute()

    write_audit_log("biometric_session_close",
                    target=f"session:{session_id}",
                    detail={"absent_added": len(absent_rows)})
    flash(f"Session closed. {len(absent_rows)} student(s) marked absent.", "success")
    return redirect(url_for("biometric.biometric_home"))


# ─────────────────────────────────────────────────────────────────────────────
# DEVICE API  — called by BioEntry W, no browser session required
# ─────────────────────────────────────────────────────────────────────────────

@biometric_bp.route("/api/biometric/scan", methods=["POST"])
def device_scan():
    """
    BioEntry W posts here when a fingerprint is scanned.

    Expected JSON body (all BioEntry W firmware variants):
      { "fingerprint_id": "1234",  "device_id": "BW-001" }
    or
      { "user_id": "1234",         "device_id": "BW-001" }

    Optional header:  X-Device-Token: <BIOMETRIC_DEVICE_SECRET>
    """
    # Token check
    if _DEVICE_SECRET:
        token = (request.headers.get("X-Device-Token")
                 or (request.json or {}).get("device_token", ""))
        if token != _DEVICE_SECRET:
            return jsonify({"status": "error", "message": "Invalid device token"}), 403

    data = request.get_json(force=True, silent=True) or {}
    fingerprint_id = str(
        data.get("fingerprint_id") or data.get("user_id") or ""
    ).strip()
    device_ip = data.get("device_ip") or request.remote_addr or ""

    if not fingerprint_id:
        return jsonify({"status": "error", "message": "Missing fingerprint_id"}), 400

    db = get_service_client()

    # Find the best open session:
    # 1) Matches device_ip exactly   2) Most recent open session (fallback)
    open_sessions = (db.table("biometric_sessions")
                       .select("*")
                       .eq("status", "open")
                       .order("created_at", desc=True)
                       .execute().data or [])

    sess = None
    for s in open_sessions:
        if s.get("device_ip") and s["device_ip"] == device_ip:
            sess = s
            break
    if sess is None and open_sessions:
        sess = open_sessions[0]   # fallback: most recent

    if not sess:
        return jsonify({"status": "error", "message": "No active attendance session"}), 404

    # Match student by biometric_id
    student_rows = (db.table("user_profiles")
                      .select("id, full_name, admission_no")
                      .eq("biometric_id", fingerprint_id)
                      .eq("role", "student")
                      .limit(1)
                      .execute().data or [])

    if not student_rows:
        return jsonify({
            "status":  "error",
            "message": f"No student linked to fingerprint ID {fingerprint_id}"
        }), 404

    student = student_rows[0]

    # Check if already recorded this session
    existing = (db.table("attendance")
                  .select("id, status")
                  .eq("student_id",  student["id"])
                  .eq("unit_id",     sess["unit_id"])
                  .eq("trainer_id",  sess["trainer_id"])
                  .eq("week",        sess["week"])
                  .eq("lesson",      sess["lesson"])
                  .eq("year",        sess["year"])
                  .eq("term",        sess["term"])
                  .limit(1)
                  .execute().data or [])

    if existing:
        return jsonify({
            "status":       "already_recorded",
            "student_name": student["full_name"],
            "admission_no": student["admission_no"],
        })

    # Insert present record into existing attendance table
    db.table("attendance").insert({
        "student_id":      student["id"],
        "unit_id":         sess["unit_id"],
        "unit_code":       sess.get("unit_code", ""),
        "trainer_id":      sess["trainer_id"],
        "lesson":          sess["lesson"],
        "week":            sess["week"],
        "year":            sess["year"],
        "term":            sess["term"],
        "status":          "present",
        "attendance_date": datetime.utcnow().isoformat(),
    }).execute()

    return jsonify({
        "status":       "success",
        "message":      f"{student['full_name']} marked present",
        "student_name": student["full_name"],
        "admission_no": student["admission_no"],
    })


@biometric_bp.route("/api/biometric/scan/test", methods=["GET", "POST"])
def device_scan_test():
    """Quick connectivity test — returns server time and open session count."""
    db = get_service_client()
    open_count = (db.table("biometric_sessions")
                    .select("id", count="exact")
                    .eq("status", "open")
                    .execute().count or 0)
    return jsonify({
        "status":         "ok",
        "server_time":    datetime.utcnow().isoformat() + "Z",
        "open_sessions":  open_count,
    })
