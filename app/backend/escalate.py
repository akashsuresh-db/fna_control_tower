"""AP Exception Escalation — SQL query → PDF attachment → Email.

The SQL WHERE clause mirrors _detect_p2p_exceptions() in streams.py exactly,
so the email always contains the same exceptions visible in the app.
"""
import io
import os
import smtplib
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from backend.db import query
from backend.config import CATALOG, SCHEMA


# ── SQL ──────────────────────────────────────────────────────────────────────

def get_ap_exceptions() -> list[dict]:
    """
    Return all AP exceptions from gold_fact_invoices.
    Mirrors the four rules in _detect_p2p_exceptions() exactly:
      1. AMOUNT_MISMATCH
      2. NO_PO_REFERENCE
      3. is_overdue AND aging_days > 60  (critical overdue)
      4. gstin_vendor IS NULL            (missing GSTIN)
    """
    rows = query(f"""
        SELECT
            invoice_number,
            vendor_name,
            po_id,
            invoice_total_inr,
            match_status,
            due_date,
            aging_days,
            is_overdue,
            gstin_vendor,
            CASE
                WHEN match_status = 'AMOUNT_MISMATCH'              THEN 'HIGH'
                WHEN match_status = 'NO_PO_REFERENCE'              THEN 'HIGH'
                WHEN is_overdue = true AND aging_days > 60         THEN 'CRITICAL'
                WHEN gstin_vendor IS NULL                          THEN 'MEDIUM'
            END AS severity,
            CASE
                WHEN match_status = 'AMOUNT_MISMATCH'
                    THEN 'Invoice amount does not match PO amount (variance exceeds 2% threshold)'
                WHEN match_status = 'NO_PO_REFERENCE'
                    THEN 'Invoice has no Purchase Order reference — cannot perform 3-way match'
                WHEN is_overdue = true AND aging_days > 60
                    THEN CONCAT('Invoice is ', CAST(aging_days AS STRING), ' days overdue — approaching write-off threshold')
                WHEN gstin_vendor IS NULL
                    THEN 'Vendor GSTIN missing — GST input credit cannot be claimed'
            END AS exception_reason
        FROM `{CATALOG}`.`{SCHEMA}`.gold_fact_invoices
        WHERE
            match_status IN ('AMOUNT_MISMATCH', 'NO_PO_REFERENCE')
            OR (is_overdue = true AND aging_days > 60)
            OR gstin_vendor IS NULL
        ORDER BY
            CASE
                WHEN is_overdue = true AND aging_days > 60 THEN 1
                WHEN match_status IN ('AMOUNT_MISMATCH', 'NO_PO_REFERENCE') THEN 2
                ELSE 3
            END,
            invoice_total_inr DESC
        LIMIT 200
    """)
    return rows or []


# ── PDF ──────────────────────────────────────────────────────────────────────

def generate_pdf(exceptions: list[dict]) -> bytes:
    """Build a landscape A4 PDF table of exceptions using reportlab."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )
    styles = getSampleStyleSheet()
    navy   = colors.HexColor("#1C2536")
    red    = colors.HexColor("#FF3621")
    amber  = colors.HexColor("#E65100")
    yellow = colors.HexColor("#F57F17")
    light  = colors.HexColor("#F5F7FA")

    critical = [e for e in exceptions if e.get("severity") == "CRITICAL"]
    high     = [e for e in exceptions if e.get("severity") == "HIGH"]
    medium   = [e for e in exceptions if e.get("severity") == "MEDIUM"]

    title_style = ParagraphStyle(
        "title", fontSize=16, textColor=navy, spaceAfter=4, fontName="Helvetica-Bold"
    )
    sub_style = ParagraphStyle(
        "sub", fontSize=9, textColor=colors.HexColor("#666666"), spaceAfter=2
    )

    elements = [
        Paragraph("AP Operations — Exception Escalation Report", title_style),
        Paragraph(
            f"Generated {datetime.now().strftime('%d %B %Y, %H:%M')}  ·  "
            f"Source: {CATALOG}.{SCHEMA}.gold_fact_invoices",
            sub_style,
        ),
        Paragraph(
            f"Total: {len(exceptions)} exceptions  |  "
            f"🔴 {len(critical)} Critical  🟠 {len(high)} High  🟡 {len(medium)} Medium",
            sub_style,
        ),
        Spacer(1, 0.15 * inch),
    ]

    # Table data
    headers = ["Invoice #", "Vendor", "Amount (INR)", "PO Ref", "Severity", "Exception Reason", "Due Date", "Aging"]
    rows = [headers]
    for exc in exceptions:
        amount = float(exc.get("invoice_total_inr") or 0)
        rows.append([
            str(exc.get("invoice_number") or ""),
            str(exc.get("vendor_name") or "")[:28],
            f"\u20b9{amount:,.0f}",
            str(exc.get("po_id") or "—"),
            str(exc.get("severity") or ""),
            str(exc.get("exception_reason") or "")[:55],
            str(exc.get("due_date") or "—"),
            f"{exc.get('aging_days') or '—'} d",
        ])

    col_widths = [1.0*inch, 1.7*inch, 1.1*inch, 0.9*inch, 0.75*inch, 3.2*inch, 0.9*inch, 0.55*inch]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)

    ts = TableStyle([
        # Header
        ("BACKGROUND",  (0, 0), (-1, 0), navy),
        ("TEXTCOLOR",   (0, 0), (-1, 0), colors.white),
        ("FONTNAME",    (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0), 8),
        # Body
        ("FONTSIZE",    (0, 1), (-1, -1), 7.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ALIGN",       (2, 0), (2, -1), "RIGHT"),
        ("ALIGN",       (7, 0), (7, -1), "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ])

    # Colour the severity cells
    for i, exc in enumerate(exceptions, start=1):
        sev = exc.get("severity", "")
        c = {"CRITICAL": red, "HIGH": amber, "MEDIUM": yellow}.get(sev)
        if c:
            ts.add("TEXTCOLOR",  (4, i), (4, i), c)
            ts.add("FONTNAME",   (4, i), (4, i), "Helvetica-Bold")

    tbl.setStyle(ts)
    elements.append(tbl)
    doc.build(elements)
    return buf.getvalue()


# ── Email ─────────────────────────────────────────────────────────────────────

def send_escalation_email(exceptions: list[dict], pdf_bytes: bytes, recipient: str) -> None:
    """
    Send an HTML email with the exceptions table + PDF attachment.

    Reads SMTP config from environment variables:
      SMTP_HOST     (default: smtp.gmail.com)
      SMTP_PORT     (default: 587)
      SMTP_USER     sender address / login
      SMTP_PASSWORD sender password / app-password
      SMTP_FROM     display name <addr>  (optional, falls back to SMTP_USER)
    """
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    sender    = os.environ.get("SMTP_FROM", smtp_user)

    if not smtp_user or not smtp_pass:
        raise ValueError("SMTP_USER and SMTP_PASSWORD environment variables are required.")

    critical = [e for e in exceptions if e.get("severity") == "CRITICAL"]
    high     = [e for e in exceptions if e.get("severity") == "HIGH"]
    medium   = [e for e in exceptions if e.get("severity") == "MEDIUM"]
    ts       = datetime.now().strftime("%d %B %Y, %H:%M")

    # ── HTML body ──
    rows_html = ""
    for exc in exceptions:
        sev = exc.get("severity", "")
        sev_css = {
            "CRITICAL": "color:#C62828;font-weight:bold;",
            "HIGH":     "color:#E65100;font-weight:bold;",
            "MEDIUM":   "color:#F57F17;font-weight:bold;",
        }.get(sev, "")
        amount = float(exc.get("invoice_total_inr") or 0)
        rows_html += f"""
          <tr style="border-bottom:1px solid #eee;">
            <td style="padding:7px 10px;">{exc.get("invoice_number","")}</td>
            <td style="padding:7px 10px;">{exc.get("vendor_name","")}</td>
            <td style="padding:7px 10px;text-align:right;">\u20b9{amount:,.0f}</td>
            <td style="padding:7px 10px;{sev_css}">{sev}</td>
            <td style="padding:7px 10px;">{exc.get("exception_reason","")}</td>
            <td style="padding:7px 10px;text-align:center;">{exc.get("aging_days") or "—"} d</td>
            <td style="padding:7px 10px;">{exc.get("due_date") or "—"}</td>
          </tr>"""

    html = f"""
