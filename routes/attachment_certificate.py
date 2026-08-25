"""
Industrial Attachment Completion Certificate routes.

- Public verification: /attachment/verify  (+ /<certificate_number>)
- PDF download helpers used by student / liaison / mentor portals
"""

from __future__ import annotations

import io
import os
from datetime import datetime

from flask import (
    Blueprint, render_template, request, flash, redirect, url_for,
    abort, make_response,
)

from auth_utils import login_required, current_user, write_audit_log
from db import get_service_client
from routes.attachment_helpers import (
    get_certificate_by_number,
    get_certificate_for_attachment,
    company_cert_label,
    format_cert_date,
    certificates_table_ok,
    INSTITUTION_NAME,
)

attachment_certificate_bp = Blueprint("attachment_certificate", __name__)


def _base_url() -> str:
    return (os.environ.get("APP_BASE_URL") or request.host_url or "").rstrip("/")


def _verify_url(certificate_number: str) -> str:
    return f"{_base_url()}/attachment/verify/{certificate_number}"


def _can_view_attachment_cert(user: dict, attachment: dict) -> bool:
    if not user or not attachment:
        return False
    role = user.get("role")
    if role in ("super_admin", "liaison_officer", "deputy_principal", "registrar"):
        return True
    if role == "student" and attachment.get("student_id") == user.get("id"):
        return True
    if role == "industry_mentor":
        db = get_service_client()
        mentor = (db.table("mentors")
                  .select("company_id")
                  .eq("user_id", user["id"])
                  .limit(1)
                  .execute().data or [])
        if mentor and mentor[0].get("company_id") == attachment.get("company_id"):
            return True
    if role == "dept_admin":
        dept = user.get("department_id")
        if dept and (
            attachment.get("department_id") == dept
            or (attachment.get("user_profiles") or {}).get("department_id") == dept
        ):
            return True
    return False


def _load_attachment(db, attachment_id: str):
    rows = (db.table("industrial_attachments")
            .select(
                "*, companies(name), "
                "user_profiles!industrial_attachments_student_id_fkey"
                "(full_name, admission_no, department_id)"
            )
            .eq("id", attachment_id)
            .limit(1)
            .execute().data or [])
    return rows[0] if rows else None


