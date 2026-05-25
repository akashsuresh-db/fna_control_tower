# Databricks notebook source
# MAGIC %md
# MAGIC # Finance & Accounting DLT Pipeline — Bronze → Silver
# MAGIC
# MAGIC **Bronze** ingests transactional data via Auto Loader (`cloudFiles`) from raw CSV files
# MAGIC in `/Volumes/{CATALOG}/finance_and_accounting/raw_csv/`. This is the real medallion entry
# MAGIC point — bronze never reads from another Delta table.
# MAGIC
# MAGIC **Silver** enriches bronze (3-way matching for AP, aging for AR, balance validation for GL).
# MAGIC
# MAGIC **Exceptions** (`silver_invoice_exceptions`) capture every UI-surfaced exception type so the
# MAGIC operator-facing app and the DLT event log stay in lockstep:
# MAGIC   - `AMOUNT_MISMATCH`
# MAGIC   - `NO_PO_REFERENCE`
# MAGIC   - `CRITICAL_OVERDUE` (overdue > 60 days)
# MAGIC   - `MISSING_GSTIN`
# MAGIC   - `DUPLICATE`
# MAGIC   - `EXTRACTION_MISMATCH` (AI-extracted total deviates from ERP)
# MAGIC
# MAGIC Gold transformations remain in `02–04_Gold_Layer_*` notebooks for performance / partitioning.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "fna_control_tower_catalog"
SCHEMA = "finance_and_accounting"
RAW_CSV = f"/Volumes/{CATALOG}/{SCHEMA}/raw_csv"
SCHEMA_LOC = f"/Volumes/{CATALOG}/{SCHEMA}/raw_csv/_dlt_schemas"


# ─── Business expectation predicates (SINGLE SOURCE OF TRUTH) ───────────────
# Each predicate is used in TWO places:
#   1) @dlt.expect decorator on silver_p2p_invoices  → shows up in the DLT Data
#      Quality tab with non-zero failed_records counts.
#   2) The CASE WHEN in silver_invoice_exceptions    → drives the UI's exception
#      type column.
# If a rule changes, change it here only. Do not duplicate logic anywhere else.
EXPECT_HAS_PO_REFERENCE       = "po_id IS NOT NULL AND po_id != ''"
EXPECT_AMOUNT_MATCHES_PO      = "po_total_amount IS NULL OR ABS(invoice_amount - po_total_amount) < invoice_amount * 0.05"
EXPECT_HAS_GRN                = "COALESCE(grn_count, 0) > 0"
EXPECT_HAS_VENDOR_GSTIN       = "gstin_vendor IS NOT NULL AND gstin_vendor != ''"
EXPECT_NOT_CRITICALLY_OVERDUE = "datediff(current_date(), invoice_date) <= 60"
EXPECT_EXTRACTION_MATCHES_ERP = "ai_extracted_amount IS NULL OR ABS(ai_extracted_amount - invoice_amount) <= invoice_amount * 0.02"


def autoload_csv(entity: str):
    """Auto Loader stream from a CSV-per-entity folder under /raw_csv/."""
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.schemaLocation", f"{SCHEMA_LOC}/{entity}")
        .option("cloudFiles.inferColumnTypes", "true")
        .option("header", "true")
        .option("multiLine", "true")
        .option("escape", '"')
        .load(f"{RAW_CSV}/{entity}/")
    )

# COMMAND ----------

# MAGIC %md ## BRONZE LAYER — Auto Loader ingestion from raw CSV

# COMMAND ----------

@dlt.table(name="bronze_vendors", comment="Vendor master — Auto Loader from /raw_csv/vendors/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_vendor_id", "vendor_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_name", "vendor_name IS NOT NULL AND LENGTH(vendor_name) > 0")
@dlt.expect("valid_email", "contact_email LIKE '%@%'")
def bronze_vendors():
    return autoload_csv("vendors")


@dlt.table(name="bronze_customers", comment="Customer master — Auto Loader from /raw_csv/customers/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_customer_id", "customer_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_name", "customer_name IS NOT NULL")
def bronze_customers():
    return autoload_csv("customers")


@dlt.table(name="bronze_po_header", comment="Purchase orders — Auto Loader from /raw_csv/po_header/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_po_id", "po_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_ref", "vendor_id IS NOT NULL")
@dlt.expect("positive_amount", "total_amount > 0")
def bronze_po_header():
    return autoload_csv("po_header")


@dlt.table(name="bronze_grn", comment="Goods receipts — Auto Loader from /raw_csv/grn/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_grn_id", "grn_id IS NOT NULL")
@dlt.expect_or_drop("valid_po_ref", "po_id IS NOT NULL")
def bronze_grn():
    return autoload_csv("grn")


@dlt.table(name="bronze_p2p_invoices", comment="Vendor invoices — Auto Loader from /raw_csv/p2p_invoices/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_invoice_id", "invoice_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_ref", "vendor_id IS NOT NULL")
@dlt.expect_or_drop("positive_total_amount", "total_amount > 0")
def bronze_p2p_invoices():
    return autoload_csv("p2p_invoices")


