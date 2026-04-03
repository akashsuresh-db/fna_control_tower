"""Generate a PDF for a Finance invoice from raw text + ERP metadata."""
import io
import re
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

# ─── Databricks brand palette ────────────────────────────────
DB_RED    = colors.HexColor("#FF3621")
DB_NAVY   = colors.HexColor("#003159")
DB_DARK   = colors.HexColor("#122A45")
DB_ORANGE = colors.HexColor("#FF7033")
AMBER     = colors.HexColor("#F59E0B")
GREY_LIGHT = colors.HexColor("#F3F4F6")
GREY_MID   = colors.HexColor("#9CA3AF")
GREY_TEXT  = colors.HexColor("#374151")
WHITE      = colors.white

# ─── Text parser (mirrors frontend logic) ────────────────────

def _get(lines: list[str], *labels: str) -> str:
    for label in labels:
        for line in lines:
            m = re.search(rf"{re.escape(label)}\s*[:\|]\s*(.+)", line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return ""


def _section_lines(lines: list[str], start_keyword: str, end_keywords: list[str]) -> list[str]:
    result, inside = [], False
    for line in lines:
        if re.search(start_keyword, line, re.IGNORECASE):
            inside = True
            continue
        if inside:
            if any(re.search(k, line, re.IGNORECASE) for k in end_keywords):
                break
            if re.match(r"^[─=\-\s]*$", line):
                continue
            trimmed = line.strip()
            if trimmed:
                result.append(trimmed)
    return result


def _parse_line_items(lines: list[str]) -> list[dict]:
    items, inside = [], False
    for line in lines:
        if re.search(r"LINE ITEMS", line, re.IGNORECASE):
            inside = True
            continue
        if inside:
            if re.search(r"INVOICE TOTAL|SUBTOTAL", line, re.IGNORECASE):
                break
            m = re.match(r"^\s+(\d+)\s{2,}(.+?)\s{2,}(\d[\d.,]*)\s{2,}([\d.,]+)\s{2,}([\d.,]+)", line)
            if m:
                items.append({
                    "idx": m.group(1),
                    "desc": m.group(2).strip(),
                    "qty": m.group(3),
                    "unit": m.group(4),
                    "amount": m.group(5),
                })
    return items


def parse_invoice_text(raw_text: str) -> dict:
    lines = raw_text.split("\n")
    return {
        "vendor_name":    _get(lines, "Vendor Name", "Vendor"),
        "vendor_address": _get(lines, "Address"),
        "vendor_gstin":   _get(lines, "GSTIN"),
        "vendor_phone":   _get(lines, "Phone", "Contact"),
        "invoice_no":     _get(lines, "Invoice No", "Invoice Number"),
        "invoice_date":   _get(lines, "Invoice Date", "Date"),
        "due_date":       _get(lines, "Due Date", "Payment Due"),
        "po_ref":         _get(lines, "PO Reference", "PO Ref", "Purchase Order"),
        "bill_to":        _section_lines(lines, "BILL TO", ["LINE ITEMS", "INVOICE TOTAL", r"[-─]+"]),
        "line_items":     _parse_line_items(lines),
        "subtotal":       _get(lines, "Subtotal", "Sub Total"),
        "cgst":           _get(lines, "CGST"),
        "sgst":           _get(lines, "SGST"),
        "total":          _get(lines, "Total Amount", "Total:", "Grand Total"),
        "bank_account":   _get(lines, "Bank Account", "Account No", "Account Number"),
        "ifsc":           _get(lines, "IFSC", "IFSC Code"),
    }


# ─── PDF builder ─────────────────────────────────────────────

def build_invoice_pdf(
    erp: dict[str, Any],
    raw_text: str | None,
) -> bytes:
    """
    Build and return a PDF for the given invoice.

    erp: dict with keys matching the /api/invoice response
    raw_text: optional TAX INVOICE formatted string
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    W = A4[0] - 3 * cm  # usable width

    # ── Styles ──────────────────────────────────────────────
    normal = ParagraphStyle("normal", fontName="Helvetica", fontSize=9, textColor=GREY_TEXT, leading=13)
    small  = ParagraphStyle("small",  fontName="Helvetica", fontSize=7.5, textColor=GREY_MID, leading=10)
    bold   = ParagraphStyle("bold",   fontName="Helvetica-Bold", fontSize=9, textColor=GREY_TEXT, leading=13)
    h1     = ParagraphStyle("h1",     fontName="Helvetica-Bold", fontSize=14, textColor=WHITE, leading=18)
    h2     = ParagraphStyle("h2",     fontName="Helvetica-Bold", fontSize=9,  textColor=DB_NAVY, leading=13, spaceAfter=2)
    label  = ParagraphStyle("label",  fontName="Helvetica", fontSize=7, textColor=GREY_MID,
                             leading=9, spaceBefore=0, spaceAfter=1, wordWrap="CJK")
    value  = ParagraphStyle("value",  fontName="Helvetica-Bold", fontSize=8.5, textColor=GREY_TEXT, leading=12)
    mono   = ParagraphStyle("mono",   fontName="Courier", fontSize=7.5, textColor=GREY_TEXT, leading=11)
    right  = ParagraphStyle("right",  fontName="Helvetica", fontSize=8.5, textColor=GREY_TEXT,
                             leading=12, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", fontName="Helvetica-Bold", fontSize=9,
                                textColor=DB_NAVY, leading=13, alignment=TA_RIGHT)
    center = ParagraphStyle("center", fontName="Helvetica", fontSize=8, textColor=GREY_MID,
                            leading=11, alignment=TA_CENTER)

    parsed = parse_invoice_text(raw_text) if raw_text else {}

    # Fall back to ERP fields when raw text is missing/incomplete
    doc_vendor  = parsed.get("vendor_name") or erp.get("vendor_name") or erp.get("vendor_id", "")
    doc_invoice_no = parsed.get("invoice_no") or erp.get("invoice_number") or erp.get("invoice_id", "")
    doc_date    = parsed.get("invoice_date") or erp.get("invoice_date", "")
    doc_due     = parsed.get("due_date") or erp.get("due_date", "")
    doc_po      = parsed.get("po_ref") or erp.get("po_id") or "—"
    doc_gstin   = parsed.get("vendor_gstin") or erp.get("gstin") or "—"

    def fmt_inr(n) -> str:
        try:
            v = float(n or 0)
            return f"\u20b9{v:,.2f}" if v else "—"
        except Exception:
            return str(n) if n else "—"

    story = []

    # ══ HEADER BANNER ══════════════════════════════════════════
    header_table = Table(
        [[
            Paragraph("TAX INVOICE", h1),
            Paragraph(f"<font color='#{int(DB_ORANGE.red*255):02x}{int(DB_ORANGE.green*255):02x}{int(DB_ORANGE.blue*255):02x}'>{doc_invoice_no}</font>", h1),
        ]],
        colWidths=[W * 0.6, W * 0.4],
    )
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DB_NAVY),
        ("VALIGN",     (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (0, -1), 14),
        ("RIGHTPADDING", (-1, 0), (-1, -1), 14),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # ══ QUARANTINE BADGE (if applicable) ══════════════════════
    qr = erp.get("quarantine_reason")
    if qr:
        badge_colors = {
            "AMOUNT_MISMATCH": (colors.HexColor("#FEF3C7"), AMBER, "⚠  AMOUNT MISMATCH"),
            "NO_PO_REFERENCE": (colors.HexColor("#FEE2E2"), DB_RED, "✗  NO PO REFERENCE"),
            "DUPLICATE":       (colors.HexColor("#F3E8FF"), colors.HexColor("#7C3AED"), "◈  DUPLICATE"),
        }
        bg, fg, label_text = badge_colors.get(qr, (GREY_LIGHT, GREY_TEXT, qr.replace("_", " ")))
        badge_style = ParagraphStyle("badge", fontName="Helvetica-Bold", fontSize=8,
                                     textColor=fg, alignment=TA_CENTER)
        badge = Table([[Paragraph(label_text, badge_style)]], colWidths=[W])
        badge.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROUNDEDCORNERS", [4]),
        ]))
        story.append(badge)
        story.append(Spacer(1, 4 * mm))

    # ══ VENDOR + INVOICE DETAILS (two columns) ═════════════════
    def kv(lbl: str, val: str) -> list:
        return [Paragraph(lbl.upper(), label), Paragraph(val or "—", value)]

    vendor_col = [
        Paragraph("VENDOR", h2),
        Paragraph(doc_vendor, bold),
    ]
    if parsed.get("vendor_address"):
        vendor_col.append(Paragraph(parsed["vendor_address"], normal))
    if doc_gstin:
        vendor_col.append(Paragraph(f"GSTIN: {doc_gstin}", mono))
    if parsed.get("vendor_phone"):
        vendor_col.append(Paragraph(parsed["vendor_phone"], small))

    detail_data = [
        kv("Invoice No",    doc_invoice_no),
        kv("Invoice Date",  doc_date),
        kv("Due Date",      doc_due),
        kv("PO Reference",  doc_po),
        kv("Payment Terms", erp.get("payment_terms") or "—"),
        kv("Status",        erp.get("status") or "—"),
    ]
    detail_tbl = Table(detail_data, colWidths=[W * 0.22, W * 0.28])
    detail_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
    ]))

    top_table = Table(
        [[
            # left: vendor stack
            Table([[p] for p in vendor_col], colWidths=[W * 0.45]),
            # right: invoice details grid
            detail_tbl,
        ]],
        colWidths=[W * 0.5, W * 0.5],
    )
    top_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEAFTER", (0, 0), (0, -1), 0.5, GREY_LIGHT),
        ("LEFTPADDING", (1, 0), (1, -1), 10),
        ("RIGHTPADDING", (0, 0), (0, -1), 10),
    ]))
    story.append(top_table)
    story.append(Spacer(1, 4 * mm))

    # ══ BILL TO ════════════════════════════════════════════════
    if parsed.get("bill_to"):
        story.append(Paragraph("BILL TO", h2))
        for i, line in enumerate(parsed["bill_to"][:5]):
            style = bold if i == 0 else normal
            story.append(Paragraph(line, style))
        story.append(Spacer(1, 3 * mm))

    # ══ MISMATCH CALLOUT ═══════════════════════════════════════
    inv_amt = float(erp.get("invoice_amount") or 0)
    po_amt  = float(erp.get("po_amount") or 0)
    if qr == "AMOUNT_MISMATCH" and po_amt > 0:
        diff = abs(inv_amt - po_amt)
        pct  = (diff / po_amt) * 100
        mismatch_style = ParagraphStyle("mis", fontName="Helvetica-Bold", fontSize=8,
                                        textColor=AMBER, leading=12)
        mismatch_box = Table(
            [[Paragraph(
                f"⚠  Amount Mismatch: Invoice {fmt_inr(inv_amt)} vs PO {fmt_inr(po_amt)} "
                f"— Difference {fmt_inr(diff)} ({pct:.1f}%)",
                mismatch_style,
            )]],
            colWidths=[W],
        )
        mismatch_box.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#FFFBEB")),
            ("LINEABOVE",     (0, 0), (-1, 0), 2, AMBER),
            ("LINEBELOW",     (0, -1), (-1, -1), 0.5, colors.HexColor("#FDE68A")),
            ("LEFTPADDING",   (0, 0), (-1, -1), 10),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
            ("TOPPADDING",    (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(mismatch_box)
        story.append(Spacer(1, 3 * mm))

    # ══ LINE ITEMS ═════════════════════════════════════════════
    items = parsed.get("line_items", [])
    if items:
        story.append(Paragraph("LINE ITEMS", h2))
        tbl_data = [[
            Paragraph("#", label),
            Paragraph("Description", label),
            Paragraph("Qty", label),
            Paragraph("Unit Price", label),
            Paragraph("Amount", label),
        ]]
        for item in items:
            tbl_data.append([
                Paragraph(item["idx"], normal),
                Paragraph(item["desc"], normal),
                Paragraph(item["qty"],  right),
                Paragraph(item["unit"], right),
                Paragraph(item["amount"], right),
            ])
        items_tbl = Table(
            tbl_data,
            colWidths=[W * 0.07, W * 0.42, W * 0.12, W * 0.18, W * 0.21],
        )
        items_tbl.setStyle(TableStyle([
            # header row
            ("BACKGROUND",    (0, 0), (-1, 0), DB_DARK),
            ("TEXTCOLOR",     (0, 0), (-1, 0), WHITE),
            ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0), 7),
            ("TOPPADDING",    (0, 0), (-1, 0), 5),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
            # data rows
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 8),
            ("TOPPADDING",    (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 4),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1), [WHITE, GREY_LIGHT]),
            ("LINEBELOW",     (0, "splitlast"), (-1, "splitlast"), 0.5, GREY_MID),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            # right-align numeric cols
            ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ]))
        story.append(items_tbl)
        story.append(Spacer(1, 3 * mm))

    # ══ TOTALS ═════════════════════════════════════════════════
    subtotal = parsed.get("subtotal") or fmt_inr(inv_amt)
    cgst     = parsed.get("cgst")
    sgst     = parsed.get("sgst")
    total    = parsed.get("total") or fmt_inr(inv_amt)

    totals_rows: list = []
    if subtotal:
        totals_rows.append([Paragraph("Subtotal", right), Paragraph(subtotal, right)])
    if cgst:
        totals_rows.append([Paragraph("CGST", right), Paragraph(cgst, right)])
    if sgst:
        totals_rows.append([Paragraph("SGST", right), Paragraph(sgst, right)])
    # separator + total
    totals_rows.append([
        Paragraph("<b>TOTAL</b>", right_bold),
        Paragraph(f"<b>{total}</b>", right_bold),
    ])

    totals_tbl = Table(totals_rows, colWidths=[W * 0.82, W * 0.18])
    style_cmds = [
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN",         (0, 0), (-1, -1), "RIGHT"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LINEABOVE",     (0, -1), (-1, -1), 1, DB_NAVY),
    ]
    totals_tbl.setStyle(TableStyle(style_cmds))
    story.append(totals_tbl)
    story.append(Spacer(1, 4 * mm))

    # ══ BANK DETAILS ═══════════════════════════════════════════
    bank  = parsed.get("bank_account")
    ifsc  = parsed.get("ifsc")
    if bank or ifsc:
        story.append(HRFlowable(width=W, thickness=0.5, color=GREY_LIGHT))
        story.append(Spacer(1, 2 * mm))
        parts = []
        if bank: parts.append(f"Account: {bank}")
        if ifsc: parts.append(f"IFSC: {ifsc}")
        story.append(Paragraph("  ·  ".join(parts), small))
        story.append(Spacer(1, 3 * mm))

    # ══ FOOTER ═════════════════════════════════════════════════
    story.append(HRFlowable(width=W, thickness=0.5, color=GREY_LIGHT))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        f"Generated by Finance Operations Platform · {erp.get('invoice_id', '')} · "
        f"Source: {erp.get('file_path', '').split('/')[-1] if erp.get('file_path') else 'ERP Record'}",
        center,
    ))

    doc.build(story)
    return buf.getvalue()
