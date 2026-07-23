"""
TTTI Academic Result Transcript PDF.

Trainee Marks & Transcript download — shows each Oral, Practical and Written
assessment mark (as entered by the trainer) in separate columns, plus total
score and grade.
"""

from __future__ import annotations

import os
from collections import Counter
from datetime import datetime
from io import BytesIO


NAVY = "#1a3a5a"
BORDER = "#cbd5e1"
ROW_LINE = "#e2e8f0"
LIGHT = "#f8fafc"
ORAL_BG = "#1e5a9f"
PRAC_BG = "#c2410c"
WRIT_BG = "#5b21b6"


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


def _bucket(assessment_type: str) -> str:
    """Map formative type → oral | practical | written (trainer: Oral/Practical/Theory)."""
    t = (assessment_type or "").upper().strip()
    if t in ("ORAL",):
        return "oral"
    if t in ("PRACTICAL", "PRACT") or "PRACT" in t:
        return "practical"
    # Theory / Written / CA / IA / CAT / anything else → Written column group
    return "written"


def _mark_cell(row: dict | None) -> str:
    """Format a single trainer-entered mark as obtained/max."""
    if not row or row.get("marks_obtained") is None:
        return "—"
    try:
        obt = float(row["marks_obtained"])
        mx = float(row.get("max_marks") or 100)
        # Show whole numbers cleanly when possible
        obt_s = f"{obt:.0f}" if obt == int(obt) else f"{obt:.1f}"
        mx_s = f"{mx:.0f}" if mx == int(mx) else f"{mx:.1f}"
        return f"{obt_s}/{mx_s}"
    except (TypeError, ValueError):
        return "—"


def _split_by_type(arows: list) -> dict:
    out = {"oral": [], "practical": [], "written": []}
    for r in arows:
        out[_bucket(r.get("assessment_type", ""))].append(r)
    return out


def _slot_labels(by_unit: dict, bucket: str, count: int, fallback: str) -> list[str]:
    """Best assessment name for each column index across units."""
    labels = []
    for i in range(count):
        names = []
        for ud in by_unit.values():
            parts = _split_by_type(ud.get("rows") or [])[bucket]
            if i < len(parts):
                n = (parts[i].get("assessment_name") or "").strip()
                if n:
                    names.append(n)
        if names:
            labels.append(Counter(names).most_common(1)[0][0])
        else:
            labels.append(f"{fallback} {i + 1}")
    return labels


