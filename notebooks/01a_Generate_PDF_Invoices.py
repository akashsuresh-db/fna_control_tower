# Databricks notebook source
# MAGIC %md
# MAGIC # 01a - Generate PDF Invoices from Raw Text
# MAGIC
# MAGIC Reads `raw_text` from `bronze_raw_invoice_documents`, generates a TAX INVOICE-styled PDF
# MAGIC per invoice using ReportLab, writes the PDF to `/Volumes/.../raw_invoices/INV*.pdf`.
# MAGIC
# MAGIC After all PDFs land, optionally deletes the legacy `.txt` files (controlled by `DELETE_TXT`).

# COMMAND ----------

# MAGIC %pip install reportlab --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import os
import re
import io
from pyspark.sql import functions as F

CATALOG = "fna_control_tower_catalog"
SCHEMA = "finance_and_accounting"
VOLUME_DIR = f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices"
DELETE_TXT = True  # PDFs verified visually, removing legacy .txt

print("Target volume:", VOLUME_DIR)

# COMMAND ----------

# MAGIC %md ## Parser and PDF builder (adapted from app/backend/invoice_pdf.py)

# COMMAND ----------

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
)
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

DB_RED    = colors.HexColor("#FF3621")
DB_NAVY   = colors.HexColor("#003159")
DB_DARK   = colors.HexColor("#122A45")
DB_ORANGE = colors.HexColor("#FF7033")
GREY_LIGHT = colors.HexColor("#F3F4F6")
GREY_MID   = colors.HexColor("#9CA3AF")
GREY_TEXT  = colors.HexColor("#374151")
WHITE      = colors.white


def _get(lines, *labels):
    for label in labels:
        for line in lines:
            m = re.search(rf"{re.escape(label)}\s*[:\|]\s*(.+)", line, re.IGNORECASE)
            if m:
                return m.group(1).strip()
    return ""


def _section_lines(lines, start_keyword, end_keywords):
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


def _parse_line_items(lines):
    items, inside = [], False
    for line in lines:
        if re.search(r"ITEMS|LINE ITEMS", line, re.IGNORECASE):
            inside = True
            continue
        if inside:
            if re.search(r"INVOICE TOTAL|SUBTOTAL|Total Amount|TOTAL:", line, re.IGNORECASE):
                break
            # Match: "  1. Description           Qty:  X  Rate:  Y  Amount:  Z"
            m = re.match(r"^\s*(\d+)\.\s+(.+?)\s+Qty:\s*(\d[\d.,]*)\s+Rate:\s*([\d.,]+)\s+Amount:\s*([\d.,]+)", line)
            if m:
                items.append({
                    "idx": m.group(1),
                    "desc": m.group(2).strip(),
                    "qty": m.group(3),
                    "unit": m.group(4),
                    "amount": m.group(5),
                })
    return items


def parse_invoice_text(raw_text):
    lines = raw_text.split("\n")
    return {
        "vendor_name":    _get(lines, "Vendor Name", "Vendor"),
        "vendor_address": _get(lines, "Address"),
        "vendor_gstin":   _get(lines, "GSTIN"),
        "vendor_phone":   _get(lines, "Phone", "Contact"),
        "vendor_email":   _get(lines, "Email"),
        "invoice_no":     _get(lines, "Invoice No", "Invoice Number"),
        "invoice_date":   _get(lines, "Invoice Date", "Date"),
        "due_date":       _get(lines, "Due Date", "Payment Due"),
        "po_ref":         _get(lines, "PO Reference", "PO Ref", "Purchase Order"),
        "bill_to":        _section_lines(lines, "BILL TO", ["LINE ITEMS", "ITEMS:", "INVOICE TOTAL", r"[-─]+"]),
        "line_items":     _parse_line_items(lines),
        "subtotal":       _get(lines, "Subtotal", "Sub Total"),
        "cgst":           _get(lines, "CGST"),
        "sgst":           _get(lines, "SGST"),
        "total":          _get(lines, "Total Amount", "Total:", "Grand Total"),
        "bank_account":   _get(lines, "Bank Account", "Account No", "Account Number"),
        "ifsc":           _get(lines, "IFSC", "IFSC Code"),
    }


