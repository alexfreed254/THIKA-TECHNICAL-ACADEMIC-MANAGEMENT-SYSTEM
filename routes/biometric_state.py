"""
biometric_state.py — Shared in-memory state for biometric operations.
Imported by both biometric_attendance.py and dept_admin.py.
"""
import threading

# Active fingerprint enrollment session
# Holds one pending enrollment at a time:
#   { student_id, student_name, dept_id, started_at, biometric_id, status }
active_enrollment: dict = {}
enrollment_lock = threading.Lock()