def build_marks_transcript_view(units_data: list) -> dict:
    """
    Build the same Oral / Practical / Written column layout used by the
    downloadable Academic Result Transcript, for on-screen Marks & Transcript.

    units_data items need: unit, term, assessments[], total_obt, total_max, pct,
    final_grade, has_marks.
    """
    from collections import OrderedDict

    by_unit = OrderedDict()
    for i, ud in enumerate(units_data or []):
        by_unit[i] = {
            "unit": ud.get("unit") or {},
            "rows": ud.get("assessments") or [],
        }

    max_oral = max_prac = max_writ = 0
    for ud in by_unit.values():
        parts = _split_by_type(ud.get("rows") or [])
        max_oral = max(max_oral, len(parts["oral"]))
        max_prac = max(max_prac, len(parts["practical"]))
        max_writ = max(max_writ, len(parts["written"]))

    if by_unit and max_oral + max_prac + max_writ == 0:
        max_oral = max_prac = max_writ = 1

    oral_labels = _slot_labels(by_unit, "oral", max_oral, "Oral") if max_oral else []
    practical_labels = _slot_labels(by_unit, "practical", max_prac, "Practical") if max_prac else []
    written_labels = _slot_labels(by_unit, "written", max_writ, "Written") if max_writ else []

    rows = []
    for ud in (units_data or []):
        parts = _split_by_type(ud.get("assessments") or [])
        oral_cells = [
            _mark_cell(parts["oral"][j] if j < len(parts["oral"]) else None)
            for j in range(max_oral)
        ]
        practical_cells = [
            _mark_cell(parts["practical"][j] if j < len(parts["practical"]) else None)
            for j in range(max_prac)
        ]
        written_cells = [
            _mark_cell(parts["written"][j] if j < len(parts["written"]) else None)
            for j in range(max_writ)
        ]
        rows.append({
            **ud,
            "oral_cells": oral_cells,
            "practical_cells": practical_cells,
            "written_cells": written_cells,
        })

    return {
        "oral_labels": oral_labels,
        "practical_labels": practical_labels,
        "written_labels": written_labels,
        "max_oral": max_oral,
        "max_practical": max_prac,
        "max_written": max_writ,
        "units_rows": rows,
    }


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
    Each row should include assessment_name, assessment_type, marks_obtained, max_marks, term.
    """
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage,
    )

    # Column counts from actual assessments present (no empty groups)
    max_oral = max_prac = max_writ = 0
    for ud in (by_unit or {}).values():
        parts = _split_by_type(ud.get("rows") or [])
        max_oral = max(max_oral, len(parts["oral"]))
        max_prac = max(max_prac, len(parts["practical"]))
        max_writ = max(max_writ, len(parts["written"]))

    n_assess = max_oral + max_prac + max_writ
    # Ensure table still builds if units exist but marks pending (show placeholder cols)
    if by_unit and n_assess == 0:
        max_oral = max_prac = max_writ = 1
        n_assess = 3

    page = landscape(A4) if n_assess > 5 else A4

    navy = colors.HexColor(NAVY)
    border = colors.HexColor(BORDER)
    row_line = colors.HexColor(ROW_LINE)
    light = colors.HexColor(LIGHT)
    oral_bg = colors.HexColor(ORAL_BG)
    prac_bg = colors.HexColor(PRAC_BG)
    writ_bg = colors.HexColor(WRIT_BG)

    buf = BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=page,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=10 * mm,
    )
    W = page[0] - 24 * mm

    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    inst = S("inst", fontName="Helvetica-Bold", fontSize=13, textColor=navy,
             alignment=TA_CENTER, leading=16, spaceAfter=2)
    office = S("office", fontName="Helvetica-Bold", fontSize=9.5, textColor=navy,
               alignment=TA_CENTER, leading=11, spaceAfter=1)
    title = S("title", fontName="Helvetica-Bold", fontSize=10.5, textColor=navy,
              alignment=TA_CENTER, leading=12, spaceAfter=2)
    year_s = S("year", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#334155"),
               alignment=TA_CENTER, leading=10)
    lbl = S("lbl", fontName="Helvetica-Bold", fontSize=8.5, textColor=colors.HexColor("#0f172a"), leading=11)
    val = S("val", fontName="Helvetica", fontSize=8.5, textColor=colors.HexColor("#1e293b"), leading=11)
    th = S("th", fontName="Helvetica-Bold", fontSize=7, textColor=colors.white,
           alignment=TA_CENTER, leading=8)
    th_sm = S("thsm", fontName="Helvetica-Bold", fontSize=6.5, textColor=colors.white,
              alignment=TA_CENTER, leading=8)
    th_l = S("thl", fontName="Helvetica-Bold", fontSize=7, textColor=colors.white,
             alignment=TA_LEFT, leading=8)
    td = S("td", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#0f172a"),
           alignment=TA_CENTER, leading=9)
    td_l = S("tdl", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#0f172a"),
             alignment=TA_LEFT, leading=9)
    legend = S("leg", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#334155"),
               alignment=TA_CENTER, leading=9)
    verify = S("ver", fontName="Helvetica-Bold", fontSize=9.5, textColor=navy, leading=11, spaceAfter=6)
    sig_h = S("sigh", fontName="Helvetica-Bold", fontSize=8, textColor=navy,
              alignment=TA_CENTER, leading=10, spaceAfter=4)
    sig_l = S("sigl", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#334155"),
              alignment=TA_CENTER, leading=11)
    foot = S("foot", fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#64748b"),
             alignment=TA_CENTER, leading=9)

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    logo_path = _resolve_logo_path()
    if logo_path:
        try:
            img = RLImage(logo_path, width=18 * mm, height=18 * mm)
            wrap = Table([[img]], colWidths=[W])
            wrap.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
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
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=2.0, color=navy, spaceBefore=1, spaceAfter=6))

    # ── Student info ─────────────────────────────────────────────────────────
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
    info_style = TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ])
    left_t = Table(left, colWidths=[30 * mm, W * 0.5 - 30 * mm])
    right_t = Table(right, colWidths=[30 * mm, W * 0.5 - 30 * mm])
    left_t.setStyle(info_style)
    right_t.setStyle(info_style)
    info = Table([[left_t, right_t]], colWidths=[W * 0.52, W * 0.48])
    info.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(info)
    story.append(Spacer(1, 5))
    story.append(HRFlowable(width="100%", thickness=0.7, color=border, spaceBefore=1, spaceAfter=6))

    # ── Results table (Oral / Practical / Written columns) ───────────────────
    if not by_unit:
        empty = Table(
            [[Paragraph("No assessment records found for the selected period.", td_l)]],
            colWidths=[W],
        )
        empty.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), light),
            ("BOX", (0, 0), (-1, -1), 0.6, border),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(empty)
    else:
        oral_labels = _slot_labels(by_unit, "oral", max_oral, "Oral") if max_oral else []
        prac_labels = _slot_labels(by_unit, "practical", max_prac, "Practical") if max_prac else []
        writ_labels = _slot_labels(by_unit, "written", max_writ, "Written") if max_writ else []

        # Row 1 — group headers
        hdr1 = [
            Paragraph("#", th), Paragraph("Unit Code", th),
            Paragraph("Unit Name", th_l), Paragraph("Term", th),
        ]
        if max_oral:
            hdr1 += [Paragraph("ORAL ASSESSMENTS", th)] + [Paragraph("", th)] * (max_oral - 1)
        if max_prac:
            hdr1 += [Paragraph("PRACTICAL ASSESSMENTS", th)] + [Paragraph("", th)] * (max_prac - 1)
        if max_writ:
            hdr1 += [Paragraph("WRITTEN ASSESSMENTS", th)] + [Paragraph("", th)] * (max_writ - 1)
        hdr1 += [Paragraph("Total", th), Paragraph("Score %", th), Paragraph("Grade", th)]

        # Row 2 — individual assessment names
        hdr2 = [Paragraph("", th_sm)] * 4
        hdr2 += [Paragraph(n, th_sm) for n in oral_labels]
        hdr2 += [Paragraph(n, th_sm) for n in prac_labels]
        hdr2 += [Paragraph(n, th_sm) for n in writ_labels]
        hdr2 += [Paragraph("Σ marks", th_sm), Paragraph("Avg", th_sm), Paragraph("", th_sm)]

        data = [hdr1, hdr2]

        for i, (_uid, ud) in enumerate(by_unit.items(), start=1):
            unit = ud.get("unit") or {}
            arows = ud.get("rows") or []
            parts = _split_by_type(arows)

            entered = [r for r in arows if r.get("marks_obtained") is not None]
            if entered:
                u_obt = round(sum(float(r["marks_obtained"]) for r in entered), 1)
                u_mx = round(sum(float(r.get("max_marks") or 100) for r in entered), 1)
                u_pct = round(u_obt / u_mx * 100, 1) if u_mx else 0.0
                grade = ("M" if u_pct >= 80 else "P" if u_pct >= 65
                         else "C" if u_pct >= 50 else "NYC")
                if u_obt == int(u_obt) and u_mx == int(u_mx):
                    total_txt = f"{int(u_obt)}/{int(u_mx)}"
                else:
                    total_txt = f"{u_obt}/{u_mx}"
                pct_txt = f"{u_pct:.1f}%"
            else:
                grade = "—"
                total_txt = "—"
                pct_txt = "—"

            terms = sorted({str(r.get("term")) for r in arows if r.get("term") not in (None, "")})
            if term:
                term_txt = f"T{term}"
            elif terms:
                term_txt = ", ".join(f"T{t}" for t in terms)
            else:
                term_txt = "—"

            mark_cells = []
            for j in range(max_oral):
                mark_cells.append(Paragraph(
                    _mark_cell(parts["oral"][j] if j < len(parts["oral"]) else None), td))
            for j in range(max_prac):
                mark_cells.append(Paragraph(
                    _mark_cell(parts["practical"][j] if j < len(parts["practical"]) else None), td))
            for j in range(max_writ):
                mark_cells.append(Paragraph(
                    _mark_cell(parts["written"][j] if j < len(parts["written"]) else None), td))

            data.append(
                [Paragraph(str(i), td),
                 Paragraph(unit.get("code") or "—", td),
                 Paragraph(unit.get("name") or "—", td_l),
                 Paragraph(term_txt, td)]
                + mark_cells
                + [Paragraph(total_txt, ParagraphStyle(f"tot{i}", parent=td, fontName="Helvetica-Bold")),
                   Paragraph(pct_txt, ParagraphStyle(f"pct{i}", parent=td, fontName="Helvetica-Bold")),
                   Paragraph(grade, ParagraphStyle(f"g{i}", parent=td, fontName="Helvetica-Bold"))]
            )

        fixed = 7 * mm + 22 * mm + 12 * mm + 18 * mm + 16 * mm + 12 * mm
        name_min = 28 * mm
        assess_budget = max(W - fixed - name_min, max(n_assess, 1) * 14 * mm)
        assess_w = assess_budget / max(n_assess, 1)
        name_w = W - fixed - (assess_budget if n_assess else 0)
        col_w = [7 * mm, 22 * mm, name_w, 12 * mm]
        if n_assess:
            col_w += [assess_w] * n_assess
        col_w += [18 * mm, 16 * mm, 12 * mm]

        style_cmds = [
            ("BACKGROUND", (0, 0), (3, 1), navy),
            ("BACKGROUND", (4 + n_assess, 0), (-1, 1), navy),
            ("SPAN", (0, 0), (0, 1)),
            ("SPAN", (1, 0), (1, 1)),
            ("SPAN", (2, 0), (2, 1)),
            ("SPAN", (3, 0), (3, 1)),
            ("SPAN", (-1, 0), (-1, 1)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, 1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("GRID", (0, 0), (-1, -1), 0.4, border),
            ("BOX", (0, 0), (-1, -1), 0.8, navy),
            ("LINEBELOW", (0, 1), (-1, 1), 0.8, navy),
        ]

        col = 4
        if max_oral:
            style_cmds.append(("BACKGROUND", (col, 0), (col + max_oral - 1, 1), oral_bg))
            if max_oral > 1:
                style_cmds.append(("SPAN", (col, 0), (col + max_oral - 1, 0)))
            col += max_oral
        if max_prac:
            style_cmds.append(("BACKGROUND", (col, 0), (col + max_prac - 1, 1), prac_bg))
            if max_prac > 1:
                style_cmds.append(("SPAN", (col, 0), (col + max_prac - 1, 0)))
            col += max_prac
        if max_writ:
            style_cmds.append(("BACKGROUND", (col, 0), (col + max_writ - 1, 1), writ_bg))
            if max_writ > 1:
                style_cmds.append(("SPAN", (col, 0), (col + max_writ - 1, 0)))

        for ri in range(2, len(data)):
            if ri % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, ri), (-1, ri), light))
            style_cmds.append(("LINEBELOW", (0, ri), (-1, ri), 0.35, row_line))

        tbl = Table(data, colWidths=col_w, repeatRows=2)
        tbl.setStyle(TableStyle(style_cmds))
        story.append(tbl)

    story.append(Spacer(1, 8))

    # ── Legend ───────────────────────────────────────────────────────────────
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
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(leg)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.7, color=border, spaceBefore=2, spaceAfter=8))

    # ── Official verification ────────────────────────────────────────────────
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
          sig_block("Chief Principal")]],
        colWidths=[W / 3] * 3,
    )
    auth.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(auth)
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=0.5, color=border, spaceBefore=2, spaceAfter=3))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %B %Y  %H:%M')}  ·  "
        f"{student.get('full_name') or '—'}  ·  Adm: {student.get('admission_no') or '—'}  ·  "
        f"Marks shown as obtained/max as entered by trainer",
        foot,
    ))

    adm = student.get("admission_no") or ""

    def _watermark(canvas_obj, _doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 36)
        canvas_obj.setFillColorRGB(0.78, 0.82, 0.86, alpha=0.14)
        canvas_obj.translate(page[0] / 2, page[1] / 2)
        canvas_obj.rotate(45)
        canvas_obj.drawCentredString(0, 14, "TTTI OFFICIAL DOCUMENT")
        if adm:
            canvas_obj.drawCentredString(0, -24, adm)
        canvas_obj.restoreState()

    pdf.build(story, onFirstPage=_watermark, onLaterPages=_watermark)
    return buf.getvalue()