def build_pdf_bytes(raw_text, invoice_id):
    parsed = parse_invoice_text(raw_text)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=1.5*cm, rightMargin=1.5*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
    )
    W = A4[0] - 3*cm

    normal = ParagraphStyle("normal", fontName="Helvetica", fontSize=9, textColor=GREY_TEXT, leading=13)
    small  = ParagraphStyle("small",  fontName="Helvetica", fontSize=7.5, textColor=GREY_MID, leading=10)
    bold   = ParagraphStyle("bold",   fontName="Helvetica-Bold", fontSize=9, textColor=GREY_TEXT, leading=13)
    h1     = ParagraphStyle("h1",     fontName="Helvetica-Bold", fontSize=14, textColor=WHITE, leading=18)
    h2     = ParagraphStyle("h2",     fontName="Helvetica-Bold", fontSize=9,  textColor=DB_NAVY, leading=13, spaceAfter=2)
    label  = ParagraphStyle("label",  fontName="Helvetica", fontSize=7, textColor=GREY_MID, leading=9)
    value  = ParagraphStyle("value",  fontName="Helvetica-Bold", fontSize=8.5, textColor=GREY_TEXT, leading=12)
    mono   = ParagraphStyle("mono",   fontName="Courier", fontSize=7.5, textColor=GREY_TEXT, leading=11)
    right  = ParagraphStyle("right",  fontName="Helvetica", fontSize=8.5, textColor=GREY_TEXT, leading=12, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("right_bold", fontName="Helvetica-Bold", fontSize=9, textColor=DB_NAVY, leading=13, alignment=TA_RIGHT)
    center = ParagraphStyle("center", fontName="Helvetica", fontSize=8, textColor=GREY_MID, leading=11, alignment=TA_CENTER)

    story = []

    # Header banner
    header = Table(
        [[Paragraph("TAX INVOICE", h1),
          Paragraph(f"<font color='#FF7033'>{parsed.get('invoice_no') or invoice_id}</font>", h1)]],
        colWidths=[W*0.6, W*0.4],
    )
    header.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,-1),DB_NAVY),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),12),
        ("BOTTOMPADDING",(0,0),(-1,-1),12),
        ("LEFTPADDING",(0,0),(0,-1),14),
        ("RIGHTPADDING",(-1,0),(-1,-1),14),
        ("ALIGN",(1,0),(1,0),"RIGHT"),
    ]))
    story.append(header)
    story.append(Spacer(1, 4*mm))

    # Vendor + Invoice details
    vendor_col = [Paragraph("VENDOR", h2), Paragraph(parsed.get("vendor_name") or "—", bold)]
    if parsed.get("vendor_address"): vendor_col.append(Paragraph(parsed["vendor_address"], normal))
    if parsed.get("vendor_gstin"):   vendor_col.append(Paragraph(f"GSTIN: {parsed['vendor_gstin']}", mono))
    if parsed.get("vendor_phone"):   vendor_col.append(Paragraph(parsed["vendor_phone"], small))
    if parsed.get("vendor_email"):   vendor_col.append(Paragraph(parsed["vendor_email"], small))

    def kv(lbl, val):
        return [Paragraph(lbl.upper(), label), Paragraph(val or "—", value)]

    detail = Table(
        [kv("Invoice No", parsed.get("invoice_no") or invoice_id),
         kv("Invoice Date", parsed.get("invoice_date")),
         kv("Due Date", parsed.get("due_date")),
         kv("PO Reference", parsed.get("po_ref"))],
        colWidths=[W*0.22, W*0.28],
    )
    detail.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),
                                ("BOTTOMPADDING",(0,0),(-1,-1),3),
                                ("TOPPADDING",(0,0),(-1,-1),1)]))

    top = Table([[Table([[p] for p in vendor_col], colWidths=[W*0.45]), detail]],
                 colWidths=[W*0.5, W*0.5])
    top.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LINEAFTER",(0,0),(0,-1),0.5,GREY_LIGHT),
        ("LEFTPADDING",(1,0),(1,-1),10),
        ("RIGHTPADDING",(0,0),(0,-1),10),
    ]))
    story.append(top)
    story.append(Spacer(1, 4*mm))

    # Bill To
    if parsed.get("bill_to"):
        story.append(Paragraph("BILL TO", h2))
        for i, line in enumerate(parsed["bill_to"][:5]):
            story.append(Paragraph(line, bold if i == 0 else normal))
        story.append(Spacer(1, 3*mm))

    # Line items
    items = parsed.get("line_items", [])
    if items:
        story.append(Paragraph("LINE ITEMS", h2))
        rows = [[Paragraph("#", label), Paragraph("Description", label),
                 Paragraph("Qty", label), Paragraph("Unit Price", label),
                 Paragraph("Amount", label)]]
        for it in items:
            rows.append([Paragraph(it["idx"], normal),
                         Paragraph(it["desc"], normal),
                         Paragraph(it["qty"], right),
                         Paragraph(it["unit"], right),
                         Paragraph(it["amount"], right)])
        tbl = Table(rows, colWidths=[W*0.07, W*0.42, W*0.12, W*0.18, W*0.21])
        tbl.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),DB_DARK),
            ("TEXTCOLOR",(0,0),(-1,0),WHITE),
            ("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,0),7),
            ("TOPPADDING",(0,0),(-1,0),5),
            ("BOTTOMPADDING",(0,0),(-1,0),5),
            ("FONTNAME",(0,1),(-1,-1),"Helvetica"),
            ("FONTSIZE",(0,1),(-1,-1),8),
            ("TOPPADDING",(0,1),(-1,-1),4),
            ("BOTTOMPADDING",(0,1),(-1,-1),4),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[WHITE,GREY_LIGHT]),
            ("ALIGN",(2,1),(-1,-1),"RIGHT"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 3*mm))

    # Totals
    totals = []
    if parsed.get("subtotal"): totals.append([Paragraph("Subtotal", right), Paragraph(parsed["subtotal"], right)])
    if parsed.get("cgst"):     totals.append([Paragraph("CGST", right),     Paragraph(parsed["cgst"], right)])
    if parsed.get("sgst"):     totals.append([Paragraph("SGST", right),     Paragraph(parsed["sgst"], right)])
    if parsed.get("total"):
        totals.append([Paragraph("<b>TOTAL</b>", right_bold), Paragraph(f"<b>{parsed['total']}</b>", right_bold)])
    if totals:
        tot = Table(totals, colWidths=[W*0.82, W*0.18])
        tot.setStyle(TableStyle([("TOPPADDING",(0,0),(-1,-1),3),
                                 ("BOTTOMPADDING",(0,0),(-1,-1),3),
                                 ("ALIGN",(0,0),(-1,-1),"RIGHT"),
                                 ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
                                 ("LINEABOVE",(0,-1),(-1,-1),1,DB_NAVY)]))
        story.append(tot)
        story.append(Spacer(1, 4*mm))

    # Bank details
    if parsed.get("bank_account") or parsed.get("ifsc"):
        story.append(HRFlowable(width=W, thickness=0.5, color=GREY_LIGHT))
        story.append(Spacer(1, 2*mm))
        parts = []
        if parsed.get("bank_account"): parts.append(f"Account: {parsed['bank_account']}")
        if parsed.get("ifsc"):         parts.append(f"IFSC: {parsed['ifsc']}")
        story.append(Paragraph("  ·  ".join(parts), small))
        story.append(Spacer(1, 3*mm))

    # Footer
    story.append(HRFlowable(width=W, thickness=0.5, color=GREY_LIGHT))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"Source: UC Volume · raw_invoices/{invoice_id}.pdf · Finance Operations Platform",
        center,
    ))

    doc.build(story)
    return buf.getvalue()

