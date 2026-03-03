from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from datetime import datetime


# ================= HEADER & FOOTER =================
def header_footer(canvas, doc):
    canvas.saveState()

    # HEADER BAR
    canvas.setFillColor(colors.HexColor("#0b3c5d"))
    canvas.rect(0, A4[1] - 70, A4[0], 70, fill=1)

    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(2 * cm, A4[1] - 40, "NIVA HEALTH KARE")

    canvas.setFont("Helvetica", 9)
    canvas.drawString(
        2 * cm,
        A4[1] - 55,
        "Head Office: Chandra Layout, Bangalore – 560040"
    )

    # FOOTER
    canvas.setFillColor(colors.grey)
    canvas.setFont("Helvetica", 8)
    canvas.drawCentredString(
        A4[0] / 2,
        1.2 * cm,
        f"Page {doc.page}"
    )

    canvas.drawCentredString(
        A4[0] / 2,
        0.7 * cm,
        "This document is confidential and intended only for the recipient"
    )

    canvas.restoreState()


# ================= MAIN PDF =================
def generate_joining_letter_pdf(data, file_path):
    doc = SimpleDocTemplate(
        file_path,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=4 * cm,
        bottomMargin=2.5 * cm
    )

    styles = getSampleStyleSheet()
    story = []

    title_style = ParagraphStyle(
        "title",
        fontSize=14,
        alignment=1,
        spaceAfter=20,
        fontName="Helvetica-Bold"
    )

    body = ParagraphStyle(
        "body",
        fontSize=10.5,
        leading=15
    )

    # ================= PAGE 1 =================
    story.append(Paragraph("APPOINTMENT & JOINING LETTER", title_style))

    story.append(Paragraph(
        f"""
        Date: <b>{datetime.today().strftime('%d %B %Y')}</b><br/><br/>

        Dear <b>{data['employee_name']}</b>,<br/><br/>

        We are pleased to offer you employment with <b>Niva Health Kare</b>,
        a growing IT-enabled healthcare organization headquartered in Bangalore.
        This letter confirms your appointment under the following terms and conditions.
        """,
        body
    ))

    story.append(Spacer(1, 15))

    details_table = Table(
        [
            ["Employee Name", data["employee_name"]],
            ["Designation", data["designation"]],
            ["Department", data["department"]],
            ["Joining Date", data["joining_date"]],
            ["Employment Type", data["employment_type"]],
            ["Work Location", data["work_location"]],
            ["Compensation", data["salary"]],
        ],
        colWidths=[doc.width * 0.35, doc.width * 0.65]
    )

    details_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f4f8")),
        ("PADDING", (0, 0), (-1, -1), 8),
    ]))

    story.append(details_table)
    story.append(PageBreak())

    # ================= PAGE 2 =================
    story.append(Paragraph("TERMS & CONDITIONS", title_style))

    story.append(Paragraph(
        """
        1. You will be on probation for a period of six (6) months from your
        date of joining. During this period, your performance and conduct will
        be evaluated.<br/><br/>

        2. Your employment is subject to company policies, rules, and regulations
        as amended from time to time.<br/><br/>

        3. You are required to maintain strict confidentiality of all company
        data, client information, and intellectual property.<br/><br/>

        4. Any violation of company policies may result in disciplinary action,
        including termination.
        """,
        body
    ))

    story.append(PageBreak())

    # ================= PAGE 3 =================
    story.append(Paragraph("CONFIDENTIALITY & DATA PROTECTION", title_style))

    story.append(Paragraph(
        """
        You shall not disclose, copy, reproduce, or share any proprietary or
        confidential information belonging to Niva Health Kare during or after
        your employment.<br/><br/>

        This obligation survives the termination of your employment.
        """,
        body
    ))

    story.append(PageBreak())

    # ================= PAGE 4 =================
    story.append(Paragraph("ACCEPTANCE OF OFFER", title_style))

    story.append(Paragraph(
        """
        Please confirm your acceptance of this appointment by signing and
        returning a copy of this letter.<br/><br/>

        We welcome you to Niva Health Kare and look forward to a successful
        professional association.
        """,
        body
    ))

    story.append(Spacer(1, 50))

    story.append(Paragraph("<b>For Niva Health Kare</b>", body))
    story.append(Spacer(1, 40))
    story.append(Paragraph("<b>Authorized Signatory</b><br/>HR Department", body))

    story.append(PageBreak())

    # ================= PAGE 5 =================
    story.append(Paragraph("DECLARATION", title_style))
    story.append(Paragraph(
        """
        I hereby accept the appointment under the terms and conditions mentioned
        above and agree to abide by company policies.<br/><br/><br/>

        Employee Signature: ___________________________<br/><br/>
        Date: ___________________
        """,
        body
    ))

    doc.build(
        story,
        onFirstPage=header_footer,
        onLaterPages=header_footer
    )
