# Databricks notebook source
# MAGIC %md
# MAGIC # Finance & Accounting DLT Pipeline - Bronze to Silver
# MAGIC
# MAGIC Uses DLT (Delta Live Tables) for:
# MAGIC - **Bronze**: Raw ingestion from source tables with quality expectations
# MAGIC - **Silver**: Cleaned, validated, enriched data with 3-way matching
# MAGIC
# MAGIC Quarantine pattern: bad records are routed to `*_exceptions` tables

# COMMAND ----------

import dlt
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "akash_s_demo"
SCHEMA = "finance_and_accounting"

# COMMAND ----------

# MAGIC %md ## BRONZE LAYER - Streaming Ingestion with DLT Expectations

# COMMAND ----------

@dlt.table(name="bronze_vendors_dlt", comment="Raw vendor master data from ERP",
           table_properties={"quality": "bronze", "domain": "P2P"})
@dlt.expect_or_drop("valid_vendor_id", "vendor_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_name", "vendor_name IS NOT NULL AND LENGTH(vendor_name) > 0")
@dlt.expect("valid_email", "contact_email LIKE '%@%'")
def bronze_vendors_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_vendors")


@dlt.table(name="bronze_po_header_dlt", comment="Raw purchase order headers from ERP",
           table_properties={"quality": "bronze", "domain": "P2P"})
@dlt.expect_or_drop("valid_po_id", "po_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_ref", "vendor_id IS NOT NULL")
@dlt.expect("valid_po_date", "po_date IS NOT NULL")
@dlt.expect("positive_amount", "total_amount > 0")
def bronze_po_header_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_po_header")


@dlt.table(name="bronze_po_line_dlt", comment="Raw purchase order line items",
           table_properties={"quality": "bronze", "domain": "P2P"})
@dlt.expect_or_drop("valid_po_ref", "po_id IS NOT NULL")
@dlt.expect("positive_quantity", "quantity > 0")
@dlt.expect("positive_unit_price", "unit_price > 0")
def bronze_po_line_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_po_line")


@dlt.table(name="bronze_grn_dlt", comment="Raw Goods Receipt Notes",
           table_properties={"quality": "bronze", "domain": "P2P"})
@dlt.expect_or_drop("valid_grn_id", "grn_id IS NOT NULL")
@dlt.expect_or_drop("valid_po_ref", "po_id IS NOT NULL")
@dlt.expect("valid_grn_date", "grn_date IS NOT NULL")
def bronze_grn_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_grn")


@dlt.table(name="bronze_p2p_invoices_dlt", comment="Raw vendor invoices - valid records",
           table_properties={"quality": "bronze", "domain": "P2P"})
@dlt.expect_or_drop("valid_invoice_id", "invoice_id IS NOT NULL")
@dlt.expect_or_drop("valid_vendor_ref", "vendor_id IS NOT NULL")
@dlt.expect_or_drop("positive_total_amount", "total_amount > 0")
@dlt.expect("valid_invoice_date", "invoice_date IS NOT NULL")
def bronze_p2p_invoices_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_p2p_invoices")


@dlt.table(name="bronze_p2p_invoices_quarantine", comment="Quarantined invoice records",
           table_properties={"quality": "quarantine", "domain": "P2P"})
def bronze_p2p_invoices_quarantine():
    return (
        spark.readStream.format("delta")
        .table(f"{CATALOG}.{SCHEMA}.bronze_p2p_invoices")
        .filter("invoice_id IS NULL OR vendor_id IS NULL OR total_amount <= 0 OR invoice_date IS NULL")
        .withColumn("_quarantine_reason", F.lit("Failed quality: null IDs or non-positive amounts"))
        .withColumn("_quarantine_ts", F.current_timestamp())
    )


@dlt.table(name="bronze_p2p_payments_dlt", comment="Raw vendor payment records",
           table_properties={"quality": "bronze", "domain": "P2P"})
@dlt.expect_or_drop("valid_payment_id", "payment_id IS NOT NULL")
@dlt.expect_or_drop("valid_invoice_ref", "invoice_id IS NOT NULL")
@dlt.expect("positive_payment", "payment_amount > 0")
def bronze_p2p_payments_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_p2p_payments")


@dlt.table(name="bronze_customers_dlt", comment="Raw customer master data from CRM",
           table_properties={"quality": "bronze", "domain": "O2C"})