# COMMAND ----------

# MAGIC %md ## Generate PDFs from canonical ERP data
# MAGIC
# MAGIC PDF content is now built from `bronze_p2p_invoices` joined with `bronze_vendors`,
# MAGIC so the vendor name, GSTIN, invoice number, dates, amounts, and PO reference printed
# MAGIC on the PDF exactly match the ERP record for the same `invoice_id`. Previously the
# MAGIC PDFs were generated from independently-randomised raw_text and didn't reconcile.
# MAGIC
# MAGIC On top of the canonical printing we apply **deterministic corruption** to ~3% of
# MAGIC invoices: `MOD(CRC32(invoice_id), 100) < 3`. For those invoices the printed total
# MAGIC is multiplied by a deterministic ratio in [0.85, 1.15] (varies by `invoice_id`)
# MAGIC so the AI extraction will diverge from the ERP by 5-15% and `EXTRACTION_MISMATCH`
# MAGIC fires on a real, defensible signal.
# MAGIC
# MAGIC Corrupted IDs land in `silver_pdf_corruption_log` for demo auditability.

# COMMAND ----------

from datetime import date
import zlib  # CRC32 for deterministic corruption

def _crc32(s: str) -> int:
    return zlib.crc32(s.encode("utf-8")) & 0xFFFFFFFF