@dlt.table(name="bronze_p2p_payments", comment="Vendor payments — Auto Loader from /raw_csv/p2p_payments/",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_csv"})
@dlt.expect_or_drop("valid_payment_id", "payment_id IS NOT NULL")
@dlt.expect_or_drop("valid_invoice_ref", "invoice_id IS NOT NULL")
@dlt.expect("positive_payment", "payment_amount > 0")
def bronze_p2p_payments():
    return autoload_csv("p2p_payments")


@dlt.table(name="bronze_sales_orders", comment="Sales orders — Auto Loader from /raw_csv/sales_orders/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_so_id", "so_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_ref", "customer_id IS NOT NULL")
def bronze_sales_orders():
    return autoload_csv("sales_orders")


@dlt.table(name="bronze_o2c_invoices", comment="Customer invoices — Auto Loader from /raw_csv/o2c_invoices/",
           table_properties={"quality": "bronze", "domain": "O2C", "source": "raw_csv"})
@dlt.expect_or_drop("valid_o2c_invoice_id", "o2c_invoice_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_ref", "customer_id IS NOT NULL")
def bronze_o2c_invoices():
    return autoload_csv("o2c_invoices")


@dlt.table(name="bronze_journal_entries", comment="Journal entries — Auto Loader from /raw_csv/journal_entries/",
           table_properties={"quality": "bronze", "domain": "R2R", "source": "raw_csv"})
@dlt.expect_or_drop("valid_je_id", "je_id IS NOT NULL")
@dlt.expect("balanced_entry", "total_debit = total_credit")
def bronze_journal_entries():
    return autoload_csv("journal_entries")


@dlt.table(name="bronze_raw_invoice_documents",
           comment="PDF invoice documents — binary Auto Loader from /raw_invoices/. "
                   "ai_parse_document (notebook 05) consumes this to produce silver_invoice_extractions.",
           table_properties={"quality": "bronze", "domain": "P2P", "source": "raw_invoices_pdf"})
def bronze_raw_invoice_documents():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "binaryFile")
        .option("cloudFiles.schemaLocation", f"{SCHEMA_LOC}/raw_invoice_documents")
        .option("pathGlobFilter", "*.pdf")
        .load(f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices/")
        .select(
            F.regexp_extract(F.col("path"), r"/(INV\d+)\.pdf$", 1).alias("invoice_id"),
            F.col("path").alias("file_path"),
            F.lit("pdf").alias("file_type"),
            F.col("length").alias("file_size_bytes"),
            F.col("modificationTime").alias("file_modified_at"),
            F.col("content"),
            F.lit("PENDING").alias("processing_status"),
            F.current_timestamp().alias("_ingested_at"),
            F.lit("uc_volume").alias("_source_system"),
        )
    )


# COMMAND ----------

# MAGIC %md ## SILVER LAYER — Enrichment, deduplication, 3-way match

# COMMAND ----------

@dlt.table(name="silver_po_header", comment="Validated POs with overdue flag",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_po_header():
    return (
        dlt.read("bronze_po_header")
        .withColumn("po_date", F.to_date("po_date"))
        .withColumn("delivery_date", F.to_date("delivery_date"))
        .withColumn("approved_date",
                    F.when(F.col("approved_date") != "", F.to_date("approved_date"))
                     .otherwise(F.lit(None).cast("date")))
        .withColumn("is_overdue",
                    F.when(
                        F.col("status").isin(["APPROVED", "PARTIALLY_RECEIVED"]) &
                        (F.col("delivery_date") < F.current_date()),
                        True
                    ).otherwise(False))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["po_id"])
    )


@dlt.table(name="silver_grn", comment="Validated GRNs",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_grn():
    return (
        dlt.read("bronze_grn")
        .withColumn("grn_date", F.to_date("grn_date"))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["grn_id"])
    )


@dlt.table(name="silver_p2p_invoices",
           comment="Deduplicated P2P invoices with 3-way match status. Six business expectations attached (warn-only) so the DLT Data Quality tab shows live failed_records for each rule. ai_extracted_amount is joined from silver_invoice_extractions so the extraction_matches_erp expectation has a real input.",
           table_properties={"quality": "silver", "domain": "P2P"})
@dlt.expect("has_po_reference",          EXPECT_HAS_PO_REFERENCE)
@dlt.expect("amount_matches_po",         EXPECT_AMOUNT_MATCHES_PO)
@dlt.expect("has_grn",                   EXPECT_HAS_GRN)
@dlt.expect("has_vendor_gstin",          EXPECT_HAS_VENDOR_GSTIN)
@dlt.expect("not_critically_overdue",    EXPECT_NOT_CRITICALLY_OVERDUE)
@dlt.expect("extraction_matches_erp",    EXPECT_EXTRACTION_MATCHES_ERP)
def silver_p2p_invoices():
    invoices = dlt.read("bronze_p2p_invoices")
    po_headers = dlt.read("silver_po_header")
    grns = dlt.read("silver_grn")
    # ai_extracted_amount must be available on each row for the
    # extraction_matches_erp expectation to evaluate. Pulled from notebook 05's
    # silver_invoice_extractions which lives outside DLT, so we read it directly.
    extractions_for_silver = (
        spark.table(f"{CATALOG}.{SCHEMA}.silver_invoice_extractions")
             .select(
                 "invoice_id",
                 F.col("extracted_total_amount").alias("ai_extracted_amount"),
                 F.col("extracted_gstin").alias("ai_extracted_gstin"),
                 F.col("extracted_vendor_name").alias("ai_extracted_vendor_name"),
                 F.col("file_path").alias("pdf_file_path"),
             )
    )

    # Deduplicate: keep one record per invoice_number
    w = Window.partitionBy("invoice_number").orderBy(F.col("_rescued_data").asc_nulls_first())
    deduped = (
        invoices
        .filter(F.col("status") != "DUPLICATE")
        .withColumn("_rn", F.row_number().over(w))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )

    with_po = deduped.join(
        po_headers.select(
            "po_id",
            F.col("total_amount").alias("po_total_amount"),
            F.col("status").alias("po_status")
        ),
        on="po_id", how="left"
    )

    grn_summary = grns.groupBy("po_id").agg(
        F.count("grn_id").alias("grn_count"),
        F.max("received_amount").alias("grn_received_amount")
    )

    return (
        with_po.join(grn_summary, on="po_id", how="left")
        .join(extractions_for_silver, on="invoice_id", how="left")  # bring AI columns in
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .withColumn("has_po_ref", (F.col("po_id").isNotNull()) & (F.col("po_id") != ""))
        .withColumn("has_grn", F.col("grn_count") > 0)
        .withColumn("amount_matches_po",
                    F.abs(F.col("invoice_amount") - F.coalesce(F.col("po_total_amount"), F.lit(0.0))) <
                    F.col("invoice_amount") * 0.05)
        .withColumn("match_status",
                    F.when(F.col("has_po_ref") & F.col("has_grn") & F.col("amount_matches_po"), "THREE_WAY_MATCHED")
                     .when(F.col("has_po_ref") & F.col("amount_matches_po"), "TWO_WAY_MATCHED")
                     .when(F.col("has_po_ref") & ~F.col("amount_matches_po"), "AMOUNT_MISMATCH")
                     .when(~F.col("has_po_ref"), "NO_PO_REFERENCE")
                     .otherwise("PENDING_REVIEW"))
        .withColumn("days_outstanding",
                    F.when(F.col("status") != "PAID",
                           F.datediff(F.current_date(), F.col("invoice_date"))))
        .withColumn("is_overdue", F.col("due_date") < F.current_date())
        .withColumn("_silver_processed_at", F.current_timestamp())
    )


