# Databricks notebook source
# MAGIC %md
# MAGIC # FINS Source Data Generator
# MAGIC
# MAGIC Creates synthetic invoice source data in `hp_sf_test.fins` with deliberately
# MAGIC planted data quality defects. These defects will be caught by DLT expectations
# MAGIC in the pipeline and routed to the quarantine / exceptions tables.
# MAGIC
# MAGIC **Schema**: `hp_sf_test.fins`
# MAGIC
# MAGIC **Source tables written**:
# MAGIC - `source_vendor_master` — 30 vendors (25 ACTIVE, 5 INACTIVE)
# MAGIC - `source_po_master`     — 110 purchase orders
# MAGIC - `source_raw_invoices`  — 120 invoices (24 with planted defects)
# MAGIC
# MAGIC **Planted defects (24 total)**:
# MAGIC | Defect                    | Count | DLT Expectation that catches it              |
# MAGIC |---------------------------|-------|----------------------------------------------|
# MAGIC | Missing PO reference      | 5     | `po_id IS NOT NULL`                          |
# MAGIC | Inactive vendor           | 4     | `vendor_status = 'ACTIVE'`                   |
# MAGIC | Amount variance > 10%     | 4     | `invoice_po_variance_pct <= 0.10`            |
# MAGIC | Duplicate invoice number  | 3     | `is_duplicate = false`                       |
# MAGIC | Future-dated invoice      | 4     | `invoice_date <= current_date()`             |
# MAGIC | Invalid GSTIN format      | 2     | `gstin_valid = true`                         |
# MAGIC | Low OCR confidence (<70%) | 2     | `ocr_confidence >= 0.70`                     |

# COMMAND ----------