def _format_inr(v: float) -> str:
    """Indian comma formatting: 12,34,567.89"""
    if v is None:
        return ""
    sign = "-" if v < 0 else ""
    v = abs(round(v, 2))
    s = f"{v:,.2f}"  # western style 1,234,567.89
    # Convert to Indian style
    int_part, dec_part = s.split(".")
    int_part = int_part.replace(",", "")
    if len(int_part) > 3:
        last3 = int_part[-3:]
        rest = int_part[:-3]
        rest = ",".join([rest[max(0, i - 2):i] for i in range(len(rest), 0, -2)][::-1])
        int_part = f"{rest},{last3}"
    return f"{sign}{int_part}.{dec_part}"

def _build_raw_text(inv: dict, vend: dict, printed_total: float, line_items: list[tuple]) -> str:
    """
    Compose a TAX INVOICE-formatted text from canonical ERP fields. build_pdf_bytes
    (defined earlier in this notebook) parses this back out into the PDF body.
    """
    lines = []
    lines.append("=" * 80)
    lines.append(" " * 28 + "TAX INVOICE")
    lines.append("=" * 80)
    lines.append(f"Vendor: {vend.get('vendor_name', 'UNKNOWN VENDOR')}")
    addr = (vend.get("city") or "") + ", " + (vend.get("state") or "")
    lines.append(f"Address: {addr.strip(', ')}")
    if vend.get("gstin"):
        lines.append(f"GSTIN: {vend['gstin']}")
    if vend.get("contact_phone"):
        lines.append(f"Phone: {vend['contact_phone']}")
    if vend.get("contact_email"):
        lines.append(f"Email: {vend['contact_email']}")
    lines.append("-" * 80)
    lines.append(f"Invoice No: {inv['invoice_number']}")
    lines.append(f"Invoice Date: {inv['invoice_date']}")
    lines.append(f"Due Date: {inv['due_date']}")
    if inv.get("po_id"):
        lines.append(f"PO Reference: {inv['po_id']}")
    lines.append("-" * 80)
    lines.append("ITEMS:")
    lines.append("")
    for i, (desc, qty, rate, amt) in enumerate(line_items, start=1):
        lines.append(f"  {i}. {desc:<40s}   Qty: {qty:>3d}   Rate: {_format_inr(rate)}   Amount: {_format_inr(amt)}")
    lines.append("-" * 80)
    lines.append(f"Subtotal:           INR {_format_inr(inv.get('invoice_amount', 0.0))}")
    if inv.get("tax_amount"):
        lines.append(f"CGST (9%):          INR {_format_inr(inv['tax_amount'] / 2)}")
        lines.append(f"SGST (9%):          INR {_format_inr(inv['tax_amount'] / 2)}")
    # The TOTAL line is what the AI extraction is meant to read. printed_total
    # is the corruption-aware value — equal to invoice_total_inr for clean rows.
    lines.append(f"Total Amount:       INR {_format_inr(printed_total)}")
    lines.append("-" * 80)
    lines.append(f"Bank Account: BNK{_crc32(inv['invoice_id']) % 10000000000:010d}")
    lines.append(f"IFSC: HDFC{_crc32(inv['invoice_id'] + 'ifsc') % 1000000:06d}")
    lines.append("=" * 80)
    return "\n".join(lines)

