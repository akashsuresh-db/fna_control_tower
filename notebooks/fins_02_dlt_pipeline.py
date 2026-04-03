# Databricks notebook source
# MAGIC %md
# MAGIC # FINS DLT Pipeline — Invoice Processing with Quality Gates
# MAGIC
# MAGIC Demonstrates a full DLT pipeline for AP invoice processing:
# MAGIC
# MAGIC ```
# MAGIC SOURCE DATA
# MAGIC     ↓
# MAGIC ┌──────────────────────────────────────────────┐  BRONZE LAYER
# MAGIC │  bronze_raw_invoice_feed                     │  ← Streaming ingestion
# MAGIC │  bronze_vendor_master_dlt                    │    Basic completeness expectations
# MAGIC │  bronze_po_master_dlt                        │    (null IDs, positive amounts)
# MAGIC └──────────────────────────────────────────────┘
# MAGIC     ↓
# MAGIC ┌──────────────────────────────────────────────┐  BRONZE: TEXT EXTRACTION
# MAGIC │  bronze_invoice_text_extracted               │  ← Parse raw_text, score OCR confidence
# MAGIC └──────────────────────────────────────────────┘    Simulates document AI processing
# MAGIC     ↓
# MAGIC ┌──────────────────────────────────────────────┐  SILVER LAYER
# MAGIC │  silver_invoices_enriched                    │  ← Join vendor + PO data
# MAGIC │                                              │    Compute variance %, duplicate flag
# MAGIC │                                              │    Validate GSTIN format
# MAGIC └──────────────────────────────────────────────┘
# MAGIC     ↓                          ↓
# MAGIC ┌──────────────────┐  ┌────────────────────────┐  QUALITY GATE
# MAGIC │  silver_invoices  │  │ silver_invoices        │
# MAGIC │  _validated       │  │ _quarantine            │  ← 7 DLT expectations
# MAGIC │  (~96 rows ✓)     │  │ (~24 rows ✗)           │    Failing rows captured here
# MAGIC └──────────────────┘  └────────────────────────┘
# MAGIC                                ↓
# MAGIC                    ┌────────────────────────────┐  GOLD LAYER
# MAGIC                    │  gold_invoice_exceptions   │  ← Exception records for display
# MAGIC                    │  gold_pipeline_summary     │  ← Per-stage record counts
# MAGIC                    └────────────────────────────┘
# MAGIC ```
# MAGIC
# MAGIC **Target catalog**: `akash_s_demo.fins`

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.types import StringType

CATALOG = "akash_s_demo"
SCHEMA  = "fins"

# ─── Quality expectations dict (reused for validated + quarantine) ────────────
INVOICE_QUALITY_CHECKS = {
    "PO reference required":         "po_id IS NOT NULL",
    "Vendor must be active":         "vendor_status = 'ACTIVE'",
    "Amount variance within 10%":    "invoice_po_variance_pct <= 0.10",
    "No duplicate invoice":          "is_duplicate = false",
    "Invoice must not be future dated": "invoice_date <= current_date()",
    "GSTIN format must be valid":    "gstin_valid = true",
    "OCR confidence above threshold":"ocr_confidence >= 0.70",
}

# COMMAND ----------

# MAGIC %md ## BRONZE — Raw Ingestion

# COMMAND ----------

@dlt.table(
    name="bronze_raw_invoice_feed",
    comment="Raw invoice records streamed from source system. Basic completeness checks applied.",
    table_properties={"quality": "bronze", "layer": "ingestion", "domain": "AP"},
)
@dlt.expect_or_drop("invoice_id not null",     "invoice_id IS NOT NULL")
@dlt.expect_or_drop("vendor_id not null",      "vendor_id IS NOT NULL")
@dlt.expect_or_drop("positive invoice amount", "invoice_amount > 0")
@dlt.expect("invoice date present",            "invoice_date IS NOT NULL")
def bronze_raw_invoice_feed():
    """
    Streaming ingestion from source system.
    Simulates Auto Loader / CDC feed arriving from ERP.
    Basic null and positive-value guards only — no business logic here.
    """
    return (
        spark.readStream
        .format("delta")
        .table(f"{CATALOG}.{SCHEMA}.source_raw_invoices")
    )