@dlt.expect_or_drop("valid_customer_id", "customer_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_name", "customer_name IS NOT NULL")
def bronze_customers_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_customers")


@dlt.table(name="bronze_sales_orders_dlt", comment="Raw sales order headers",
           table_properties={"quality": "bronze", "domain": "O2C"})
@dlt.expect_or_drop("valid_so_id", "so_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_ref", "customer_id IS NOT NULL")
@dlt.expect("positive_so_amount", "total_amount > 0")
def bronze_sales_orders_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_sales_orders")


@dlt.table(name="bronze_o2c_invoices_dlt", comment="Raw customer invoices",
           table_properties={"quality": "bronze", "domain": "O2C"})
@dlt.expect_or_drop("valid_o2c_invoice_id", "o2c_invoice_id IS NOT NULL")
@dlt.expect_or_drop("valid_customer_ref", "customer_id IS NOT NULL")
@dlt.expect("positive_o2c_amount", "total_amount > 0")
def bronze_o2c_invoices_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_o2c_invoices")


@dlt.table(name="bronze_journal_entries_dlt", comment="Raw journal entries from ERP",
           table_properties={"quality": "bronze", "domain": "R2R"})
@dlt.expect_or_drop("valid_je_id", "je_id IS NOT NULL")
@dlt.expect("balanced_entry", "total_debit = total_credit")
@dlt.expect("positive_amounts", "total_debit >= 0 AND total_credit >= 0")
def bronze_journal_entries_dlt():
    return spark.readStream.format("delta").table(f"{CATALOG}.{SCHEMA}.bronze_journal_entries")


@dlt.table(name="bronze_je_exceptions", comment="Unbalanced or invalid journal entries",
           table_properties={"quality": "quarantine", "domain": "R2R"})
def bronze_je_exceptions():
    return (
        spark.readStream.format("delta")
        .table(f"{CATALOG}.{SCHEMA}.bronze_journal_entries")
        .filter("total_debit != total_credit OR total_debit < 0")
        .withColumn("_exception_reason", F.lit("Unbalanced journal entry"))
        .withColumn("_exception_ts", F.current_timestamp())
    )


# COMMAND ----------

# MAGIC %md ## SILVER LAYER - Batch Reads for Enrichment and Deduplication

# COMMAND ----------

# Note: Silver tables use dlt.read() (batch) from bronze DLT tables
# This allows window functions and joins for deduplication and matching

@dlt.table(name="silver_vendors", comment="Cleaned and normalized vendor master",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_vendors():
    return (
        dlt.read("bronze_vendors_dlt")
        .withColumn("vendor_name_normalized",
                    F.trim(F.regexp_replace(F.upper(F.col("vendor_name")), r"\s+", " ")))
        .withColumn("is_gst_registered",
                    F.when(F.col("gstin").isNotNull() & (F.col("gstin") != ""), True).otherwise(False))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["vendor_id"])
    )


@dlt.table(name="silver_customers", comment="Cleaned and normalized customer master",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_customers():
    return (
        dlt.read("bronze_customers_dlt")
        .withColumn("customer_name_normalized",
                    F.trim(F.regexp_replace(F.upper(F.col("customer_name")), r"\s+", " ")))
        .withColumn("is_gst_registered",
                    F.when(F.col("gstin").isNotNull() & (F.col("gstin") != ""), True).otherwise(False))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["customer_id"])
    )


@dlt.table(name="silver_po_header", comment="Validated purchase order headers",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_po_header():
    return (
        dlt.read("bronze_po_header_dlt")
        .withColumn("po_date", F.to_date("po_date"))
        .withColumn("delivery_date", F.to_date("delivery_date"))
        .withColumn("approved_date",
                    F.when(F.col("approved_date") != "", F.to_date("approved_date")).otherwise(F.lit(None).cast("date")))
        .withColumn("is_overdue",
                    F.when(
                        F.col("status").isin(["APPROVED", "PARTIALLY_RECEIVED"]) &
                        (F.col("delivery_date") < F.current_date()),
                        True
                    ).otherwise(False))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["po_id"])
    )


@dlt.table(name="silver_grn", comment="Validated goods receipt notes",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_grn():
    return (
        dlt.read("bronze_grn_dlt")
        .withColumn("grn_date", F.to_date("grn_date"))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["grn_id"])
    )