CATALOG = "hp_sf_test"
SCHEMA  = "fins"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
print(f"Schema ready: {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md ## Dependencies

# COMMAND ----------

# MAGIC %pip install faker --quiet

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

CATALOG = "hp_sf_test"
SCHEMA  = "fins"

import random
from datetime import date, timedelta
from faker import Faker
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *

fake = Faker("en_IN")
random.seed(42)
Faker.seed(42)

spark = SparkSession.builder.getOrCreate()
print("Ready")

# COMMAND ----------

# MAGIC %md ## 1. Vendor Master

# COMMAND ----------

ACTIVE_VENDOR_IDS   = [f"FINSV{str(i).zfill(3)}" for i in range(1, 26)]   # V001-V025
INACTIVE_VENDOR_IDS = [f"FINSV{str(i).zfill(3)}" for i in range(26, 31)]  # V026-V030
ALL_VENDOR_IDS      = ACTIVE_VENDOR_IDS + INACTIVE_VENDOR_IDS

INDUSTRY_NAMES = [
    "Technologies Pvt Ltd", "Consulting Services Ltd", "Systems & Solutions",
    "Enterprises LLP", "Infrastructure Ltd", "Digital Services",
    "Manufacturing Co", "Logistics Pvt Ltd", "Analytics Ltd", "Cloud Solutions",
]

def valid_gstin(state_code: int = 27) -> str:
    """Generate a syntactically valid GSTIN."""
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    pan_alpha = "".join(random.choices(letters, k=5))
    pan_num   = str(random.randint(1000, 9999))
    pan_check = random.choice(letters)
    entity    = random.choice("1234567890ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    checksum  = random.choice("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    return f"{state_code:02d}{pan_alpha}{pan_num}{pan_check}{entity}Z{checksum}"


vendors = []
for i, vid in enumerate(ALL_VENDOR_IDS):
    base = fake.company().split()[0]
    name = f"{base} {INDUSTRY_NAMES[i % len(INDUSTRY_NAMES)]}"
    status = "ACTIVE" if vid in ACTIVE_VENDOR_IDS else "INACTIVE"
    vendors.append({
        "vendor_id":      vid,
        "vendor_name":    name,
        "vendor_status":  status,
        "gstin":          valid_gstin(random.choice([27, 29, 7, 33, 36])),
        "payment_terms":  random.choice(["Net 30", "Net 45", "Net 60", "2/10 Net 30"]),
        "contact_email":  fake.company_email(),
        "city":           fake.city(),
    })

vendor_schema = StructType([
    StructField("vendor_id",     StringType()),
    StructField("vendor_name",   StringType()),
    StructField("vendor_status", StringType()),
    StructField("gstin",         StringType()),
    StructField("payment_terms", StringType()),
    StructField("contact_email", StringType()),
    StructField("city",          StringType()),
])

df_vendors = spark.createDataFrame(vendors, schema=vendor_schema)
df_vendors.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.source_vendor_master")
print(f"Vendors written: {df_vendors.count()} rows")
df_vendors.groupBy("vendor_status").count().show()

# COMMAND ----------

# MAGIC %md ## 2. PO Master

# COMMAND ----------

today = date.today()
PO_COUNT = 110

pos = []
for i in range(1, PO_COUNT + 1):
    vendor = random.choice(ACTIVE_VENDOR_IDS)  # POs always go to active vendors
    po_date = today - timedelta(days=random.randint(30, 180))
    po_amount = round(random.uniform(50_000, 2_000_000), 2)
    pos.append({
        "po_id":         f"FINSPO{str(i).zfill(4)}",
        "vendor_id":     vendor,
        "po_date":       po_date,
        "po_amount":     po_amount,
        "description":   random.choice([
            "IT Hardware Procurement", "Software Licenses",
            "Consulting Services", "Office Supplies",
            "Cloud Infrastructure", "Marketing Services",
            "Logistics & Warehousing", "Facility Management",
        ]),
        "department":    random.choice(["IT", "Finance", "Operations", "HR", "Marketing", "Procurement"]),
        "po_status":     "OPEN",
    })

po_schema = StructType([
    StructField("po_id",       StringType()),
    StructField("vendor_id",   StringType()),
    StructField("po_date",     DateType()),
    StructField("po_amount",   DoubleType()),
    StructField("description", StringType()),
    StructField("department",  StringType()),
    StructField("po_status",   StringType()),
])

df_pos = spark.createDataFrame(pos, schema=po_schema)
df_pos.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.source_po_master")
print(f"POs written: {df_pos.count()} rows")

# COMMAND ----------

# MAGIC %md ## 3. Invoice Source Data (with planted defects)

# COMMAND ----------

# --- Pull the PO list for reference ---
po_list = [(r["po_id"], r["vendor_id"], r["po_amount"]) for r in df_pos.collect()]

def make_raw_text(inv_num, vendor_name, inv_date, po_ref, amount, gstin, terms, garbled=False):
    """Simulate text extracted from a scanned invoice PDF."""
    if garbled:
        # Simulate low-quality OCR output
        garbled_vendor = vendor_name[:3] + "0" + vendor_name[4:7] + "@" + vendor_name[7:]
        garbled_amount = str(amount).replace("1", "I").replace("0", "O")[:8] + "??"
        return (
            f"INV01CE\n"
            f"Inv N0: {inv_num}\n"
            f"V3nd0r: {garbled_vendor}\n"
            f"D@te: {str(inv_date).replace('-','/')}\n"
            f"P0 Ref: {po_ref or 'N/A'}\n"
            f"Am0unt: INR {garbled_amount}\n"
            f"GS1N: {gstin or '?????'}\n"
        )
    return (
        f"TAX INVOICE\n"
        f"Invoice No: {inv_num}\n"
        f"Vendor: {vendor_name}\n"
        f"Date: {str(inv_date).replace('-','/')}\n"
        f"PO Reference: {po_ref or 'N/A'}\n"
        f"Amount (INR): {amount:,.2f}\n"
        f"GSTIN: {gstin or 'N/A'}\n"
        f"Payment Terms: {terms}\n"
    )


invoices = []
used_invoice_numbers = []  # Track for duplicates

# ─── CLEAN invoices (1–96) ────────────────────────────────────────────────────
for i in range(1, 97):
    po_id, vendor_id, po_amount = random.choice(po_list)
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    invoice_amount = round(po_amount * random.uniform(0.90, 1.05), 2)  # within tolerance
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today - timedelta(days=random.randint(1, 45))
    gstin = valid_gstin()
    used_invoice_numbers.append((inv_num, vendor_id))
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.82, 0.99), 2),
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, gstin, vendor_row["payment_terms"]),
        "_defect":        "none",
    })

# ─── DEFECT 1: Missing PO Reference (5 invoices, IDs 97–101) ─────────────────
for i in range(97, 102):
    vendor_id = random.choice(ACTIVE_VENDOR_IDS)
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    invoice_amount = round(random.uniform(100_000, 500_000), 2)
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today - timedelta(days=random.randint(1, 20))
    gstin = valid_gstin()
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          None,          # ← DEFECT
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      None,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.80, 0.97), 2),
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, None, invoice_amount, gstin, vendor_row["payment_terms"]),
        "_defect":        "missing_po",
    })

# ─── DEFECT 2: Inactive Vendor (4 invoices, IDs 102–105) ─────────────────────
for i, vendor_id in enumerate(INACTIVE_VENDOR_IDS[:4], start=102):
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    po_id, _, po_amount = random.choice(po_list)
    invoice_amount = round(po_amount * random.uniform(0.95, 1.05), 2)
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today - timedelta(days=random.randint(5, 30))
    gstin = valid_gstin()
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,     # ← DEFECT: inactive vendor
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.78, 0.95), 2),
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, gstin, vendor_row["payment_terms"]),
        "_defect":        "inactive_vendor",
    })

# ─── DEFECT 3: Amount Variance > 10% (4 invoices, IDs 106–109) ───────────────
for i in range(106, 110):
    po_id, vendor_id, po_amount = random.choice(po_list)
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    invoice_amount = round(po_amount * random.uniform(1.15, 1.30), 2)  # ← DEFECT: 15–30% over
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today - timedelta(days=random.randint(1, 25))
    gstin = valid_gstin()
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.80, 0.95), 2),
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, gstin, vendor_row["payment_terms"]),
        "_defect":        "amount_variance",
    })