def _line_items_for(invoice_amount: float, vendor_category: str) -> list[tuple]:
    """Reverse-engineer line items so qty*rate sums to invoice_amount."""
    if invoice_amount is None or invoice_amount <= 0:
        return []
    descs = {
        "IT Services":     ["Cloud workload migration", "DevOps consulting"],
        "Manufacturing":   ["Steel raw material", "Industrial fabrication"],
        "Logistics":       ["Freight charges", "Warehouse handling"],
        "Consulting":      ["Advisory engagement", "Implementation services"],
        "Raw Materials":   ["Chemicals (Q-grade)", "Polymer pellets"],
        "Office Supplies": ["Office equipment", "Stationery bundle"],
        "Facilities":      ["Facility maintenance", "Security services"],
        "Marketing":       ["Campaign production", "Brand strategy retainer"],
        "Legal":           ["Legal retainer", "Compliance review"],
        "HR Services":     ["Recruitment retainer", "Payroll processing"],
    }.get(vendor_category, ["Service line A", "Service line B"])
    half = round(invoice_amount * 0.6, 2)
    rem  = round(invoice_amount - half, 2)
    return [
        (descs[0], 1, half, half),
        (descs[1], 1, rem,  rem),
    ]

# COMMAND ----------

# Pull canonical ERP data joined with vendor master — for every invoice that has
# a corresponding bronze_raw_invoice_documents row (the 200 invoices we host PDFs for).
canonical = spark.sql(f"""
SELECT
    i.invoice_id,
    i.invoice_number,
    DATE_FORMAT(TO_DATE(i.invoice_date), 'dd-MMM-yyyy')  AS invoice_date,
    DATE_FORMAT(TO_DATE(i.due_date),     'dd-MMM-yyyy')  AS due_date,
    i.invoice_amount,
    i.tax_amount,
    i.total_amount         AS invoice_total_inr,
    i.po_id,
    i.vendor_id,
    v.vendor_name,
    v.vendor_category,
    v.gstin,
    v.city,
    v.state,
    v.contact_phone,
    v.contact_email
FROM `{CATALOG}`.`{SCHEMA}`.`bronze_p2p_invoices`         AS i
LEFT JOIN `{CATALOG}`.`{SCHEMA}`.`bronze_vendors`         AS v
       ON i.vendor_id = v.vendor_id
WHERE i.invoice_id IN (SELECT invoice_id FROM `{CATALOG}`.`{SCHEMA}`.`bronze_raw_invoice_documents`)
""").collect()

print(f"Canonical rows pulled: {len(canonical)}")

# COMMAND ----------

