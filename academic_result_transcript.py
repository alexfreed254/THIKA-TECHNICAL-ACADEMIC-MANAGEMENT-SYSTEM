"""
TTTI Academic Result Transcript PDF.

Matches the official Examinations Office transcript layout used from the
trainee Marks & Transcript download.
"""

from __future__ import annotations

import io
import os
from datetime import datetime


NAVY = "#1a3a5a"
BORDER = "#cbd5e1"
ROW_LINE = "#e2e8f0"
LIGHT = "#f8fafc"

# Formative types rolled into "Oral / CAT"
ORAL_CAT_TYPES = {"ORAL", "CA", "WRITTEN", "IA", "CAT", "THEORY", "OTHER"}
PRACTICAL_TYPES = {"PRACTICAL", "PRACT"}


def _resolve_logo_path() -> str | None:
    base = os.path.dirname(os.path.abspath(__file__))
    for rel in (
        os.path.join("static", "assets", "THIKATTILOGO.jpg"),
        os.path.join("frontend", "public", "ttti-logo.jpg"),
        os.path.join("static", "assets", "KENYACOATOFARMS.png"),
    ):
        path = os.path.join(base, rel)
        if os.path.exists(path):
            return path
    return None


def _fmt_score(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.1f}"
    except (TypeError, ValueError):
        return "—"


def _type_bucket(assessment_type: str) -> str:
    t = (assessment_type or "").upper().strip()
    if t in PRACTICAL_TYPES or "PRACT" in t:
        return "practical"
    return "oral_cat"


def _avg_pct(rows: list) -> float | None:
    entered = [r for r in rows if r.get("marks_obtained") is not None]
    if not entered:
        return None
    total_pct = 0.0
    for r in entered:
        mx = float(r.get("max_marks") or 100) or 100.0
        total_pct += float(r["marks_obtained"]) / mx * 100.0
    return round(total_pct / len(entered), 1)