<html><body style="font-family:Arial,sans-serif;color:#333;max-width:960px;margin:0 auto;padding:0;">
  <div style="background:#1C2536;padding:20px 28px;border-radius:8px 8px 0 0;">
    <h2 style="color:white;margin:0;font-size:18px;">⚠️ AP Operations — Exception Escalation</h2>
    <p style="color:#90CAF9;margin:6px 0 0;font-size:13px;">{ts} &nbsp;·&nbsp; Finance &amp; Accounting Control Tower</p>
  </div>

  <div style="background:#FFF8E1;padding:12px 28px;border-left:4px solid #FF3621;font-size:14px;">
    <strong>{len(exceptions)} exception{"s" if len(exceptions)!=1 else ""} require your attention</strong>
    &nbsp;&nbsp;
    <span style="color:#C62828;">🔴 {len(critical)} Critical</span>
    &nbsp;
    <span style="color:#E65100;">🟠 {len(high)} High</span>
    &nbsp;
    <span style="color:#F57F17;">🟡 {len(medium)} Medium</span>
  </div>

  <table style="width:100%;border-collapse:collapse;font-size:13px;margin-top:0;">
    <thead>
      <tr style="background:#2C3E50;color:white;">
        <th style="padding:9px 10px;text-align:left;">Invoice #</th>
        <th style="padding:9px 10px;text-align:left;">Vendor</th>
        <th style="padding:9px 10px;text-align:right;">Amount</th>
        <th style="padding:9px 10px;text-align:left;">Severity</th>
        <th style="padding:9px 10px;text-align:left;">Exception Reason</th>
        <th style="padding:9px 10px;text-align:center;">Aging</th>
        <th style="padding:9px 10px;text-align:left;">Due Date</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>

  <p style="color:#888;font-size:11px;padding:16px 28px;border-top:1px solid #eee;margin:0;">
    Source: <code>{CATALOG}.{SCHEMA}.gold_fact_invoices</code> &nbsp;·&nbsp;
    PDF report attached (downloadable). &nbsp;·&nbsp;
    Sent from Finance &amp; Accounting Control Tower on Databricks.
  </p>
</body></html>"""

    # ── Build MIME ──
    msg = MIMEMultipart()
    msg["From"]    = sender
    msg["To"]      = recipient
    msg["Subject"] = (
        f"[ESCALATION] {len(exceptions)} AP Exception"
        f"{'s' if len(exceptions)!=1 else ''} — {datetime.now().strftime('%d %b %Y')}"
    )
    msg.attach(MIMEText(html, "html"))

    # PDF attachment
    part = MIMEBase("application", "octet-stream")
    part.set_payload(pdf_bytes)
    encoders.encode_base64(part)
    filename = f"AP_Exceptions_{datetime.now().strftime('%Y%m%d')}.pdf"
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(sender, recipient, msg.as_string())
