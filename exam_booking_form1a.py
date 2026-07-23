"""
TTTI Regular Candidate Assessment Registration Form – 1A (PDF).

Layout matches the official printed institutional form:
header + motto, instructions/attachments boxes, candidate details grid,
units table, departmental clearance, gold-bordered authorization strip.
"""

from __future__ import annotations

import io
import os
from datetime import datetime


NAVY = "#0F2744"
LABEL_BLUE = "#BDD7EE"
GOLD = "#C9A227"
LIGHT_GOLD = "#F5E6B8"
BORDER = "#1A3A5C"


def _resolve_logo_path() -> str | None:
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "static", "assets", "THIKATTILOGO.jpg"),
        os.path.join(base, "frontend", "public", "ttti-logo.jpg"),
        os.path.join(base, "static", "assets", "KENYACOATOFARMS.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def build_exam_booking_form1a_pdf(
    student: dict,
    course_name: str,
    course_code: str,
    department_name: str,
    units_data: list,
    serial_number: str,
    year: str,
    series: str,
    term: str,
    form_data: dict | None = None,
    documents: dict | None = None,
    storage_client=None,
) -> bytes:
    """Generate Form 1A PDF bytes (optionally append supporting document pages)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch, mm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage, PageBreak,
    )
    from PIL import Image as PILImage

    fd = form_data or {}
    navy = colors.HexColor(NAVY)
    label_bg = colors.HexColor(LABEL_BLUE)
    gold = colors.HexColor(GOLD)
    light_gold = colors.HexColor(LIGHT_GOLD)
    border = colors.HexColor(BORDER)

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    W = A4[0] - 24 * mm

    base = getSampleStyleSheet()

    def S(name, **kw):
        return ParagraphStyle(name, parent=base["Normal"], **kw)

    inst_title = S("inst", fontName="Helvetica-Bold", fontSize=13, textColor=navy,
                   alignment=TA_CENTER, leading=16, spaceAfter=0)
    motto = S("motto", fontName="Helvetica-Oblique", fontSize=9, textColor=gold,
              alignment=TA_CENTER, leading=11, spaceAfter=2)
    form_title = S("ftitle", fontName="Helvetica-Bold", fontSize=10.5, textColor=colors.black,
                   alignment=TA_CENTER, leading=13, spaceAfter=0)
    meta = S("meta", fontName="Helvetica", fontSize=8, textColor=colors.black, leading=10)
    box_h = S("boxh", fontName="Helvetica-Bold", fontSize=8.5, textColor=navy, leading=11, spaceAfter=3)
    box_b = S("boxb", fontName="Helvetica", fontSize=7.5, textColor=colors.HexColor("#1e293b"), leading=10)
    sect = S("sect", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, leading=11)
    lbl = S("lbl", fontName="Helvetica-Bold", fontSize=7.5, textColor=navy, leading=9)
    val = S("val", fontName="Helvetica", fontSize=8, textColor=colors.black, leading=10)
    th = S("th", fontName="Helvetica-Bold", fontSize=7.5, textColor=colors.white,
           alignment=TA_CENTER, leading=9)
    td = S("td", fontName="Helvetica", fontSize=8, textColor=colors.black, leading=10)
    td_c = S("tdc", fontName="Helvetica", fontSize=8, textColor=colors.black,
             alignment=TA_CENTER, leading=10)
    auth_h = S("authh", fontName="Helvetica-Bold", fontSize=8, textColor=navy,
               alignment=TA_CENTER, leading=10, spaceAfter=4)
    auth_s = S("auths", fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#334155"),
               alignment=TA_CENTER, leading=9)
    foot = S("foot", fontName="Helvetica", fontSize=7, textColor=colors.HexColor("#64748b"), leading=9)

    story = []

    # ── Header ───────────────────────────────────────────────────────────────
    logo_path = _resolve_logo_path()
    logo_cell = Paragraph("", meta)
    if logo_path:
        try:
            logo_cell = RLImage(logo_path, width=0.78 * inch, height=0.78 * inch)
        except Exception:
            pass

    header_right = [
        Paragraph("THIKA TECHNICAL TRAINING INSTITUTE", inst_title),
        Paragraph('"Pride in Technology"', motto),
    ]
    hdr = Table([[logo_cell, header_right]], colWidths=[0.95 * inch, W - 0.95 * inch])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 4))

    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#64748b"),
                            dash=(2, 2), spaceBefore=1, spaceAfter=2))
    story.append(Paragraph("REGULAR CANDIDATE ASSESSMENT REGISTRATION FORM – 1A", form_title))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#64748b"),
                            dash=(2, 2), spaceBefore=2, spaceAfter=4))

    series_label = {"1": "MARCH", "2": "JULY", "3": "NOVEMBER"}.get(str(series), f"Series {series}")
    term_label = f"Term {term}" if str(term) and not str(term).lower().startswith("term") else str(term or "")
    exam_meta = f"Exam Year: {year}  |  Series: {series_label}  |  Term: {term_label}"

    meta_tbl = Table(
        [[
            Paragraph("Form Code: TTTI/EXAMS/CDACC/REG/1A", meta),
            Paragraph(f"<u>{exam_meta}</u>", ParagraphStyle(
                "metar", parent=meta, alignment=TA_RIGHT, fontName="Helvetica-Bold"
            )),
        ]],
        colWidths=[W * 0.42, W * 0.58],
    )
    meta_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(meta_tbl)
    story.append(HRFlowable(width="100%", thickness=2.2, color=navy, spaceBefore=2, spaceAfter=6))

    # ── Instructions + Attachments side by side ──────────────────────────────
    instr_lines = [
        Paragraph("INSTRUCTIONS", box_h),
        Paragraph("• Register on the student portal before filling this form.", box_b),
        Paragraph("• Attach all required documents listed.", box_b),
        Paragraph("• Submit to the departmental HOD before the deadline.", box_b),
    ]
    attach_lines = [
        Paragraph("REQUIRED ATTACHMENTS", box_h),
        Paragraph("[ ]  Copy of National ID / Passport", box_b),
        Paragraph("[ ]  Copy of Birth Certificate", box_b),
        Paragraph("[ ]  KCSE Certificate / Previous Module Result Slip", box_b),
        Paragraph("[ ]  Fee Statement showing exam fee payment", box_b),
    ]

    box_style = TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, navy),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ])
    half = (W - 6) / 2
    left_box = Table([[instr_lines]], colWidths=[half])
    left_box.setStyle(box_style)
    right_box = Table([[attach_lines]], colWidths=[half])
    right_box.setStyle(box_style)
    boxes = Table([[left_box, right_box]], colWidths=[half + 3, half + 3])
    boxes.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 3),
        ("LEFTPADDING", (1, 0), (1, 0), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(boxes)
    story.append(Spacer(1, 8))

    def section_bar(text: str):
        t = Table([[Paragraph(text, sect)]], colWidths=[W])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), navy),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        return t

    def r4(a, b, c, d):
        return [
            Paragraph(a, lbl), Paragraph(str(b or "—"), val),
            Paragraph(c, lbl), Paragraph(str(d or "—"), val),
        ]

    def grid_style():
        return TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.6, border),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 0), (0, -1), label_bg),
            ("BACKGROUND", (2, 0), (2, -1), label_bg),
        ])

    # ── SECTION 1 ────────────────────────────────────────────────────────────
    story.append(section_bar("SECTION 1: CANDIDATE DETAILS"))

    dob = fd.get("date_of_birth") or student.get("date_of_birth") or ""
    if dob and len(str(dob)) >= 10:
        try:
            dob = datetime.strptime(str(dob)[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
        except Exception:
            pass

    full_name = fd.get("full_name") or student.get("full_name") or ""
    gender = fd.get("gender") or student.get("gender") or ""
    mobile = fd.get("mobile_number") or student.get("mobile_number") or ""
    email = student.get("email") or ""
    nid = fd.get("national_id_no") or student.get("national_id_no") or ""
    module = fd.get("module_level") or student.get("level") or "N/A"
    pwd = fd.get("pwd_status") or student.get("pwd_status") or "N/A"

    cw4 = [W * 0.22, W * 0.28, W * 0.22, W * 0.28]
    detail_rows = [
        r4("Full Name (as per ID):", full_name, "Admission Number:", student.get("admission_no", "")),
        r4("Gender:", gender, "Date of Birth:", dob),
        r4("Mobile Number:", mobile, "Email Address:", email),
        r4("National ID / Birth Cert No.:", nid, "Course Code:", course_code),
    ]
    d1 = Table(detail_rows, colWidths=cw4)
    d1.setStyle(grid_style())
    story.append(d1)

    course_row = [[Paragraph("Course Name (see overleaf):", lbl), Paragraph(course_name or "—", val)]]
    d2 = Table(course_row, colWidths=[W * 0.28, W * 0.72])
    d2.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, border),
        ("BACKGROUND", (0, 0), (0, 0), label_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(d2)

    detail_rows2 = [
        r4("Module / Level / TEP:", module, "PWD Status:", pwd),
        r4("Exam Year:", year, "Series / Term:", f"{series_label} / {term_label}"),
    ]
    d3 = Table(detail_rows2, colWidths=cw4)
    d3.setStyle(grid_style())
    story.append(d3)
    story.append(Spacer(1, 8))

    # ── SECTION 2 ────────────────────────────────────────────────────────────
    story.append(section_bar("SECTION 2: UNITS OF COMPETENCY"))

    u_header = [
        Paragraph("S/N", th),
        Paragraph("Unit of Competency", th),
        Paragraph("Unit Type (Core/Common/Basic)", th),
        Paragraph("Unit Cost (Ksh)", th),
    ]
    u_rows = [u_header]
    total_cost = 0.0
    for i, ud in enumerate(units_data):
        unit = ud.get("unit") or {}
        cost_raw = ud.get("cost") or ""
        try:
            cost_val = float(cost_raw) if cost_raw not in ("", None) else 0.0
        except (ValueError, TypeError):
            cost_val = 0.0
        total_cost += cost_val
        cost_str = f"{cost_val:,.2f}" if cost_val else ""
        name = unit.get("name") or ""
        code = unit.get("code") or ""
        display = f"{code} — {name}" if code else name
        u_rows.append([
            Paragraph(str(i + 1), td_c),
            Paragraph(display, td),
            Paragraph(ud.get("type") or "Core", td_c),
            Paragraph(cost_str, td_c),
        ])

    while len(u_rows) < 6:
        u_rows.append([
            Paragraph(str(len(u_rows)), td_c),
            Paragraph("", td),
            Paragraph("", td),
            Paragraph("", td),
        ])

    u_rows.append([
        Paragraph("TOTAL", ParagraphStyle("tot2", parent=lbl, alignment=TA_RIGHT)),
        Paragraph("", td),
        Paragraph("", td),
        Paragraph(f"{total_cost:,.2f}" if total_cost else "", ParagraphStyle(
            "totv2", parent=val, fontName="Helvetica-Bold", alignment=TA_CENTER
        )),
    ])

    col_w = [0.4 * inch, W - 0.4 * inch - 1.55 * inch - 1.05 * inch, 1.55 * inch, 1.05 * inch]
    utbl = Table(u_rows, colWidths=col_w, repeatRows=1)
    utbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, border),
        ("BACKGROUND", (0, 0), (-1, 0), navy),
        ("BACKGROUND", (0, -1), (2, -1), label_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("SPAN", (0, -1), (2, -1)),
        ("ALIGN", (0, -1), (2, -1), "RIGHT"),
    ]))
    story.append(utbl)
    story.append(Spacer(1, 8))

    # ── SECTION 3 ────────────────────────────────────────────────────────────
    story.append(section_bar("SECTION 3: DEPARTMENTAL CLEARANCE"))
    clear_rows = [
        [Paragraph("Department:", lbl), Paragraph(department_name or "—", val)],
        [Paragraph("HOD Name:", lbl), Paragraph("Head of Department", val)],
    ]
    ctbl = Table(clear_rows, colWidths=[W * 0.22, W * 0.78])
    ctbl.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.6, border),
        ("BACKGROUND", (0, 0), (0, -1), label_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(ctbl)
    story.append(Spacer(1, 10))

    # ── Authorization strip (gold border, 3 columns) ─────────────────────────
    def sig_block(title, subtitle=None):
        lines = [Paragraph(title, auth_h)]
        if subtitle:
            lines.append(Paragraph(subtitle, auth_s))
            lines.append(Spacer(1, 4))
        lines.append(Paragraph("Name: ___________________________", auth_s))
        lines.append(Spacer(1, 6))
        lines.append(Paragraph("Sign: ____________________________", auth_s))
        lines.append(Spacer(1, 6))
        lines.append(Paragraph("Date: ____________________________", auth_s))
        return lines

    stamp_inner = Table([[Paragraph("", auth_s)]], colWidths=[W * 0.26], rowHeights=[28 * mm])
    stamp_inner.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94a3b8"), None, (2, 2)),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ]))
    stamp_col = [
        Paragraph("OFFICIAL STAMP", auth_h),
        Paragraph("(Affix stamp here)", ParagraphStyle(
            "st2", parent=auth_s, fontName="Helvetica-Oblique", spaceAfter=4
        )),
        stamp_inner,
    ]

    auth = Table(
        [[sig_block("HEAD OF DEPARTMENT"),
          sig_block("OFFICIAL AUTHORIZATION", "EXAMINATION OFFICER"),
          stamp_col]],
        colWidths=[W / 3, W / 3, W / 3],
    )
    auth.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 1.8, gold),
        ("INNERGRID", (0, 0), (-1, -1), 0.8, gold),
        ("BACKGROUND", (0, 0), (-1, -1), light_gold),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(auth)
    story.append(Spacer(1, 8))

    # ── Footer ───────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#cbd5e1"), spaceAfter=3))
    foot_tbl = Table(
        [[
            Paragraph(f"Serial No: {serial_number}", foot),
            Paragraph("Page 1 of 1  •  System-generated document", ParagraphStyle(
                "fr", parent=foot, alignment=TA_RIGHT
            )),
        ]],
        colWidths=[W * 0.55, W * 0.45],
    )
    foot_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(foot_tbl)

    # ── Supporting document pages ────────────────────────────────────────────
    attach_order = [
        ("national_id", "COPY OF NATIONAL ID / PASSPORT"),
        ("birth_certificate", "COPY OF BIRTH CERTIFICATE"),
        ("kcse_certificate", "KCSE CERTIFICATE (Module I students)"),
        ("kcse_result_slip", "KCSE RESULT SLIP"),
        ("most_recent_result_slip", "PREVIOUS MODULE RESULT SLIP (Continuing students)"),
    ]
    pdf_attachments = []
    if documents and storage_client:
        for doc_key, doc_label in attach_order:
            rec = documents.get(doc_key)
            if not rec or not rec.get("file_path"):
                continue
            fp = rec["file_path"]
            ext = fp.rsplit(".", 1)[-1].lower() if "." in fp else ""
            try:
                raw = bytes(storage_client.from_("assessment-evidence").download(fp))
            except Exception:
                continue
            if ext in ("jpg", "jpeg", "png", "webp", "gif"):
                try:
                    pimg = PILImage.open(io.BytesIO(raw))
                    if pimg.mode not in ("RGB", "L"):
                        pimg = pimg.convert("RGB")
                    max_w = A4[0] - 28 * mm
                    max_h = A4[1] - 36 * mm
                    iw, ih = pimg.size
                    ratio = min(max_w / iw, max_h / ih, 1.0)
                    out = io.BytesIO()
                    if ratio < 1.0:
                        pimg = pimg.resize((int(iw * ratio), int(ih * ratio)), PILImage.LANCZOS)
                    pimg.save(out, format="JPEG", quality=92)
                    out.seek(0)
                    story.append(PageBreak())
                    story.append(Paragraph(doc_label, ParagraphStyle(
                        "dl", parent=base["Normal"], fontName="Helvetica-Bold",
                        fontSize=10, textColor=navy, spaceAfter=6
                    )))
                    story.append(RLImage(out, width=iw * ratio, height=ih * ratio))
                except Exception:
                    pass
            elif ext == "pdf":
                pdf_attachments.append((doc_label, raw))

    pdf.build(story)
    form_bytes = buf.getvalue()

    if pdf_attachments:
        try:
            from pypdf import PdfWriter, PdfReader
            writer = PdfWriter()
            writer.append(PdfReader(io.BytesIO(form_bytes)))
            for _, pdf_raw in pdf_attachments:
                try:
                    writer.append(PdfReader(io.BytesIO(pdf_raw)))
                except Exception:
                    pass
            merged = io.BytesIO()
            writer.write(merged)
            return merged.getvalue()
        except ImportError:
            pass

    return form_bytes