@dlt.table(
    name="bronze_vendor_master_dlt",
    comment="Vendor master reference data.",
    table_properties={"quality": "bronze", "layer": "ingestion", "domain": "AP"},
)
@dlt.expect_or_drop("vendor_id not null",   "vendor_id IS NOT NULL")
@dlt.expect_or_drop("vendor_name not null", "vendor_name IS NOT NULL")
@dlt.expect("valid status values", "vendor_status IN ('ACTIVE', 'INACTIVE')")
def bronze_vendor_master_dlt():
    return (
        spark.readStream
        .format("delta")
        .table(f"{CATALOG}.{SCHEMA}.source_vendor_master")
    )


@dlt.table(
    name="bronze_po_master_dlt",
    comment="Purchase order master reference data.",
    table_properties={"quality": "bronze", "layer": "ingestion", "domain": "AP"},
)
@dlt.expect_or_drop("po_id not null",      "po_id IS NOT NULL")
@dlt.expect_or_drop("vendor_id not null",  "vendor_id IS NOT NULL")
@dlt.expect_or_drop("positive po amount",  "po_amount > 0")
@dlt.expect("po date present",             "po_date IS NOT NULL")
def bronze_po_master_dlt():
    return (
        spark.readStream
        .format("delta")
        .table(f"{CATALOG}.{SCHEMA}.source_po_master")
    )

# COMMAND ----------

# MAGIC %md ## BRONZE — Text Extraction
# MAGIC
# MAGIC Simulates a document AI / OCR step that parses fields from raw invoice text
# MAGIC and assigns an OCR confidence score. Real implementations would call
# MAGIC Azure Document Intelligence, AWS Textract, or Databricks DBRX vision models here.

# COMMAND ----------

@dlt.table(
    name="bronze_invoice_text_extracted",
    comment=(
        "Invoice fields parsed from raw document text. "
        "OCR confidence score attached. Low-confidence records flagged for review. "
        "Simulates output from a Document AI / LLM extraction pipeline."
    ),
    table_properties={"quality": "bronze", "layer": "text_extraction", "domain": "AP"},
)
def bronze_invoice_text_extracted():
    """
    Text extraction step: parse structured fields from raw_text and
    validate OCR confidence. In production this would call a model serving
    endpoint (e.g. Databricks DBRX, Azure Document Intelligence).
    Reads as snapshot (batch) from bronze to enable downstream window functions.
    """
    raw = dlt.read("bronze_raw_invoice_feed")

    return (
        raw
        # Simulate extracting key fields from raw_text via regex / NLP
        .withColumn(
            "extracted_invoice_number",
            F.regexp_extract(F.col("raw_text"), r"Invoice No[:\s]+([A-Z0-9\-]+)", 1),
        )
        .withColumn(
            "extracted_amount_str",
            F.regexp_extract(F.col("raw_text"), r"Amount.*?:\s*([\d,\.]+)", 1),
        )
        .withColumn(
            "extracted_gstin",
            F.regexp_extract(F.col("raw_text"), r"GSTIN[:\s]+([A-Z0-9]+)", 1),
        )
        .withColumn(
            "extraction_status",
            F.when(F.col("ocr_confidence") >= 0.90, F.lit("HIGH_CONFIDENCE"))
             .when(F.col("ocr_confidence") >= 0.70, F.lit("MEDIUM_CONFIDENCE"))
             .otherwise(F.lit("LOW_CONFIDENCE")),
        )
        .withColumn(
            "extraction_timestamp", F.current_timestamp()
        )
    )

# COMMAND ----------

# MAGIC %md ## SILVER — Enriched Invoices
# MAGIC
# MAGIC Joins invoice data with vendor and PO master tables.
# MAGIC Computes derived fields needed for quality gate expectations.

