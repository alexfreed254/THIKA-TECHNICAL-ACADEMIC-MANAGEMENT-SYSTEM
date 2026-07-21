"""
TVET CDACC Competency Grading — single source of truth.

Marks Range   Grade                Code   Meaning
80-100%       Mastery              M      Performs with high mastery, accuracy,
                                          independence, consistency, excellence.
65-79%        Proficient           P      Strong competence, performs tasks
                                          effectively with minor improvements.
50-64%        Competent            C      Minimum required standard achieved.
0-49%         Not Yet Competent    NYC    Requires further training / reassessment.
CRNM          Course Requirement   CRNM   A required course/assessment requirement
              Not Met                     is unfulfilled, regardless of marks.
"""

CDACC_SCALE = (
    {"code": "M",   "label": "Mastery",           "min": 80, "max": 100,
     "desc": "Performs the competency with a high level of mastery, accuracy, "
             "independence, consistency, and excellence."},
    {"code": "P",   "label": "Proficient",        "min": 65, "max": 79,
     "desc": "Demonstrates strong competence and performs the required tasks "
             "effectively, with only minor areas for improvement."},
    {"code": "C",   "label": "Competent",         "min": 50, "max": 64,
     "desc": "Has achieved the minimum required standard and can perform the "
             "required competency to the expected standard."},
    {"code": "NYC", "label": "Not Yet Competent", "min": 0,  "max": 49,
     "desc": "Has not yet demonstrated the required level of competence and "
             "requires further training, practice, support, or reassessment."},
)

CRNM_CODE = "CRNM"
CRNM_LABEL = "Course Requirement Not Met"
CRNM_DESC = ("Has not fulfilled a required course or assessment requirement, "
             "regardless of the numerical marks.")

CDACC_LABELS = {b["code"]: b["label"] for b in CDACC_SCALE}
CDACC_LABELS[CRNM_CODE] = CRNM_LABEL

# Codes that count as a pass / meeting the standard
PASSING_CODES = frozenset({"M", "P", "C"})


def cdacc_code(pct):
    """Map a percentage (0-100) to a CDACC competency code."""
    if pct is None:
        return None
    if pct >= 80:
        return "M"
    if pct >= 65:
        return "P"
    if pct >= 50:
        return "C"
    return "NYC"


def cdacc_label(code):
    return CDACC_LABELS.get(code, "—")


def compute_grade(obtained, max_marks):
    """Return (percentage, cdacc_code) from raw marks. Safe on bad input."""
    try:
        pct = round(float(obtained) / float(max_marks) * 100, 1) if max_marks else 0.0
    except (TypeError, ValueError, ZeroDivisionError):
        pct = 0.0
    return pct, cdacc_code(pct)