# ─── DEFECT 4: Duplicate Invoice Number (3 invoices, IDs 110–112) ────────────
dup_sources = used_invoice_numbers[:3]
for offset, (orig_num, orig_vendor_id) in enumerate(dup_sources):
    i = 110 + offset
    vendor_row = next(v for v in vendors if v["vendor_id"] == orig_vendor_id)
    po_id, _, po_amount = random.choice([(p, v, a) for p, v, a in po_list if v == orig_vendor_id] or [po_list[0]])
    invoice_amount = round(po_amount * random.uniform(0.92, 1.05), 2)
    inv_date = today - timedelta(days=random.randint(1, 10))
    gstin = valid_gstin()
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": orig_num,      # ← DEFECT: same number re-submitted
        "vendor_id":      orig_vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.82, 0.96), 2),
        "raw_text":       make_raw_text(orig_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, gstin, vendor_row["payment_terms"]),
        "_defect":        "duplicate",
    })

# ─── DEFECT 5: Future-Dated Invoice (4 invoices, IDs 113–116) ────────────────
for i in range(113, 117):
    po_id, vendor_id, po_amount = random.choice(po_list)
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    invoice_amount = round(po_amount * random.uniform(0.95, 1.05), 2)
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today + timedelta(days=random.randint(5, 45))  # ← DEFECT: future date
    gstin = valid_gstin()
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.80, 0.95), 2),
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, gstin, vendor_row["payment_terms"]),
        "_defect":        "future_dated",
    })

# ─── DEFECT 6: Invalid GSTIN Format (2 invoices, IDs 117–118) ────────────────
for i in range(117, 119):
    po_id, vendor_id, po_amount = random.choice(po_list)
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    invoice_amount = round(po_amount * random.uniform(0.95, 1.05), 2)
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today - timedelta(days=random.randint(1, 20))
    bad_gstin = f"INVALID{str(i)}"  # ← DEFECT: bad GSTIN
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          bad_gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.82, 0.95), 2),
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, bad_gstin, vendor_row["payment_terms"]),
        "_defect":        "invalid_gstin",
    })

# ─── DEFECT 7: Low OCR Confidence (2 invoices, IDs 119–120) ─────────────────
for i in range(119, 121):
    po_id, vendor_id, po_amount = random.choice(po_list)
    vendor_row = next(v for v in vendors if v["vendor_id"] == vendor_id)
    invoice_amount = round(po_amount * random.uniform(0.95, 1.05), 2)
    inv_num = f"FINS-INV-{str(i).zfill(4)}"
    inv_date = today - timedelta(days=random.randint(1, 15))
    gstin = valid_gstin()
    invoices.append({
        "invoice_id":     f"FINSINV{str(i).zfill(5)}",
        "invoice_number": inv_num,
        "vendor_id":      vendor_id,
        "vendor_name":    vendor_row["vendor_name"],
        "po_id":          po_id,
        "invoice_date":   inv_date,
        "invoice_amount": invoice_amount,
        "po_amount":      po_amount,
        "gstin":          gstin,
        "payment_terms":  vendor_row["payment_terms"],
        "ocr_confidence": round(random.uniform(0.40, 0.65), 2),  # ← DEFECT: low OCR
        "raw_text":       make_raw_text(inv_num, vendor_row["vendor_name"], inv_date, po_id, invoice_amount, gstin, vendor_row["payment_terms"], garbled=True),
        "_defect":        "low_ocr",
    })

print(f"Total invoices generated: {len(invoices)}")
from collections import Counter
print("Defect breakdown:", Counter(r["_defect"] for r in invoices))

# COMMAND ----------

invoice_schema = StructType([
    StructField("invoice_id",     StringType()),
    StructField("invoice_number", StringType()),
    StructField("vendor_id",      StringType()),
    StructField("vendor_name",    StringType()),
    StructField("po_id",          StringType()),
    StructField("invoice_date",   DateType()),
    StructField("invoice_amount", DoubleType()),
    StructField("po_amount",      DoubleType()),
    StructField("gstin",          StringType()),
    StructField("payment_terms",  StringType()),
    StructField("ocr_confidence", DoubleType()),
    StructField("raw_text",       StringType()),
    StructField("_defect",        StringType()),
])

df_invoices = spark.createDataFrame(invoices, schema=invoice_schema)
df_invoices.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.source_raw_invoices")

print(f"\nInvoices written: {df_invoices.count()} rows")
print("\nDefect distribution:")
df_invoices.groupBy("_defect").count().orderBy("count", ascending=False).show()

# COMMAND ----------

# MAGIC %md ## Verify Source Tables

# COMMAND ----------

for table in ["source_vendor_master", "source_po_master", "source_raw_invoices"]:
    count = spark.table(f"{CATALOG}.{SCHEMA}.{table}").count()
    print(f"  {CATALOG}.{SCHEMA}.{table}: {count} rows")

print(f"\nSource data ready. Run the DLT pipeline next.")