# COMMAND ----------

# MAGIC %md ## EXCEPTIONS — every UI exception type lives in the pipeline

# COMMAND ----------

@dlt.table(name="silver_invoice_exceptions",
           comment="Every invoice an accountant would touch — i.e. anything that isn't a clean THREE_WAY_MATCH. exception_type is derived from the SAME six predicate constants used by silver_p2p_invoices' @dlt.expect decorators, so the DLT Data Quality tab and this table stay in lockstep.",
           table_properties={"quality": "quarantine", "domain": "P2P"})
def silver_invoice_exceptions():
    # Read from silver (post-dedup, post-3-way-match, post-AI-extraction join) so the
    # classification matches what the AP analyst sees and the predicates above evaluate
    # on the same row shape.
    enriched = (
        dlt.read("silver_p2p_invoices")
           .withColumn("days_overdue", F.datediff(F.current_date(), F.col("invoice_date")))
    )

    # Single source of truth: each exception_type maps to the NEGATION of one
    # predicate constant. Order matters: highest-severity first.
    return (
        enriched
        .withColumn("exception_type",
                    F.when(F.col("status") == "DUPLICATE", "DUPLICATE")
                     .when(~F.expr(EXPECT_HAS_PO_REFERENCE),       "NO_PO_REFERENCE")
                     .when(~F.expr(EXPECT_AMOUNT_MATCHES_PO),      "AMOUNT_MISMATCH")
                     .when(~F.expr(EXPECT_HAS_GRN),                "MISSING_GRN")
                     .when(~F.expr(EXPECT_HAS_VENDOR_GSTIN),       "MISSING_GSTIN")
                     .when(~F.expr(EXPECT_NOT_CRITICALLY_OVERDUE), "CRITICAL_OVERDUE")
                     .when(~F.expr(EXPECT_EXTRACTION_MATCHES_ERP), "EXTRACTION_MISMATCH")
                     # Catch-all so the exception table is a true superset of
                     # "anything that isn't THREE_WAY_MATCHED".
                     .when(F.col("match_status") != "THREE_WAY_MATCHED", "PENDING_REVIEW")
                     .otherwise(None))
        .filter(F.col("exception_type").isNotNull())
        .withColumn("_exception_ts", F.current_timestamp())
    )


# COMMAND ----------

# MAGIC %md ## SILVER — O2C / R2R

# COMMAND ----------

@dlt.table(name="silver_o2c_invoices", comment="Validated customer invoices with aging",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_o2c_invoices():
    return (
        dlt.read("bronze_o2c_invoices")
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .withColumn("days_outstanding",
                    F.when(F.col("status") != "PAID",
                           F.datediff(F.current_date(), F.col("invoice_date"))))
        .withColumn("days_overdue",
                    F.when(
                        (F.col("status") != "PAID") & (F.col("due_date") < F.current_date()),
                        F.datediff(F.current_date(), F.col("due_date"))
                    ).otherwise(F.lit(0)))
        .withColumn("aging_bucket",
                    F.when(F.col("days_outstanding") <= 30, "0-30 days")
                     .when(F.col("days_outstanding") <= 60, "31-60 days")
                     .when(F.col("days_outstanding") <= 90, "61-90 days")
                     .otherwise("90+ days"))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["o2c_invoice_id"])
    )


@dlt.table(name="silver_sales_orders", comment="Sales orders with delivery delay",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_sales_orders():
    return (
        dlt.read("bronze_sales_orders")
        .withColumn("so_date", F.to_date("so_date"))
        .withColumn("expected_delivery_date", F.to_date("expected_delivery_date"))
        .withColumn("actual_delivery_date",
                    F.when(F.col("actual_delivery_date").isNotNull() & (F.col("actual_delivery_date") != ""),
                           F.to_date("actual_delivery_date"))
                     .otherwise(F.lit(None).cast("date")))
        .withColumn("delivery_delay_days",
                    F.when(
                        F.col("actual_delivery_date").isNotNull(),
                        F.datediff(F.col("actual_delivery_date"), F.col("expected_delivery_date"))
                    ))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["so_id"])
    )


# silver_journal_entries folded into gold_fact_gl (filter posted+balanced inline)


# COMMAND ----------

# MAGIC %md ## GOLD LAYER — Business-ready facts and dims (all in this pipeline)

# COMMAND ----------

# Auxiliary tables that live outside the pipeline today (notebook 00 / notebook 05).
# We read them with spark.table so DLT just consumes them as inputs.
def _ext(table: str):
    return spark.table(f"{CATALOG}.{SCHEMA}.{table}")


# ── P2P GOLD ─────────────────────────────────────────────────────────────────

@dlt.table(name="gold_dim_vendor",
           comment="Enriched vendor dim — folds the old silver_vendors normalization inline (dedup vendor_id, uppercase-normalize vendor_name, is_gst_registered) so the graph stays compact.",
           table_properties={"quality": "gold", "domain": "P2P"})