def build_certificate_pdf_bytes(cert: dict) -> bytes:
    """Generate the system completion certificate PDF (ReportLab)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, Image as RLImage,
    )

    buf = io.BytesIO()
    pdf = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=14 * mm, bottomMargin=16 * mm,
    )
    W = A4[0] - 36 * mm

    base = getSampleStyleSheet()
    DARK = colors.HexColor("#0f2c54")
    GREEN = colors.HexColor("#006600")
    BORDER = colors.HexColor("#e2e8f0")
    LGREY = colors.HexColor("#f8fafc")
    MID = colors.HexColor("#DCE6F4")

    ctr16b = ParagraphStyle(
        "ia16", parent=base["Normal"], fontSize=15, fontName="Helvetica-Bold",
        alignment=TA_CENTER, textColor=GREEN, spaceAfter=2, leading=18,
    )
    ctr12b = ParagraphStyle(
        "ia12", parent=base["Normal"], fontSize=11, fontName="Helvetica-Bold",
        alignment=TA_CENTER, textColor=DARK, spaceAfter=2, leading=14,
    )
    ctr9 = ParagraphStyle(
        "ia9", parent=base["Normal"], fontSize=9, fontName="Helvetica",
        alignment=TA_CENTER, spaceAfter=1, textColor=colors.HexColor("#475569"),
    )
    body = ParagraphStyle(
        "iabody", parent=base["Normal"], fontSize=10, fontName="Helvetica",
        alignment=TA_JUSTIFY, leading=14, spaceAfter=6,
    )
    lft10b = ParagraphStyle(
        "ial10b", parent=base["Normal"], fontSize=10, fontName="Helvetica-Bold",
        textColor=DARK,
    )
    lft9b = ParagraphStyle(
        "ial9b", parent=base["Normal"], fontSize=9, fontName="Helvetica-Bold",
    )
    lft9 = ParagraphStyle(
        "ial9", parent=base["Normal"], fontSize=9, fontName="Helvetica",
    )
    mono = ParagraphStyle(
        "iamono", parent=base["Normal"], fontSize=11, fontName="Courier-Bold",
        alignment=TA_CENTER, textColor=colors.HexColor("#15803d"),
    )

    story = []

    # Logos
    root = os.path.join(os.path.dirname(__file__), "..", "static", "assets")
    ttti_logo_path = os.path.join(root, "THIKATTILOGO.jpg")
    govt_logo_path = os.path.join(root, "KENYACOATOFARMS.png")
    ttti_logo_cell = Paragraph("", lft9)
    govt_logo_cell = Paragraph("", lft9)
    if os.path.exists(ttti_logo_path):
        try:
            ttti_logo_cell = RLImage(ttti_logo_path, width=22 * mm, height=22 * mm)
        except Exception:
            pass
    if os.path.exists(govt_logo_path):
        try:
            govt_logo_cell = RLImage(govt_logo_path, width=22 * mm, height=22 * mm)
        except Exception:
            pass

    hdr = Table([[
        govt_logo_cell,
        [
            Paragraph(INSTITUTION_NAME.upper(), ctr16b),
            Paragraph("INDUSTRIAL ATTACHMENT CERTIFICATE OF COMPLETION", ctr12b),
            Paragraph("Academic Management System", ctr9),
        ],
        ttti_logo_cell,
    ]], colWidths=[24 * mm, W - 48 * mm, 24 * mm])
    hdr.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(hdr)
    story.append(HRFlowable(width="100%", thickness=2, color=GREEN, spaceAfter=8))

    cert_no = cert.get("certificate_number") or ""
    verify_url = _verify_url(cert_no)

    # QR code (optional dependency)
    qr_cell = Paragraph("", lft9)
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=4, border=1)
        qr.add_data(verify_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_buf = io.BytesIO()
        img.save(qr_buf, format="PNG")
        qr_buf.seek(0)
        qr_cell = RLImage(qr_buf, width=28 * mm, height=28 * mm)
    except Exception:
        qr_cell = Paragraph("Scan to verify<br/>(see URL below)", ctr9)

    serial_block = [
        Paragraph("CERTIFICATE NUMBER", lft9b),
        Paragraph(cert_no, mono),
        Spacer(1, 4),
        Paragraph("Scan QR to view live verification status.", lft9),
    ]
    serial_tbl = Table([[serial_block, qr_cell]], colWidths=[W - 34 * mm, 34 * mm])
    serial_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#166534")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    story.append(serial_tbl)
    story.append(Spacer(1, 12))

    story.append(Paragraph("This is to certify that:", body))
    story.append(Spacer(1, 4))

    def _row(label, value):
        t = Table(
            [[Paragraph(label, lft9b), Paragraph(str(value or "—"), lft9)]],
            colWidths=[42 * mm, W - 42 * mm],
        )
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LINEBELOW", (1, 0), (1, 0), 0.4, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ]))
        return t

    story.append(_row("Trainee Name:", cert.get("trainee_name")))
    story.append(_row("Admission No.:", cert.get("admission_no")))
    story.append(_row("Programme:", cert.get("programme")))
    story.append(_row("Department:", cert.get("department_name")))
    story.append(_row("Institution:", cert.get("institution_name") or INSTITUTION_NAME))
    story.append(Spacer(1, 8))

    period = (
        f"{format_cert_date(cert.get('attachment_start'))}"
        f" – {format_cert_date(cert.get('attachment_end'))}"
    )
    story.append(Paragraph(
        "has successfully completed the required industrial attachment at:",
        body,
    ))
    story.append(_row("Company:", cert.get("company_name")))
    story.append(_row("Department/Section:", cert.get("company_department")))
    story.append(_row("Attachment Period:", period))
    story.append(Spacer(1, 8))

    story.append(Paragraph(
        "During the attachment, the trainee participated in relevant industrial "
        "activities and acquired practical skills and competencies related to the programme.",
        body,
    ))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width="100%", thickness=1, color=GREEN, spaceAfter=8))

    line = "_" * 28

    def _sig_box(title, name_prefill="", stamp=False):
        half = W / 2 - 4 * mm
        name_line = name_prefill or line
        rows = [
            [Paragraph(f"<b>{title}</b>", lft9b)],
            [Spacer(1, 8)],
            [Paragraph(f"Name:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{name_line}", lft9)],
            [Spacer(1, 8)],
            [Paragraph(f"Signature:&nbsp;{line}", lft9)],
            [Spacer(1, 8)],
            [Paragraph(f"Date:&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{line}", lft9)],
        ]
        if stamp:
            rows += [
                [Spacer(1, 8)],
                [Paragraph("Company Stamp", lft9b)],
                [Paragraph(
                    "<font color='#64748b'>[ Stamp area ]</font>",
                    ParagraphStyle("stamp", parent=lft9, alignment=TA_CENTER),
                )],
            ]
        t = Table(rows, colWidths=[half])
        t.setStyle(TableStyle([
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("BOX", (0, 0), (-1, -1), 0.7, GREEN),
            ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0fdf4")),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (0, 0), 6),
            ("BOTTOMPADDING", (0, 0), (0, 0), 6),
        ]))
        return t

    company_box = _sig_box(
        "Company Supervisor",
        cert.get("supervisor_name") or line,
        stamp=True,
    )
    liaison_box = _sig_box(
        "Industrial Liaison Officer",
        cert.get("liaison_officer_name") or line,
        stamp=False,
    )
    dual = Table([[company_box, liaison_box]], colWidths=[W / 2 - 2 * mm, W / 2 - 2 * mm])
    dual.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Paragraph("COMPANY CERTIFICATION &amp; INSTITUTION VERIFICATION", lft10b))
    story.append(Spacer(1, 6))
    story.append(dual)
    story.append(Spacer(1, 12))

    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    story.append(Paragraph(
        f"Issued: {format_cert_date(cert.get('issued_at') or datetime.utcnow().date())} "
        f"&nbsp;&nbsp;|&nbsp;&nbsp; Verify: {verify_url}",
        ctr9,
    ))
    story.append(Paragraph(
        "System-generated certificate. Live company certification status is shown only on the verify page.",
        ctr9,
    ))

    serial_wm = cert_no

    def _wm(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 30)
        canvas_obj.setFillColorRGB(0.0, 0.4, 0.0, alpha=0.07)
        canvas_obj.translate(A4[0] / 2, A4[1] / 2)
        canvas_obj.rotate(45)
        canvas_obj.drawCentredString(0, 20, "TTTI IA CERTIFICATE")
        canvas_obj.drawCentredString(0, -18, serial_wm)
        canvas_obj.restoreState()

    pdf.build(story, onFirstPage=_wm, onLaterPages=_wm)
    return buf.getvalue()


# ── Public verification ───────────────────────────────────────────────────────

@attachment_certificate_bp.route("/verify", methods=["GET", "POST"])
@attachment_certificate_bp.route("/verify/<path:certificate_number>")
def verify(certificate_number=None):
    db = get_service_client()
    result = None
    error = None

    if request.method == "POST":
        certificate_number = (request.form.get("certificate_number") or "").strip()

    if certificate_number:
        certificate_number = certificate_number.strip().upper()
        if not certificates_table_ok(db):
            error = "Certificate verification is not configured yet."
        else:
            cert = get_certificate_by_number(db, certificate_number)
            if not cert:
                error = "No certificate found for that number."
            else:
                co_status = cert.get("company_certification_status") or "pending_company_stamp"
                result = {
                    "certificate_number": cert.get("certificate_number"),
                    "trainee": cert.get("trainee_name"),
                    "admission_no": cert.get("admission_no"),
                    "programme": cert.get("programme"),
                    "department": cert.get("department_name"),
                    "company": cert.get("company_name"),
                    "period": (
                        f"{format_cert_date(cert.get('attachment_start'))}"
                        f" – {format_cert_date(cert.get('attachment_end'))}"
                    ),
                    "attachment_status": "COMPLETED",
                    "company_certification": company_cert_label(co_status),
                    "verified": "YES" if co_status == "verified" else "NO",
                    "system_verified": True,
                    "issued_at": format_cert_date(cert.get("issued_at")),
                }

    return render_template(
        "attachment/verify.html",
        result=result,
        error=error,
        certificate_number=certificate_number or "",
    )


# ── Authenticated HTML preview ────────────────────────────────────────────────

@attachment_certificate_bp.route("/certificate/<attachment_id>")
@login_required
def certificate_view(attachment_id):
    db = get_service_client()
    user = current_user()
    att = _load_attachment(db, attachment_id)
    if not att:
        abort(404)
    if not _can_view_attachment_cert(user, att):
        abort(403)

    cert = get_certificate_for_attachment(db, attachment_id)
    if not cert:
        flash("No completion certificate has been issued for this attachment yet.", "warning")
        if user.get("role") == "student":
            return redirect(url_for("student.industrial_attachment"))
        if user.get("role") == "liaison_officer":
            return redirect(url_for("liaison_officer.placement_detail", att_id=attachment_id))
        return redirect(url_for("industry_mentor.trainees"))

    verify_url = _verify_url(cert["certificate_number"])
    return render_template(
        "attachment/completion_certificate.html",
        cert=cert,
        att=att,
        verify_url=verify_url,
        company_cert_label=company_cert_label,
        format_cert_date=format_cert_date,
    )


@attachment_certificate_bp.route("/certificate/<attachment_id>/pdf")
@login_required
def certificate_pdf(attachment_id):
    db = get_service_client()
    user = current_user()
    att = _load_attachment(db, attachment_id)
    if not att:
        abort(404)
    if not _can_view_attachment_cert(user, att):
        abort(403)

    cert = get_certificate_for_attachment(db, attachment_id)
    if not cert:
        flash("Certificate not issued yet.", "warning")
        return redirect(url_for("attachment_certificate.certificate_view",
                                attachment_id=attachment_id))

    try:
        pdf_bytes = build_certificate_pdf_bytes(cert)
        resp = make_response(pdf_bytes)
        resp.headers["Content-Type"] = "application/pdf"
        safe = (cert.get("certificate_number") or "IA").replace("/", "-")
        adm = (cert.get("admission_no") or "").replace(" ", "")
        resp.headers["Content-Disposition"] = (
            f'attachment; filename="IA_Completion_{safe}_{adm}.pdf"'
        )
        write_audit_log(
            "download_ia_certificate",
            target=f"attachment:{attachment_id}",
            detail={"certificate_number": cert.get("certificate_number")},
        )
        return resp
    except ImportError:
        flash("PDF generation requires reportlab. Run: pip install reportlab pillow qrcode", "warning")
        return redirect(url_for("attachment_certificate.certificate_view",
                                attachment_id=attachment_id))
    except Exception as exc:
        flash(f"Could not generate PDF: {exc}", "danger")
        return redirect(url_for("attachment_certificate.certificate_view",
                                attachment_id=attachment_id))