# COMMAND ----------

@dlt.table(
    name="silver_invoices_enriched",
    comment=(
        "Invoices enriched with vendor status, PO amounts, and computed quality fields. "
        "Includes: amount variance %, duplicate flag, GSTIN validity, OCR confidence. "
        "All expectations are evaluated on this table."
    ),
    table_properties={"quality": "silver", "layer": "enrichment", "domain": "AP"},
)
def silver_invoices_enriched():
    """
    Snapshot join — enrich each invoice with current vendor status and PO data.
    Computes all fields required by the quality gate expectations downstream.
    """
    invoices = dlt.read("bronze_invoice_text_extracted")
    vendors  = dlt.read("bronze_vendor_master_dlt")
    pos      = dlt.read("bronze_po_master_dlt")

    # Window for duplicate detection: same invoice_number from same vendor
    # Works in batch mode (silver reads as snapshot)
    from pyspark.sql.window import Window
    dup_window = Window.partitionBy("invoice_number", "vendor_id").orderBy("invoice_id")

    return (
        invoices
        # Join vendor status
        .join(
            vendors.select("vendor_id", "vendor_status", F.col("vendor_name").alias("master_vendor_name")),
            on="vendor_id",
            how="left",
        )
        # Join PO master for amount comparison
        .join(
            pos.select(
                F.col("po_id").alias("po_ref"),
                F.col("po_amount").alias("po_master_amount"),
            ),
            on=F.col("po_id") == F.col("po_ref"),
            how="left",
        )
        # Compute amount variance % vs PO
        .withColumn(
            "invoice_po_variance_pct",
            F.when(
                F.col("po_master_amount").isNotNull() & (F.col("po_master_amount") > 0),
                F.abs(F.col("invoice_amount") - F.col("po_master_amount")) / F.col("po_master_amount"),
            ).otherwise(F.lit(1.0)),  # If no PO, treat as 100% variance
        )
        # Flag duplicates: row_number > 1 for same invoice_number + vendor_id
        .withColumn("_row_num", F.row_number().over(dup_window))
        .withColumn("is_duplicate", F.col("_row_num") > 1)
        .drop("_row_num")
        # Validate GSTIN: standard Indian GSTIN regex
        # Format: 2-digit state + 5 alpha + 4 digit + 1 alpha + 1 alphanumeric + Z + 1 alphanumeric
        .withColumn(
            "gstin_valid",
            F.when(F.col("gstin").isNull(), F.lit(True))
             .otherwise(
                 F.col("gstin").rlike(
                     r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
                 )
             ),
        )
        .drop("po_ref")
    )

# COMMAND ----------

# MAGIC %md ## SILVER — Quality Gate
# MAGIC
# MAGIC **7 expectations** applied. Records that PASS all checks → `silver_invoices_validated`.
# MAGIC Records that FAIL any check → `silver_invoices_quarantine` with a reason code.

# COMMAND ----------

@dlt.expect_all_or_drop(INVOICE_QUALITY_CHECKS)
@dlt.table(
    name="silver_invoices_validated",
    comment=(
        "Invoices that passed ALL 7 quality expectations. "
        "Ready for payment processing and 3-way match."
    ),
    table_properties={"quality": "silver", "layer": "validated", "domain": "AP"},
)
def silver_invoices_validated():
    """
    Clean invoice records — passed every expectation.
    These are ready for AP payment processing.
    """
    return dlt.read("silver_invoices_enriched")