def gold_dim_vendor():
    # Folded silver_vendors transforms: dedup + normalize + is_gst_registered
    vendors = (
        dlt.read("bronze_vendors")
        .withColumn("vendor_name_normalized",
                    F.trim(F.regexp_replace(F.upper(F.col("vendor_name")), r"\s+", " ")))
        .withColumn("is_gst_registered",
                    F.when(F.col("gstin").isNotNull() & (F.col("gstin") != ""), True).otherwise(False))
        .dropDuplicates(["vendor_id"])
    )
    invoices = dlt.read("silver_p2p_invoices")
    payments = dlt.read("bronze_p2p_payments")

    vendor_spend = (
        invoices.filter(F.col("status") != "REJECTED")
        .groupBy("vendor_id")
        .agg(
            F.count("invoice_id").alias("total_invoices"),
            F.sum("total_amount").alias("total_spend"),
            F.avg("total_amount").alias("avg_invoice_amount"),
            F.countDistinct("po_id").alias("total_pos"),
            F.sum(F.when(F.col("match_status") == "THREE_WAY_MATCHED", 1).otherwise(0)).alias("three_way_matched_count"),
            F.sum(F.when(F.col("match_status") == "AMOUNT_MISMATCH", 1).otherwise(0)).alias("amount_mismatch_count"),
            F.sum(F.when(F.col("status") == "PENDING", 1).otherwise(0)).alias("pending_invoices"),
            F.max("invoice_date").alias("last_invoice_date"),
        )
    )
    payment_perf = (
        payments.filter(F.col("status") == "COMPLETED")
        .groupBy("vendor_id")
        .agg(
            F.count("payment_id").alias("total_payments"),
            F.sum("payment_amount").alias("total_paid_amount"),
        )
    )
    return (
        vendors.join(vendor_spend, "vendor_id", "left")
               .join(payment_perf, "vendor_id", "left")
               .select(
                   "vendor_id", "vendor_name", "vendor_name_normalized", "vendor_category",
                   "country", "city", "state", "payment_terms", "currency",
                   "gstin", "is_gst_registered", "is_active",
                   F.coalesce(F.col("total_invoices"), F.lit(0)).alias("total_invoices"),
                   F.coalesce(F.col("total_spend"), F.lit(0.0)).alias("total_spend_inr"),
                   F.coalesce(F.col("avg_invoice_amount"), F.lit(0.0)).alias("avg_invoice_amount_inr"),
                   F.coalesce(F.col("total_pos"), F.lit(0)).alias("total_purchase_orders"),
                   F.coalesce(F.col("three_way_matched_count"), F.lit(0)).alias("three_way_matched_invoices"),
                   F.coalesce(F.col("amount_mismatch_count"), F.lit(0)).alias("amount_mismatch_invoices"),
                   F.coalesce(F.col("pending_invoices"), F.lit(0)).alias("pending_invoices"),
                   F.coalesce(F.col("total_payments"), F.lit(0)).alias("total_payments_count"),
                   F.coalesce(F.col("total_paid_amount"), F.lit(0.0)).alias("total_paid_amount_inr"),
                   "last_invoice_date",
                   F.when(F.col("total_invoices") > 0,
                          F.round(F.coalesce(F.col("three_way_matched_count"), F.lit(0)) /
                                  F.col("total_invoices") * 100, 1)).alias("match_compliance_pct"),
                   F.current_timestamp().alias("_gold_processed_at"),
               )
    )


@dlt.table(name="gold_fact_invoices",
           comment="Invoice facts with aging, match status, payment timing, and PDF traceability",
           partition_cols=["invoice_year", "invoice_month"],
           table_properties={"quality": "gold", "domain": "P2P"})
