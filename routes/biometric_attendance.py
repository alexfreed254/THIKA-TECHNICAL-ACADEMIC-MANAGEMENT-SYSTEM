"""
routes/biometric_attendance.py — Biometric Fingerprint Attendance System

Fingerprint sensors installed in classrooms send scan data to /biometric/api/scan.
Trainer starts a session selecting class, unit, room, lesson time, week, term, year.
Attendance is saved into the same `attendance` table used by manual attendance.
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from auth_utils import trainer_required, current_user, write_audit_log
from db import get_service_client
from datetime import datetime, date
import threading
import os

biometric_bp = Blueprint("biometric", __name__)

# ── In-memory session store (short-lived, per lesson) ────────────────────────
# Structure: { session_id: { ...session data, students: [{id, name, adm_no, biometric_id, status}] } }
_sessions = {}
_lock = threading.Lock()

LESSON_TIMES = [
    {"value": "1", "label": "Lesson 1",  "time": "08:00 – 10:00 AM"},
    {"value": "2", "label": "Lesson 2",  "time": "10:15 – 12:15 PM"},
    {"value": "3", "label": "Lesson 3",  "time": "12:45 – 02:45 PM"},
    {"value": "4", "label": "Lesson 4",  "time": "03:00 – 05:00 PM"},
]


def _trainer_class_unit_pairs(db, trainer_id):
    """Return list of {class_id, class_name, unit_id, unit_code, unit_name} for this trainer."""
    rows = (db.table("class_units")
              .select("class_id, unit_id, classes(id, name), units(id, code, name)")
              .eq("trainer_id", trainer_id)
              .execute().data or [])
    pairs = []
    seen = set()
    for r in rows:
        cls  = r.get("classes") or {}
        unit = r.get("units")  or {}
        cid  = cls.get("id")
        uid  = unit.get("id")
        if not cid or not uid:
            continue
        key = (cid, uid)
        if key in seen:
            continue
        seen.add(key)
        pairs.append({
            "class_id":   cid,
            "class_name": cls.get("name", ""),
            "unit_id":    uid,
            "unit_code":  unit.get("code", ""),
            "unit_name":  unit.get("name", ""),
        })
    return pairs


def _class_students(db, class_id):
    """Return enrolled students with biometric_id for a class."""
    rows = (db.table("enrollments")
              .select("student_id, user_profiles!enrollments_student_id_fkey(id, full_name, admission_no, biometric_id)")
              .eq("class_id", class_id)
              .execute().data or [])
    students = []
    for r in rows:
        p = r.get("user_profiles") or {}
        sid = p.get("id") or r.get("student_id")
        if not sid:
            continue
        students.append({
            "id":           sid,
            "name":         p.get("full_name") or "Unknown",
            "admission_no": p.get("admission_no") or "",
            "biometric_id": str(p.get("biometric_id") or ""),
            "status":       "absent",
            "marked_manual": False,
        })
    students.sort(key=lambda s: s["name"])
    return students


# ── Setup page ────────────────────────────────────────────────────────────────

@biometric_bp.route("/", methods=["GET", "POST"])
@trainer_required
def biometric_home():
    db = get_service_client()
    user = current_user()
    trainer_id = user["id"]

    pairs = _trainer_class_unit_pairs(db, trainer_id)

    # Derive distinct classes and units for dropdowns
    class_map = {}
    for p in pairs:
        cid = p["class_id"]
        if cid not in class_map:
            class_map[cid] = p["class_name"]
    classes = sorted([{"id": k, "name": v} for k, v in class_map.items()], key=lambda x: x["name"])

    current_year = datetime.now().year
    current_week = datetime.now().isocalendar()[1]

    if request.method == "POST":
        class_id = request.form.get("class_id", "").strip()
        unit_id  = request.form.get("unit_id",  "").strip()
        room     = request.form.get("room",     "").strip()
        lesson   = request.form.get("lesson",   "").strip()
        week     = request.form.get("week",     "").strip()
        term     = request.form.get("term",     "").strip()
        year     = request.form.get("year",     str(current_year)).strip()

        if not all([class_id, unit_id, room, lesson, week, term, year]):
            flash("All fields are required.", "error")
            return redirect(url_for("biometric.biometric_home"))

        # Verify trainer teaches this class/unit combination
        valid = any(p["class_id"] == class_id and p["unit_id"] == unit_id for p in pairs)
        if not valid:
            flash("You are not assigned to this class/unit combination.", "error")
            return redirect(url_for("biometric.biometric_home"))

        students = _class_students(db, class_id)
        if not students:
            flash("No students enrolled in this class.", "warning")
            return redirect(url_for("biometric.biometric_home"))

        pair = next((p for p in pairs if p["class_id"] == class_id and p["unit_id"] == unit_id), {})
        lesson_obj = next((l for l in LESSON_TIMES if l["value"] == lesson), {})

        session_id = f"{trainer_id[:8]}_{class_id[:8]}_{unit_id[:8]}_{int(datetime.now().timestamp())}"

        with _lock:
            _sessions[session_id] = {
                "trainer_id":    trainer_id,
                "trainer_name":  user.get("full_name", "Trainer"),
                "class_id":      class_id,
                "class_name":    pair.get("class_name", ""),
                "unit_id":       unit_id,
                "unit_code":     pair.get("unit_code", ""),
                "unit_name":     pair.get("unit_name", ""),
                "room":          room,
                "lesson":        lesson,
                "lesson_label":  lesson_obj.get("label", f"Lesson {lesson}"),
                "lesson_time":   lesson_obj.get("time", ""),
                "week":          int(week),
                "term":          int(term),
                "year":          int(year),
                "attendance_date": date.today().isoformat(),
                "students":      students,
                "status":        "active",
                "started_at":    datetime.now().isoformat(),
                "last_scan":     None,
            }

        write_audit_log("start_biometric_session",
                        target=f"class:{class_id},unit:{unit_id},room:{room}")
        return redirect(url_for("biometric.biometric_session", session_id=session_id))

    return render_template("trainer/biometric_attendance.html",
                           classes=classes,
                           pairs_json=pairs,
                           lesson_times=LESSON_TIMES,
                           current_year=current_year,
                           current_week=current_week)


# ── Live session page ─────────────────────────────────────────────────────────

@biometric_bp.route("/<session_id>")
@trainer_required
def biometric_session(session_id):
    user = current_user()
    with _lock:
        session = _sessions.get(session_id)
    if not session:
        flash("Session not found or expired.", "error")
        return redirect(url_for("biometric.biometric_home"))
    if session["trainer_id"] != user["id"]:
        flash("Unauthorised access.", "error")
        return redirect(url_for("biometric.biometric_home"))
    return render_template("trainer/biometric_session.html",
                           session_id=session_id,
                           session=session,
                           lesson_times=LESSON_TIMES)


# ── Polling endpoint (JS calls this every 2 s) ────────────────────────────────

@biometric_bp.route("/<session_id>/status")
@trainer_required
def session_status(session_id):
    user = current_user()
    with _lock:
        session = _sessions.get(session_id)
    if not session:
        return jsonify({"error": "not_found"}), 404
    if session["trainer_id"] != user["id"]:
        return jsonify({"error": "unauthorised"}), 403
    present = [s for s in session["students"] if s["status"] == "present"]
    absent  = [s for s in session["students"] if s["status"] != "present"]
    return jsonify({
        "session_status": session["status"],
        "present_count":  len(present),
        "absent_count":   len(absent),
        "total":          len(session["students"]),
        "last_scan":      session.get("last_scan"),
        "students": [
            {
                "id":           s["id"],
                "name":         s["name"],
                "admission_no": s["admission_no"],
                "status":       s["status"],
                "marked_manual": s.get("marked_manual", False),
            }
            for s in session["students"]
        ],
    })


# ── Manual override: mark one student ────────────────────────────────────────

@biometric_bp.route("/<session_id>/mark", methods=["POST"])
@trainer_required
def manual_mark(session_id):
    user = current_user()
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id", "")
    new_status = data.get("status", "")

    if new_status not in ("present", "absent"):
        return jsonify({"success": False, "error": "Invalid status"}), 400

    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return jsonify({"success": False, "error": "Session not found"}), 404
        if session["trainer_id"] != user["id"]:
            return jsonify({"success": False, "error": "Unauthorised"}), 403
        student = next((s for s in session["students"] if s["id"] == student_id), None)
        if not student:
            return jsonify({"success": False, "error": "Student not in session"}), 404
        student["status"] = new_status
        student["marked_manual"] = True

    return jsonify({"success": True, "student_name": student["name"], "status": new_status})


# ── Save attendance to database ───────────────────────────────────────────────

@biometric_bp.route("/<session_id>/save", methods=["POST"])
@trainer_required
def save_attendance(session_id):
    user = current_user()
    db   = get_service_client()

    with _lock:
        session = _sessions.get(session_id)

    if not session:
        return jsonify({"success": False, "error": "Session not found"}), 404
    if session["trainer_id"] != user["id"]:
        return jsonify({"success": False, "error": "Unauthorised"}), 403
    if session["status"] != "active":
        return jsonify({"success": False, "error": "Session already closed"}), 409

    try:
        records = []
        for s in session["students"]:
            records.append({
                "student_id":      s["id"],
                "unit_id":         session["unit_id"],
                "unit_code":       session["unit_code"],
                "trainer_id":      session["trainer_id"],
                "lesson":          session["lesson"],
                "week":            session["week"],
                "year":            session["year"],
                "term":            session["term"],
                "status":          s["status"],
                "attendance_date": session["attendance_date"],
            })

        db.table("attendance").insert(records).execute()

        with _lock:
            if session_id in _sessions:
                _sessions[session_id]["status"] = "saved"

        present = sum(1 for s in session["students"] if s["status"] == "present")
        absent  = len(session["students"]) - present

        write_audit_log("save_biometric_attendance",
                        target=f"class:{session['class_id']},unit:{session['unit_id']},week:{session['week']}")

        return jsonify({
            "success":       True,
            "present_count": present,
            "absent_count":  absent,
            "total":         len(session["students"]),
        })
    except Exception as exc:
        return jsonify({"success": False, "error": str(exc)}), 500


# ── Cancel session ────────────────────────────────────────────────────────────

@biometric_bp.route("/<session_id>/cancel", methods=["POST"])
@trainer_required
def cancel_session(session_id):
    user = current_user()
    with _lock:
        session = _sessions.get(session_id)
        if not session:
            return jsonify({"success": False, "error": "Session not found"}), 404
        if session["trainer_id"] != user["id"]:
            return jsonify({"success": False, "error": "Unauthorised"}), 403
        _sessions[session_id]["status"] = "cancelled"
    write_audit_log("cancel_biometric_session", target=f"session:{session_id}")
    return jsonify({"success": True})


# ── Fingerprint device API (called by sensor hardware) ───────────────────────

@biometric_bp.route("/api/scan", methods=["POST"])
def device_scan():
    """
    Called by the BioEntry W fingerprint sensor when a finger is placed.

    JSON body:
      { "biometric_id": "1234", "room": "Lab 1", "device_secret": "optional" }

    The sensor must be configured to POST to:
      https://<your-domain>/biometric/api/scan
    """
    secret = os.environ.get("BIOMETRIC_DEVICE_SECRET", "")
    data   = request.get_json(silent=True) or {}

    # Optional shared-secret auth
    if secret and data.get("device_secret") != secret:
        return jsonify({"status": "error", "message": "Unauthorised device"}), 401

    biometric_id = str(data.get("biometric_id") or data.get("fingerprint_id") or "").strip()
    room         = str(data.get("room") or "").strip()

    if not biometric_id:
        return jsonify({"status": "error", "message": "Missing biometric_id"}), 400

    scan_time = datetime.now().isoformat()

    # Find matching active session (prefer room match, fallback to any active)
    with _lock:
        matched_sid = None
        for sid, sess in _sessions.items():
            if sess["status"] != "active":
                continue
            if room and sess["room"].lower() == room.lower():
                matched_sid = sid
                break
        # Fallback: any active session if room not provided / not found
        if not matched_sid and not room:
            for sid, sess in _sessions.items():
                if sess["status"] == "active":
                    matched_sid = sid
                    break

        if not matched_sid:
            return jsonify({"status": "error", "message": "No active session for this room"}), 404

        session = _sessions[matched_sid]
        student = next((s for s in session["students"]
                        if s.get("biometric_id") and s["biometric_id"] == biometric_id), None)

        if not student:
            return jsonify({
                "status":  "error",
                "message": f"Fingerprint ID {biometric_id} not linked to any student in this class"
            }), 404

        if student["status"] == "present":
            return jsonify({
                "status":  "already_scanned",
                "message": f"{student['name']} already marked present",
                "student": student["name"],
            })

        student["status"] = "present"
        session["last_scan"] = {
            "student_id":   student["id"],
            "student_name": student["name"],
            "admission_no": student["admission_no"],
            "scan_time":    scan_time,
        }

    write_audit_log("biometric_scan",
                    target=f"student:{student['id']},room:{room},bio_id:{biometric_id}")

    return jsonify({
        "status":        "ok",
        "student_name":  student["name"],
        "admission_no":  student["admission_no"],
        "scan_time":     scan_time,
    })