@dlt.table(
    name="silver_invoices_quarantine",
    comment=(
        "Invoices that failed one or more quality expectations. "
        "Each row includes a human-readable quarantine_reason and the specific "
        "failed_checks list for audit trail. These become the AP exceptions."
    ),
    table_properties={"quality": "quarantine", "layer": "exceptions", "domain": "AP"},
)
def silver_invoices_quarantine():
    """
    Quarantined invoice records — failed at least one quality expectation.
    Uses the SAME conditions as INVOICE_QUALITY_CHECKS (single source of truth).
    quarantine_reason picks the most actionable failure for the AP clerk.
    """
    enriched = dlt.read("silver_invoices_enriched")

    # Mirror of INVOICE_QUALITY_CHECKS — same conditions, inverted for filter
    fails_any = (
        F.col("po_id").isNull()
        | (F.col("vendor_status") != "ACTIVE")
        | (F.col("invoice_po_variance_pct") > 0.10)
        | (F.col("is_duplicate") == True)
        | (F.col("invoice_date") > F.current_date())
        | (F.col("gstin_valid") == False)
        | (F.col("ocr_confidence") < 0.70)
    )

    # Priority-ordered quarantine reason (first matching failure shown to AP clerk)
    quarantine_reason_expr = (
        F.when(F.col("po_id").isNull(),
               F.lit("Failed Invoice has no Purchase Order reference — cannot perform 3-way match"))
         .when(F.col("vendor_status") != "ACTIVE",
               F.concat(F.lit("Vendor "), F.col("vendor_id"), F.lit(" is not in the approved vendor list — payment blocked")))
         .when(F.col("invoice_po_variance_pct") > 0.10,
               F.concat(
                   F.lit("Invoice amount variance "),
                   F.round(F.col("invoice_po_variance_pct") * 100, 1).cast(StringType()),
                   F.lit("% exceeds the 10% tolerance against PO value"),
               ))
         .when(F.col("is_duplicate") == True,
               F.lit("Duplicate invoice detected — same invoice number already submitted by this vendor"))
         .when(F.col("invoice_date") > F.current_date(),
               F.concat(F.lit("Future-dated invoice ("), F.col("invoice_date").cast(StringType()), F.lit(") — date validation failed")))
         .when(F.col("gstin_valid") == False,
               F.concat(F.lit("Invalid GSTIN format '"), F.col("gstin"), F.lit("' — GST compliance check failed")))
         .when(F.col("ocr_confidence") < 0.70,
               F.concat(
                   F.lit("Low OCR confidence ("),
                   F.round(F.col("ocr_confidence") * 100, 0).cast("int").cast(StringType()),
                   F.lit("%) — document quality insufficient for automated processing"),
               ))
         .otherwise(F.lit("Multiple validation failures — manual review required"))
    )

    # Recommended action keyed on failure type
    recommended_action_expr = (
        F.when(F.col("po_id").isNull(),
               F.lit("Route to AP supervisor for manual PO assignment or rejection"))
         .when(F.col("vendor_status") != "ACTIVE",
               F.lit("Verify vendor status with Procurement — reactivate or use alternate vendor"))
         .when(F.col("invoice_po_variance_pct") > 0.10,
               F.lit("Request credit note from vendor or raise PO amendment"))
         .when(F.col("is_duplicate") == True,
               F.lit("Hold for 48 hours — auto-reject if original already processed"))
         .when(F.col("invoice_date") > F.current_date(),
               F.lit("Return to vendor for re-dating or hold until invoice date is reached"))
         .when(F.col("gstin_valid") == False,
               F.lit("Request corrected invoice with valid GSTIN from vendor"))
         .when(F.col("ocr_confidence") < 0.70,
               F.lit("Route to manual data entry team for re-keying"))
         .otherwise(F.lit("Escalate to AP Manager for review"))
    )

    return (
        enriched
        .filter(fails_any)
        .withColumn("quarantine_reason",    quarantine_reason_expr)
        .withColumn("recommended_action",   recommended_action_expr)
        .withColumn("exception_type",
            F.when(F.col("po_id").isNull(),                          F.lit("MISSING_PO"))
             .when(F.col("vendor_status") != "ACTIVE",               F.lit("INACTIVE_VENDOR"))
             .when(F.col("invoice_po_variance_pct") > 0.10,          F.lit("AMOUNT_VARIANCE"))
             .when(F.col("is_duplicate") == True,                    F.lit("DUPLICATE"))
             .when(F.col("invoice_date") > F.current_date(),         F.lit("FUTURE_DATED"))
             .when(F.col("gstin_valid") == False,                    F.lit("INVALID_GSTIN"))
             .when(F.col("ocr_confidence") < 0.70,                   F.lit("LOW_OCR_CONFIDENCE"))
             .otherwise(F.lit("MULTIPLE_FAILURES"))
        )
        .withColumn("quarantine_timestamp", F.current_timestamp())
    )