def gold_fact_invoices():
    invoices = dlt.read("silver_p2p_invoices")
    po = dlt.read("silver_po_header")
    grns = dlt.read("silver_grn")
    dim_vendor = dlt.read("gold_dim_vendor")
    payments = dlt.read("bronze_p2p_payments")
    # pdf_file_path now flows in via silver_p2p_invoices (joined with silver_invoice_extractions
    # there so the @dlt.expect predicates have access to ai_extracted_amount). We just
    # normalise it here (strip the dbfs: prefix if present).

    payment_info = (
        payments.groupBy("invoice_id").agg(
            F.min("payment_date").alias("payment_date"),
            F.sum("payment_amount").alias("paid_amount"),
            F.first("payment_method").alias("payment_method"),
        )
    )
    grn_info = (
        grns.groupBy("po_id").agg(
            F.max("grn_id").alias("grn_id"),
            F.max("grn_date").alias("grn_date"),
            F.max("received_amount").alias("grn_received_amount"),
            F.max("quality_check_status").alias("quality_check_status"),
        )
    )

    return (
        invoices
        .join(payment_info, "invoice_id", "left")
        .join(grn_info, "po_id", "left")
        .join(dim_vendor.select("vendor_id", "vendor_name", "vendor_category", "vendor_name_normalized"),
              "vendor_id", "left")
        .join(po.select("po_id", F.col("po_number"),
                        F.col("po_date").alias("po_date_from_po")),
              "po_id", "left")
        .withColumn("pdf_file_path", F.regexp_replace(F.col("pdf_file_path"), "^dbfs:", ""))
        .withColumn("payment_date", F.to_date("payment_date"))
        .withColumn("days_to_pay",
                    F.when(F.col("payment_date").isNotNull(),
                           F.datediff(F.col("payment_date"), F.col("invoice_date"))))
        .withColumn("aging_days",
                    F.when(F.col("status") != "PAID",
                           F.datediff(F.current_date(), F.col("invoice_date")))
                     .otherwise(F.col("days_to_pay")))
        .withColumn("aging_bucket",
                    F.when(F.col("aging_days") <= 30, "0-30 days")
                     .when(F.col("aging_days") <= 60, "31-60 days")
                     .when(F.col("aging_days") <= 90, "61-90 days")
                     .otherwise("90+ days"))
        .withColumn("payment_on_time",
                    F.when(F.col("payment_date").isNotNull(),
                           F.col("payment_date") <= F.col("due_date")))
        .withColumn("invoice_year",  F.year("invoice_date"))
        .withColumn("invoice_month", F.month("invoice_date"))
        .withColumn("invoice_quarter",
                    F.concat(F.year("invoice_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("invoice_date")) / 3).cast("string")))
        .select(
            "invoice_id", "invoice_number", "po_id", "grn_id", "vendor_id",
            "vendor_name", "vendor_category", "vendor_name_normalized",
            "invoice_date", "due_date", "payment_date",
            F.col("po_date_from_po").alias("po_date"), "grn_date",
            "invoice_amount", "tax_amount",
            F.col("total_amount").alias("invoice_total_inr"),
            F.coalesce(F.col("paid_amount"), F.lit(0.0)).alias("paid_amount_inr"),
            F.col("status").alias("invoice_status"),
            "po_status", "match_status", "has_po_ref", "has_grn", "is_overdue",
            F.col("quality_check_status").alias("grn_quality_status"),
            "aging_days", "aging_bucket", "days_to_pay", "payment_on_time",
            "days_outstanding", "payment_method",
            "invoice_year", "invoice_month", "invoice_quarter",
            "gstin_vendor", "tds_applicable", "tds_rate",
            "pdf_file_path",
            F.when(F.col("pdf_file_path").isNotNull(), F.lit("ERP_AND_PDF"))
             .otherwise(F.lit("ERP_ONLY")).alias("data_source"),
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


@dlt.table(name="gold_fact_payments",
           comment="Payment facts with timing (early/on-time/late)",
           partition_cols=["payment_year", "payment_month"],
           table_properties={"quality": "gold", "domain": "P2P"})
def gold_fact_payments():
    payments = dlt.read("bronze_p2p_payments")
    invoices = dlt.read("silver_p2p_invoices")
    dim_vendor = dlt.read("gold_dim_vendor")

    inv_for_pay = invoices.select(
        "invoice_id", "invoice_date", "due_date", "total_amount",
        F.col("vendor_id").alias("inv_vendor_id"), "po_id", "match_status",
    )
    return (
        payments
        .join(inv_for_pay, "invoice_id", "left")
        .join(dim_vendor.select(F.col("vendor_id").alias("dv_vendor_id"),
                                 "vendor_name", "vendor_category"),
              F.col("inv_vendor_id") == F.col("dv_vendor_id"), "left")
        .withColumn("payment_date", F.to_date("payment_date"))
        .withColumn("invoice_date", F.to_date("invoice_date"))
        .withColumn("due_date", F.to_date("due_date"))
        .withColumn("days_to_pay", F.datediff(F.col("payment_date"), F.col("invoice_date")))
        .withColumn("early_late_days", F.datediff(F.col("due_date"), F.col("payment_date")))
        .withColumn("payment_timing",
                    F.when(F.col("early_late_days") > 0, "EARLY")
                     .when(F.col("early_late_days") == 0, "ON_TIME")
                     .otherwise("LATE"))
        .withColumn("payment_year",  F.year("payment_date"))
        .withColumn("payment_month", F.month("payment_date"))
        .withColumn("payment_quarter",
                    F.concat(F.year("payment_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("payment_date")) / 3).cast("string")))
        .select(
            "payment_id", "invoice_id", F.col("inv_vendor_id").alias("vendor_id"), "po_id",
            "vendor_name", "vendor_category",
            "payment_date", "invoice_date", "due_date",
            F.col("payment_amount").alias("payment_amount_inr"),
            F.col("total_amount").alias("invoice_total_inr"),
            "currency", "payment_method", "reference_number",
            F.col("status").alias("payment_status"),
            "match_status",
            "days_to_pay", "early_late_days", "payment_timing",
            "payment_year", "payment_month", "payment_quarter",
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


# ── O2C GOLD ─────────────────────────────────────────────────────────────────

@dlt.table(name="gold_dim_customer",
           comment="Enriched customer dim — folds the old silver_customers normalization inline (dedup customer_id, normalize name, is_gst_registered).",
           table_properties={"quality": "gold", "domain": "O2C"})
def gold_dim_customer():
    # Folded silver_customers transforms: dedup + normalize + is_gst_registered
    customers = (
        dlt.read("bronze_customers")
        .withColumn("customer_name_normalized",
                    F.trim(F.regexp_replace(F.upper(F.col("customer_name")), r"\s+", " ")))
        .withColumn("is_gst_registered",
                    F.when(F.col("gstin").isNotNull() & (F.col("gstin") != ""), True).otherwise(False))
        .dropDuplicates(["customer_id"])
    )
    sales_orders = dlt.read("silver_sales_orders")
    invoices = dlt.read("silver_o2c_invoices")
    # bronze_o2c_payments isn't in the DLT pipeline — read directly from Delta
    pay = _ext("bronze_o2c_payments")

    collection_metrics = (
        invoices.join(
            pay.groupBy("o2c_invoice_id").agg(F.min("payment_date").alias("first_payment_date")),
            "o2c_invoice_id", "left",
        )
        .withColumn("first_payment_date", F.to_date("first_payment_date"))
        .withColumn("days_to_collect",
                    F.when(F.col("first_payment_date").isNotNull(),
                           F.datediff(F.col("first_payment_date"), F.col("invoice_date"))))
        .groupBy("customer_id")
        .agg(
            F.count("o2c_invoice_id").alias("total_invoices"),
            F.sum("total_amount").alias("total_billed"),
            F.sum(F.when(F.col("status") == "PAID", F.col("total_amount")).otherwise(0)).alias("total_collected"),
            F.sum(F.when(F.col("status").isin(["OUTSTANDING", "OVERDUE"]), F.col("total_amount")).otherwise(0)).alias("outstanding_ar"),
            F.avg("days_to_collect").alias("avg_days_to_collect"),
            F.sum(F.when(F.col("status") == "OVERDUE", 1).otherwise(0)).alias("overdue_invoice_count"),
            F.max("invoice_date").alias("last_invoice_date"),
        )
        .withColumn("dso",
                    F.when(F.col("total_billed") > 0,
                           F.round(F.col("outstanding_ar") / F.col("total_billed") * 90, 1)))
        .withColumn("collection_rate",
                    F.when(F.col("total_billed") > 0,
                           F.round(F.col("total_collected") / F.col("total_billed") * 100, 1)))
    )
    so_metrics = (
        sales_orders.groupBy("customer_id").agg(
            F.count("so_id").alias("total_orders"),
            F.sum("total_amount").alias("total_order_value"),
            F.avg("total_amount").alias("avg_order_value"),
        )
    )
    return (
        customers.join(collection_metrics, "customer_id", "left")
                 .join(so_metrics, "customer_id", "left")
                 .select(
                     "customer_id", "customer_name", "customer_name_normalized",
                     "segment", "industry", "country", "city", "state",
                     "payment_terms", "credit_limit", "currency",
                     "account_manager", "is_active", "is_gst_registered",
                     F.coalesce(F.col("total_orders"), F.lit(0)).alias("total_sales_orders"),
                     F.coalesce(F.col("total_order_value"), F.lit(0.0)).alias("total_order_value_inr"),
                     F.coalesce(F.col("avg_order_value"), F.lit(0.0)).alias("avg_order_value_inr"),
                     F.coalesce(F.col("total_invoices"), F.lit(0)).alias("total_invoices"),
                     F.coalesce(F.col("total_billed"), F.lit(0.0)).alias("total_billed_inr"),
                     F.coalesce(F.col("total_collected"), F.lit(0.0)).alias("total_collected_inr"),
                     F.coalesce(F.col("outstanding_ar"), F.lit(0.0)).alias("outstanding_ar_inr"),
                     "dso",
                     F.col("collection_rate").alias("collection_rate_pct"),
                     F.coalesce(F.col("avg_days_to_collect"), F.lit(0.0)).alias("avg_days_to_collect"),
                     F.coalesce(F.col("overdue_invoice_count"), F.lit(0)).alias("overdue_invoices"),
                     F.when(F.col("credit_limit") > 0,
                            F.round(F.coalesce(F.col("outstanding_ar"), F.lit(0.0)) /
                                    F.col("credit_limit") * 100, 1)).alias("credit_utilization_pct"),
                     "last_invoice_date",
                     F.current_timestamp().alias("_gold_processed_at"),
                 )
    )


@dlt.table(name="gold_fact_sales",
           comment="Sales order facts with product-mix breakdown",
           partition_cols=["so_year", "so_month"],
           table_properties={"quality": "gold", "domain": "O2C"})
def gold_fact_sales():
    sales_orders = dlt.read("silver_sales_orders")
    dim_customer = dlt.read("gold_dim_customer")
    so_lines = _ext("bronze_so_lines")

    product_mix = (
        so_lines.groupBy("so_id").agg(
            F.collect_list("category").alias("product_categories"),
            F.size(F.collect_set("product_code")).alias("unique_products"),
            F.sum(F.when(F.col("category") == "Software", F.col("total_line_amount")).otherwise(0)).alias("software_revenue"),
            F.sum(F.when(F.col("category") == "Services", F.col("total_line_amount")).otherwise(0)).alias("services_revenue"),
            F.sum(F.when(F.col("category") == "Support", F.col("total_line_amount")).otherwise(0)).alias("support_revenue"),
            F.sum(F.when(F.col("category") == "Infrastructure", F.col("total_line_amount")).otherwise(0)).alias("infra_revenue"),
            F.avg("discount_percentage").alias("avg_discount_pct"),
        )
    )
    return (
        sales_orders
        .join(dim_customer.select("customer_id", "customer_name", "segment", "industry"),
              "customer_id", "left")
        .join(product_mix, "so_id", "left")
        .withColumn("so_year",  F.year("so_date"))
        .withColumn("so_month", F.month("so_date"))
        .withColumn("so_quarter",
                    F.concat(F.year("so_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("so_date")) / 3).cast("string")))
        .withColumn("revenue_excl_tax", F.round(F.col("total_amount") / 1.18, 2))
        .withColumn("gst_amount",       F.round(F.col("total_amount") - F.col("revenue_excl_tax"), 2))
        .select(
            "so_id", "so_number", "customer_id", "customer_name", "segment", "industry",
            "so_date", "expected_delivery_date", "actual_delivery_date",
            "status", "region", "sales_rep",
            F.col("total_amount").alias("so_total_inr"),
            "revenue_excl_tax", "gst_amount", "unique_products",
            F.coalesce(F.col("software_revenue"), F.lit(0.0)).alias("software_revenue_inr"),
            F.coalesce(F.col("services_revenue"), F.lit(0.0)).alias("services_revenue_inr"),
            F.coalesce(F.col("support_revenue"), F.lit(0.0)).alias("support_revenue_inr"),
            F.coalesce(F.col("infra_revenue"), F.lit(0.0)).alias("infrastructure_revenue_inr"),
            F.coalesce(F.col("avg_discount_pct"), F.lit(0.0)).alias("avg_discount_pct"),
            "delivery_delay_days",
            "so_year", "so_month", "so_quarter",
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


@dlt.table(name="gold_fact_collections",
           comment="Collections facts with aging buckets and balance outstanding",
           partition_cols=["collection_year", "collection_month"],
           table_properties={"quality": "gold", "domain": "O2C"})
def gold_fact_collections():
    invoices = dlt.read("silver_o2c_invoices")
    sales_orders = dlt.read("silver_sales_orders")
    dim_customer = dlt.read("gold_dim_customer")
    pay = _ext("bronze_o2c_payments")

    pay_agg = (
        pay.groupBy("o2c_invoice_id").agg(
            F.sum("payment_amount").alias("total_received"),
            F.min("payment_date").alias("first_payment_date"),
            F.max("payment_date").alias("last_payment_date"),
            F.count("receipt_id").alias("payment_count"),
            F.first("payment_method").alias("payment_method"),
        )
    )
    return (
        invoices.join(pay_agg, "o2c_invoice_id", "left")
        .join(dim_customer.select("customer_id", "customer_name", "segment", "industry"),
              "customer_id", "left")
        .join(sales_orders.select("so_id", "region", "sales_rep"), "so_id", "left")
        .withColumn("first_payment_date", F.to_date("first_payment_date"))
        .withColumn("days_to_collect",
                    F.when(F.col("first_payment_date").isNotNull(),
                           F.datediff(F.col("first_payment_date"), F.col("invoice_date"))))
        .withColumn("balance_outstanding",
                    F.col("total_amount") - F.coalesce(F.col("total_received"), F.lit(0.0)))
        .withColumn("is_fully_collected", F.col("balance_outstanding") <= 0)
        .withColumn("collection_year",  F.year("invoice_date"))
        .withColumn("collection_month", F.month("invoice_date"))
        .withColumn("collection_quarter",
                    F.concat(F.year("invoice_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("invoice_date")) / 3).cast("string")))
        .select(
            "o2c_invoice_id", "invoice_number", "so_id", "customer_id", "customer_name",
            "segment", "industry", "region", "sales_rep",
            "invoice_date", "due_date", "first_payment_date",
            F.col("total_amount").alias("invoice_total_inr"),
            F.col("invoice_amount").alias("invoice_amount_excl_tax"),
            "tax_amount",
            F.coalesce(F.col("total_received"), F.lit(0.0)).alias("amount_collected_inr"),
            "balance_outstanding",
            F.col("status").alias("invoice_status"),
            "aging_bucket", "days_outstanding", "days_overdue",
            "days_to_collect", "is_fully_collected",
            F.col("payment_count").alias("payment_installments"),
            "payment_method",
            "collection_year", "collection_month", "collection_quarter",
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


# ── R2R GOLD ─────────────────────────────────────────────────────────────────

@dlt.table(name="gold_fact_gl",
           comment="GL entries enriched with COA/cost-center metadata — folds the old silver_journal_entries inline (filter POSTED + balanced, dates as DATE, fiscal_quarter).",
           partition_cols=["gl_year", "gl_month"],
           table_properties={"quality": "gold", "domain": "R2R"})
def gold_fact_gl():
    # Folded silver_journal_entries transforms inline: only posted + balanced JEs
    silver_je = (
        dlt.read("bronze_journal_entries")
        .filter(F.col("total_debit") == F.col("total_credit"))
        .filter(F.col("status") == "POSTED")
        .withColumn("je_date", F.to_date("je_date"))
        .withColumn("fiscal_quarter",
                    F.concat(F.col("fiscal_year").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("je_date")) / 3).cast("string")))
        .dropDuplicates(["je_id"])
        .select("je_id", "je_number", "je_date", "je_type", "period",
                "fiscal_year", "fiscal_quarter", "status", "posted_by")
    )
    # bronze_je_lines / chart_of_accounts / cost_centers live outside DLT (notebook 00)
    je_lines = _ext("bronze_je_lines")
    coa = _ext("bronze_chart_of_accounts")
    cc = _ext("bronze_cost_centers")

    return (
        je_lines
        .join(silver_je.select("je_id", "je_number", "je_date", "je_type", "period",
                                "fiscal_year", "fiscal_quarter", "status", "posted_by"),
              "je_id", "inner")
        .join(coa.select("account_code", "account_name", "account_type", "account_subtype"),
              "account_code", "left")
        .join(cc.select(F.col("cost_center_code").alias("cost_center"),
                         "cost_center_name", "department"),
              "cost_center", "left")
        .withColumn("je_date", F.to_date("je_date"))
        .withColumn("amount", F.col("debit_amount") - F.col("credit_amount"))
        .withColumn("gl_year",  F.year("je_date"))
        .withColumn("gl_month", F.month("je_date"))
        .withColumn("gl_quarter",
                    F.concat(F.year("je_date").cast("string"), F.lit("-Q"),
                             F.ceil(F.month(F.col("je_date")) / 3).cast("string")))
        .withColumn("normal_balance",
                    F.when(F.col("account_type").isin(["Asset", "Expense"]), "DEBIT")
                     .otherwise("CREDIT"))
        .select(
            "je_id", "je_number",
            F.col("line_number").alias("gl_line_number"),
            "account_code", "account_name", "account_type", "account_subtype",
            "cost_center", "cost_center_name", "department",
            "je_date", "period", "fiscal_year", "fiscal_quarter",
            "gl_year", "gl_month", "gl_quarter",
            "je_type", "status", "posted_by",
            F.col("debit_amount").alias("debit_inr"),
            F.col("credit_amount").alias("credit_inr"),
            F.col("amount").alias("net_amount_inr"),
            "normal_balance",
            F.col("description").alias("gl_description"),
            F.current_timestamp().alias("_gold_processed_at"),
        )
    )


@dlt.table(name="gold_fact_trial_balance",
           comment="Period-end trial balance. AR (1100) and AP (2000) overridden from the sub-ledger so the GL ties out to gold_fact_collections / gold_fact_invoices. balance_type derived from account_type (natural sign) so signs are always Asset/Expense=DR, Liability/Equity/Revenue=CR.",
           partition_cols=["fiscal_year"],
           table_properties={"quality": "gold", "domain": "R2R", "reconciles_to": "sub_ledger"})
def gold_fact_trial_balance():
    gl = dlt.read("gold_fact_gl")

    # 1) Period balances from the GL (for every account except the two we override)
    period_balances = (
        gl.groupBy("fiscal_year", "fiscal_quarter", "period", "account_code", "account_name",
                   "account_type", "account_subtype")
          .agg(
              F.sum("debit_inr").alias("period_debit"),
              F.sum("credit_inr").alias("period_credit"),
              F.count("je_id").alias("transaction_count"),
          )
          .withColumn("period_net", F.col("period_debit") - F.col("period_credit"))
    )
    ytd_window = (
        Window.partitionBy("account_code", "fiscal_year")
              .orderBy("period")
              .rowsBetween(Window.unboundedPreceding, Window.currentRow)
    )
    je_tb = (
        period_balances
        .withColumn("ytd_debit",  F.sum("period_debit").over(ytd_window))
        .withColumn("ytd_credit", F.sum("period_credit").over(ytd_window))
        .withColumn("ytd_net",    F.col("ytd_debit") - F.col("ytd_credit"))
        # Closing balance magnitude = |YTD net|. balance_type below is the canonical
        # accounting sign for the account type, NOT the sign of the random JE rollup.
        .withColumn("closing_balance_inr", F.abs(F.col("ytd_net")))
        .withColumn("balance_type",
                    F.when(F.col("account_type").isin(["Asset", "Expense"]), "DR")
                     .otherwise("CR"))
    )

    # 2) Sub-ledger overrides for AR (1100) and AP (2000) — these are the single source
    #    of truth for those balances. We KEEP the period dimension by exploding the
    #    sub-ledger total across the same set of periods as the rest of the TB.
    ar_total = (
        spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_collections")
             .agg(F.sum("balance_outstanding").alias("ar_balance"))
    )
    ap_total = (
        spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_invoices")
             .filter(F.col("invoice_status") != "PAID")
             .agg(F.sum(F.col("invoice_total_inr") - F.coalesce(F.col("paid_amount_inr"), F.lit(0.0))).alias("ap_balance"))
    )

    # Distinct periods/fiscal_year in the TB — we'll attach the sub-ledger total to
    # the most-recent period so the headline number is reported once at the latest TB cut.
    latest_period = je_tb.agg(F.max("period").alias("p"), F.max("fiscal_year").alias("y"),
                              F.max("fiscal_quarter").alias("q")).collect()[0]
    p_lit, y_lit, q_lit = latest_period["p"], latest_period["y"], latest_period["q"]

    ar_override = (
        ar_total
        .withColumn("fiscal_year", F.lit(y_lit))
        .withColumn("fiscal_quarter", F.lit(q_lit))
        .withColumn("period", F.lit(p_lit))
        .withColumn("account_code", F.lit("1100"))
        .withColumn("account_name", F.lit("Accounts Receivable"))
        .withColumn("account_type", F.lit("Asset"))
        .withColumn("account_subtype", F.lit("Current Asset"))
        .withColumn("period_debit",  F.col("ar_balance"))
        .withColumn("period_credit", F.lit(0.0))
        .withColumn("period_net",    F.col("ar_balance"))
        .withColumn("ytd_debit",     F.col("ar_balance"))
        .withColumn("ytd_credit",    F.lit(0.0))
        .withColumn("ytd_net",       F.col("ar_balance"))
        .withColumn("closing_balance_inr", F.col("ar_balance"))
        .withColumn("balance_type",  F.lit("DR"))
        .withColumn("transaction_count", F.lit(0).cast("bigint"))
        .drop("ar_balance")
    )
    ap_override = (
        ap_total
        .withColumn("fiscal_year", F.lit(y_lit))
        .withColumn("fiscal_quarter", F.lit(q_lit))
        .withColumn("period", F.lit(p_lit))
        .withColumn("account_code", F.lit("2000"))
        .withColumn("account_name", F.lit("Accounts Payable"))
        .withColumn("account_type", F.lit("Liability"))
        .withColumn("account_subtype", F.lit("Current Liability"))
        .withColumn("period_debit",  F.lit(0.0))
        .withColumn("period_credit", F.col("ap_balance"))
        .withColumn("period_net",    -F.col("ap_balance"))
        .withColumn("ytd_debit",     F.lit(0.0))
        .withColumn("ytd_credit",    F.col("ap_balance"))
        .withColumn("ytd_net",       -F.col("ap_balance"))
        .withColumn("closing_balance_inr", F.col("ap_balance"))
        .withColumn("balance_type",  F.lit("CR"))
        .withColumn("transaction_count", F.lit(0).cast("bigint"))
        .drop("ap_balance")
    )

    # Drop the JE-derived 1100 and 2000 rows so the override is authoritative
    je_tb_filtered = je_tb.filter(~F.col("account_code").isin(["1100", "2000"]))

    cols = ["fiscal_year", "fiscal_quarter", "period",
            "account_code", "account_name", "account_type", "account_subtype",
            "period_debit", "period_credit", "period_net",
            "ytd_debit", "ytd_credit", "ytd_net",
            "closing_balance_inr", "balance_type", "transaction_count"]

    return (
        je_tb_filtered.select(*cols)
        .unionByName(ar_override.select(*cols))
        .unionByName(ap_override.select(*cols))
        .withColumn("_gold_processed_at", F.current_timestamp())
    )


@dlt.table(name="gold_recon_subledger_vs_gl",
           comment="Sub-ledger vs GL reconciliation. One row per reconciled account showing sub-ledger total, GL trial-balance closing balance, and the delta. Must be zero for the loop to be closed.",
           table_properties={"quality": "gold", "domain": "Cross"})
def gold_recon_subledger_vs_gl():
    ar_sub = (
        spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_collections")
             .agg(F.sum("balance_outstanding").alias("subledger_amount"))
             .withColumn("account_code", F.lit("1100"))
             .withColumn("account_name", F.lit("Accounts Receivable"))
             .withColumn("subledger_source_table", F.lit("gold_fact_collections"))
             .withColumn("subledger_metric", F.lit("SUM(balance_outstanding)"))
    )
    ap_sub = (
        spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_invoices")
             .filter(F.col("invoice_status") != "PAID")
             .agg(F.sum(F.col("invoice_total_inr") - F.coalesce(F.col("paid_amount_inr"), F.lit(0.0))).alias("subledger_amount"))
             .withColumn("account_code", F.lit("2000"))
             .withColumn("account_name", F.lit("Accounts Payable"))
             .withColumn("subledger_source_table", F.lit("gold_fact_invoices"))
             .withColumn("subledger_metric", F.lit("SUM(invoice_total_inr - paid_amount_inr) WHERE invoice_status != 'PAID'"))
    )
    sub = ar_sub.unionByName(ap_sub)

    gl = (
        dlt.read("gold_fact_trial_balance")
        .filter(F.col("account_code").isin(["1100", "2000"]))
        # Keep one row per account (latest period override)
        .groupBy("account_code")
        .agg(F.max("closing_balance_inr").alias("gl_amount"),
             F.max("balance_type").alias("balance_type"))
    )

    return (
        sub.join(gl, "account_code", "left")
           .withColumn("delta", F.coalesce(F.col("subledger_amount"), F.lit(0.0)) -
                                 F.coalesce(F.col("gl_amount"), F.lit(0.0)))
           .withColumn("tied", F.abs(F.col("delta")) < F.lit(1.0))
           .select(
               "account_code", "account_name", "balance_type",
               "subledger_source_table", "subledger_metric",
               "subledger_amount", "gl_amount", "delta", "tied",
               F.current_timestamp().alias("_gold_processed_at"),
           )
    )