def build_academic_result_transcript_pdf(
    student: dict,
    course_name: str,
    course_code: str,
    department_name: str,
    class_name: str,
    year: str,
    term: str,
    by_unit: dict,
) -> bytes:
    """
    Build transcript PDF bytes.

    by_unit: OrderedDict[unit_id -> {"unit": {...}, "rows": [assessment mark dicts]}]
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage,
    )

    navy = colors.HexColor(NAVY)
    border = colors.HexColor(BORDER)
    row_line = colors.HexColor(ROW_LINE)
    light = colors.HexColor(LIGHT)

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=12 * mm, bottomMargin=12 * mm,
    )
    W = A4[0] - 32 * mm

    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    inst = S("inst", fontName="Helvetica-Bold", fontSize=14, textColor=navy,
             alignment=TA_CENTER, leading=17, spaceAfter=2)
    office = S("office", fontName="Helvetica-Bold", fontSize=10, textColor=navy,
               alignment=TA_CENTER, leading=12, spaceAfter=1)
    title = S("title", fontName="Helvetica-Bold", fontSize=11, textColor=navy,
              alignment=TA_CENTER, leading=13, spaceAfter=2)
    year_s = S("year", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#334155"),
               alignment=TA_CENTER, leading=11, spaceAfter=0)
    lbl = S("lbl", fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor("#0f172a"), leading=12)
    val = S("val", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#1e293b"), leading=12)
    th = S("th", fontName="Helvetica-Bold", fontSize=7.5, textColor=colors.white,
           alignment=TA_CENTER, leading=9)
    th_l = S("thl", fontName="Helvetica-Bold", fontSize=7.5, textColor=colors.white,
             alignment=TA_LEFT, leading=9)
    td = S("td", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#0f172a"),
           alignment=TA_CENTER, leading=10)
    td_l = S("tdl", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#0f172a"),
             alignment=TA_LEFT, leading=10)
    legend = S("leg", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#334155"),
               alignment=TA_CENTER, leading=10)
    verify = S("ver", fontName="Helvetica-Bold", fontSize=10, textColor=navy,
               alignment=TA_LEFT, leading=12, spaceAfter=8)
    sig_h = S("sigh", fontName="Helvetica-Bold", fontSize=8.5, textColor=navy,
              alignment=TA_CENTER, leading=11, spaceAfter=6)
    sig_l = S("sigl", fontName="Helvetica", fontSize=8, textColor=colors.HexColor("#334155"),
              alignment=TA_CENTER, leading=12)
    foot = S("foot", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#64748b"),
             alignment=TA_CENTER, leading=9)

    story = []

    # ── Header (centered logo + titles) ──────────────────────────────────────
    logo_path = _resolve_logo_path()
    if logo_path:
        try:
            img = RLImage(logo_path, width=22 * mm, height=22 * mm)
            wrap = Table([[img]], colWidths=[W])
            wrap.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(wrap)
        except Exception:
            pass

    story.append(Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", inst))
    story.append(Paragraph("EXAMINATIONS OFFICE", office))
    story.append(Paragraph("ACADEMIC RESULT TRANSCRIPT", title))
    year_line = f"Academic Year: {year}"
    if term:
        year_line += f"   ·   Term {term}"
    story.append(Paragraph(year_line, year_s))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=2.0, color=navy, spaceBefore=2, spaceAfter=8))

    # ── Student info (two columns) ───────────────────────────────────────────
    left = [
        [Paragraph("Student Name:", lbl), Paragraph(student.get("full_name") or "—", val)],
        [Paragraph("Course Name:", lbl), Paragraph(course_name or "—", val)],
        [Paragraph("Department:", lbl), Paragraph(department_name or "—", val)],
    ]
    right = [
        [Paragraph("Admission No:", lbl), Paragraph(student.get("admission_no") or "—", val)],
        [Paragraph("Course Code:", lbl), Paragraph(course_code or "—", val)],
        [Paragraph("Class / Cohort:", lbl), Paragraph(class_name or "—", val)],
    ]
    left_t = Table(left, colWidths=[32 * mm, W * 0.5 - 32 * mm])
    right_t = Table(right, colWidths=[32 * mm, W * 0.5 - 32 * mm])
    info_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])
    left_t.setStyle(info_style)
    right_t.setStyle(info_style)
    info = Table([[left_t, right_t]], colWidths=[W * 0.52, W * 0.48])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.7, color=border, spaceBefore=2, spaceAfter=8))

    # ── Results table ────────────────────────────────────────────────────────
    headers = [
        Paragraph("#", th),
        Paragraph("Unit Code", th),
        Paragraph("Unit Name", th_l),
        Paragraph("Term", th),
        Paragraph("Oral / CAT", th),
        Paragraph("Practical", th),
        Paragraph("Total / Score", th),
        Paragraph("Grade", th),
    ]
    rows = [headers]

    if not by_unit:
        empty = [[Paragraph("No assessment records found for the selected period.", td_l)]]
        empty_t = Table(empty, colWidths=[W])
        empty_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), light),
            ("BOX", (0, 0), (-1, -1), 0.6, border),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(empty_t)
    else:
        for i, (_uid, ud) in enumerate(by_unit.items(), start=1):
            unit = ud.get("unit") or {}
            arows = ud.get("rows") or []
            oral_rows = [r for r in arows if _type_bucket(r.get("assessment_type", "")) == "oral_cat"]
            prac_rows = [r for r in arows if _type_bucket(r.get("assessment_type", "")) == "practical"]

            oral_pct = _avg_pct(oral_rows)
            prac_pct = _avg_pct(prac_rows)

            entered = [r for r in arows if r.get("marks_obtained") is not None]
            if entered:
                u_obt = round(sum(float(r["marks_obtained"]) for r in entered), 1)
                u_mx = round(sum(float(r.get("max_marks") or 100) for r in entered), 1)
                u_pct = round(u_obt / u_mx * 100, 1) if u_mx else 0.0
                grade = ("M" if u_pct >= 80 else "P" if u_pct >= 65
                         else "C" if u_pct >= 50 else "NYC")
                total_txt = f"{u_obt:.1f} / {u_pct:.1f}%"
            else:
                grade = "—"
                total_txt = "—"

            terms = sorted({str(r.get("term")) for r in arows if r.get("term") not in (None, "")})
            if term:
                term_txt = f"T{term}"
            elif terms:
                term_txt = ", ".join(f"T{t}" for t in terms)
            else:
                term_txt = "—"

            rows.append([
                Paragraph(str(i), td),
                Paragraph(unit.get("code") or "—", td),
                Paragraph(unit.get("name") or "—", td_l),
                Paragraph(term_txt, td),
                Paragraph(_fmt_score(oral_pct), td),
                Paragraph(_fmt_score(prac_pct), td),
                Paragraph(total_txt, td),
                Paragraph(grade, ParagraphStyle(
                    f"g{i}", parent=td, fontName="Helvetica-Bold"
                )),
            ])

        col_w = [
            8 * mm,   # #
            28 * mm,  # code
            W - 8 * mm - 28 * mm - 12 * mm - 20 * mm - 20 * mm - 28 * mm - 16 * mm,  # name
            12 * mm,  # term
            20 * mm,  # oral
            20 * mm,  # practical
            28 * mm,  # total
            16 * mm,  # grade
        ]
        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        style_cmds = [
            ("BACKGROUND", (0, 0), (-1, 0), navy),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 1), (-1, -2), 0.4, row_line),
            ("LINEBELOW", (0, -1), (-1, -1), 0.6, border),
            ("BOX", (0, 0), (-1, -1), 0.7, navy),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, navy),
        ]
        for ri in range(1, len(rows)):
            if ri % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, ri), (-1, ri), light))
        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)

    story.append(Spacer(1, 10))

    # ── Grading legend ───────────────────────────────────────────────────────
    legend_row = [[
        Paragraph("<b>M — Mastery</b><br/>80–100%", legend),
        Paragraph("<b>P — Proficient</b><br/>65–79%", legend),
        Paragraph("<b>C — Competent</b><br/>50–64%", legend),
        Paragraph("<b>NYC — Not Yet Competent</b><br/>0–49%", legend),
    ]]
    leg = Table(legend_row, colWidths=[W / 4] * 4)
    leg.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), light),
        ("BOX", (0, 0), (-1, -1), 0.6, border),
        ("INNERGRID", (0, 0), (-1, -1), 0.4, border),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(leg)
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=0.7, color=border, spaceBefore=2, spaceAfter=10))

    # ── Official verification (3 columns) ────────────────────────────────────
    story.append(Paragraph("OFFICIAL VERIFICATION", verify))

    def sig_block(heading: str):
        return [
            Paragraph(heading, sig_h),
            Paragraph("Name: ____________________", sig_l),
            Paragraph("Signature: ____________________", sig_l),
            Paragraph("Date: ____________________", sig_l),
        ]

    auth = Table(
        [[sig_block("Head of Department"),
          sig_block("Examinations Officer"),
          sig_block("Registrar / Principal")]],
        colWidths=[W / 3] * 3,
    )
    auth.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(auth)

    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=0.5, color=border, spaceBefore=2, spaceAfter=4))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %B %Y  %H:%M')}  ·  "
        f"{student.get('full_name') or '—'}  ·  Adm: {student.get('admission_no') or '—'}",
        foot,
    ))

    # Light diagonal watermark
    adm = student.get("admission_no") or ""

    def _watermark(canvas_obj, _doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 40)
        canvas_obj.setFillColorRGB(0.78, 0.82, 0.86, alpha=0.16)
        canvas_obj.translate(A4[0] / 2, A4[1] / 2)
        canvas_obj.rotate(45)
        canvas_obj.drawCentredString(0, 18, "TTTI OFFICIAL DOCUMENT")
        if adm:
            canvas_obj.drawCentredString(0, -28, adm)
        canvas_obj.restoreState()

    pdf.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    return buf.getvalue()