@dlt.table(name="silver_p2p_invoices",
           comment="Deduplicated P2P invoices with 3-way match status",
           table_properties={"quality": "silver", "domain": "P2P"})
def silver_p2p_invoices():
    invoices = dlt.read("bronze_p2p_invoices_dlt")
    po_headers = dlt.read("silver_po_header")
    grns = dlt.read("silver_grn")

    # Deduplicate: keep one record per invoice_number (latest ingested)
    w = Window.partitionBy("invoice_number").orderBy(F.col("_ingested_at").desc())
    deduped = (
        invoices
        .filter(F.col("status") != "DUPLICATE")
        .withColumn("_rn", F.row_number().over(w))
        .filter(F.col("_rn") == 1)
        .drop("_rn")
    )

    # 2-way: join to PO
    with_po = deduped.join(
        po_headers.select(
            "po_id",
            F.col("total_amount").alias("po_total_amount"),
            F.col("status").alias("po_status")
        ),
        on="po_id", how="left"
    )

    # 3-way: check if GRN exists for the PO
    grn_summary = grns.groupBy("po_id").agg(
        F.count("grn_id").alias("grn_count"),
        F.max("received_amount").alias("grn_received_amount")
    )

    return (
        with_po.join(grn_summary, on="po_id", how="left")
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


@dlt.table(name="silver_invoice_exceptions",
           comment="Invoice records with validation issues",
           table_properties={"quality": "quarantine", "domain": "P2P"})
def silver_invoice_exceptions():
    invoices = dlt.read("bronze_p2p_invoices_dlt")
    po_headers = dlt.read("silver_po_header")

    with_po_exc = invoices.join(
        po_headers.select("po_id", F.col("total_amount").alias("po_total_amount")),
        on="po_id", how="left"
    )

    return (
        with_po_exc
        .withColumn("exception_type",
                    F.when(F.col("status") == "DUPLICATE", "DUPLICATE_INVOICE")
                     .when((F.col("po_id").isNull()) | (F.col("po_id") == ""), "MISSING_PO_REFERENCE")
                     .when(
                         F.abs(F.col("invoice_amount") - F.coalesce(F.col("po_total_amount"), F.lit(0.0))) >
                         F.col("invoice_amount") * 0.05,
                         "AMOUNT_MISMATCH"
                     )
                     .otherwise(None))
        .filter(F.col("exception_type").isNotNull())
        .withColumn("_exception_ts", F.current_timestamp())
    )


@dlt.table(name="silver_o2c_invoices", comment="Validated customer invoices with aging",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_o2c_invoices():
    return (
        dlt.read("bronze_o2c_invoices_dlt")
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


@dlt.table(name="silver_sales_orders", comment="Validated and enriched sales orders",
           table_properties={"quality": "silver", "domain": "O2C"})
def silver_sales_orders():
    return (
        dlt.read("bronze_sales_orders_dlt")
        .withColumn("so_date", F.to_date("so_date"))
        .withColumn("expected_delivery_date", F.to_date("expected_delivery_date"))
        .withColumn("actual_delivery_date",
                    F.when(F.col("actual_delivery_date") != "", F.to_date("actual_delivery_date"))
                     .otherwise(F.lit(None).cast("date")))
        .withColumn("delivery_delay_days",
                    F.when(
                        F.col("actual_delivery_date").isNotNull(),
                        F.datediff(F.col("actual_delivery_date"), F.col("expected_delivery_date"))
                    ))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["so_id"])
    )


@dlt.table(name="silver_journal_entries",
           comment="Validated and balanced journal entries",
           table_properties={"quality": "silver", "domain": "R2R"})
def silver_journal_entries():
    return (
        dlt.read("bronze_journal_entries_dlt")
        .filter(F.col("total_debit") == F.col("total_credit"))
        .filter(F.col("status") == "POSTED")
        .withColumn("je_date", F.to_date("je_date"))
        .withColumn("fiscal_quarter",
                    F.concat(
                        F.col("fiscal_year").cast("string"),
                        F.lit("-Q"),
                        F.ceil(F.month(F.col("je_date")) / 3).cast("string")
                    ))
        .withColumn("_silver_processed_at", F.current_timestamp())
        .dropDuplicates(["je_id"])
    )