# Apply deterministic corruption to ~3% of invoices.
# Ratio is computed from CRC32 — same invoice_id always yields the same printed total,
# so the demo is reproducible.
CORRUPT_PCT = 3   # ~3% of invoices get corrupted
def _printed_total(inv_id: str, true_total: float) -> tuple[float, bool, float]:
    """
    Returns (printed_total, corrupted, ratio).
    ratio = 1.0 for clean rows; in [0.85, 1.15] for corrupted rows.
    """
    h = _crc32(inv_id)
    if h % 100 < CORRUPT_PCT:
        # Map h to ratio in [-0.15, +0.15] in 1% steps, skipping 0.
        delta = ((h % 31) - 15) / 100.0
        if delta == 0:
            delta = 0.05
        ratio = 1.0 + delta
        return round(true_total * ratio, 2), True, ratio
    return true_total, False, 1.0

corruption_rows: list[dict] = []
success, failures = 0, []
for r in canonical:
    inv = r.asDict()
    inv_id = inv["invoice_id"]
    try:
        true_total = float(inv["invoice_total_inr"] or 0)
        printed_total, corrupted, ratio = _printed_total(inv_id, true_total)
        items = _line_items_for(float(inv["invoice_amount"] or 0), inv.get("vendor_category"))
        raw_text = _build_raw_text(inv, inv, printed_total, items)
        pdf_bytes = build_pdf_bytes(raw_text, inv_id)
        out_path = f"{VOLUME_DIR}/{inv_id}.pdf"
        with open(out_path, "wb") as f:
            f.write(pdf_bytes)
        success += 1
        if corrupted:
            corruption_rows.append({
                "invoice_id": inv_id,
                "invoice_number": inv["invoice_number"],
                "vendor_name": inv.get("vendor_name"),
                "true_total_inr": true_total,
                "printed_total_inr": printed_total,
                "corruption_ratio": ratio,
                "corruption_pct": round((ratio - 1.0) * 100, 2),
            })
    except Exception as e:
        failures.append((inv_id, str(e)[:200]))

print(f"PDFs generated: {success}")
print(f"Corrupted (deterministic):  {len(corruption_rows)} / {len(canonical)} ({len(corruption_rows)*100/len(canonical):.1f}%)")
print(f"Failures: {len(failures)}")
for f in failures[:5]:
    print(" ", f)

# COMMAND ----------

# MAGIC %md ## Persist the corruption log for demo auditability

# COMMAND ----------

if corruption_rows:
    corruption_df = spark.createDataFrame(corruption_rows)
    (corruption_df
       .withColumn("_logged_at", F.current_timestamp())
       .write.format("delta").mode("overwrite").option("mergeSchema", "true")
       .saveAsTable(f"{CATALOG}.{SCHEMA}.silver_pdf_corruption_log"))
    print(f"silver_pdf_corruption_log: {len(corruption_rows)} rows written")
else:
    print("No corruptions this run.")

# COMMAND ----------

# MAGIC %md ## Verify

# COMMAND ----------

import os
files = os.listdir(VOLUME_DIR)
pdfs = [f for f in files if f.lower().endswith(".pdf")]
txts = [f for f in files if f.lower().endswith(".txt")]
print(f"Total files in {VOLUME_DIR}: {len(files)}")
print(f"  .pdf: {len(pdfs)}")
print(f"  .txt: {len(txts)}")

# Spot check: read one PDF back, confirm magic header
sample_pdf = os.path.join(VOLUME_DIR, pdfs[0])
with open(sample_pdf, "rb") as f:
    head = f.read(8)
print(f"Sample {pdfs[0]} first bytes: {head}  (should start with %PDF-)")

# COMMAND ----------

# MAGIC %md ## Optional: delete legacy .txt files (only when DELETE_TXT=True)

# COMMAND ----------

if DELETE_TXT and len(pdfs) >= len(canonical):
    removed = 0
    for fn in txts:
        try:
            os.remove(os.path.join(VOLUME_DIR, fn))
            removed += 1
        except Exception as e:
            print("rm failed", fn, e)
    print(f"Removed {removed} .txt files")
else:
    print("DELETE_TXT=False (or PDF count short of source row count) — .txt retained")