# COMMAND ----------

# MAGIC %md ## GOLD — Invoice Exceptions
# MAGIC
# MAGIC Final output table for the AP exceptions workflow.
# MAGIC Schema mirrors what the Finance Operations app expects.

# COMMAND ----------

@dlt.table(
    name="gold_invoice_exceptions",
    comment=(
        "AP invoice exceptions derived from the DLT quality pipeline. "
        "Each row is a quarantined invoice with structured exception metadata. "
        "Ready for display in the Finance Operations application."
    ),
    table_properties={"quality": "gold", "layer": "exceptions", "domain": "AP"},
)
def gold_invoice_exceptions():
    """
    Clean projection of quarantined invoices for the AP exceptions dashboard.
    Columns align with the existing silver_invoice_exceptions schema in finance_and_accounting.
    """
    return (
        dlt.read("silver_invoices_quarantine")
        .select(
            F.col("invoice_id"),
            F.col("invoice_number"),
            F.col("vendor_id"),
            F.col("vendor_name"),
            F.col("po_id"),
            F.col("invoice_date"),
            F.col("invoice_amount"),
            F.col("po_master_amount").alias("po_amount"),
            F.col("payment_terms"),
            F.col("gstin"),
            F.col("exception_type"),
            F.col("quarantine_reason"),
            F.col("recommended_action"),
            F.round(F.col("invoice_po_variance_pct") * 100, 2).alias("variance_pct"),
            F.col("ocr_confidence"),
            F.col("extraction_status"),
            F.col("quarantine_timestamp"),
        )
        .orderBy("quarantine_timestamp")
    )

# COMMAND ----------

# MAGIC %md ## GOLD — Pipeline Summary
# MAGIC
# MAGIC Per-stage record counts for pipeline health monitoring.
# MAGIC Shows the full funnel: ingested → extracted → enriched → validated / quarantined.

# COMMAND ----------

@dlt.table(
    name="gold_pipeline_summary",
    comment=(
        "Record counts at each pipeline stage. "
        "Use this to visualise the ingestion funnel and exception rate."
    ),
    table_properties={"quality": "gold", "layer": "monitoring", "domain": "AP"},
)
def gold_pipeline_summary():
    """
    Stage-by-stage funnel counts. Each source table contributes tagged rows
    that are then aggregated to produce a single summary table.
    """
    stages = [
        (dlt.read("bronze_raw_invoice_feed"),       "1_bronze_ingested",    "Raw invoices ingested from source system"),
        (dlt.read("bronze_invoice_text_extracted"), "2_bronze_extracted",   "Text fields extracted, OCR confidence scored"),
        (dlt.read("silver_invoices_enriched"),      "3_silver_enriched",    "Enriched with vendor & PO master data"),
        (dlt.read("silver_invoices_validated"),     "4_silver_validated",   "Passed all 7 quality expectations"),
        (dlt.read("silver_invoices_quarantine"),    "5_silver_quarantined", "Failed expectations — quarantined for review"),
    ]

    frames = [
        df.select(
            F.lit(stage).alias("stage"),
            F.lit(description).alias("description"),
            F.lit(1).alias("n"),
        )
        for df, stage, description in stages
    ]

    from functools import reduce
    from pyspark.sql import DataFrame
    unioned = reduce(DataFrame.union, frames)

    return (
        unioned
        .groupBy("stage", "description")
        .agg(F.count("n").alias("record_count"))
        .orderBy("stage")
    )
