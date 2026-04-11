# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Layer - Procure-to-Pay (P2P)
# MAGIC
# MAGIC Creates Gold tables for P2P analytics:
# MAGIC - `gold_dim_vendor`: Enriched vendor dimension
# MAGIC - `gold_fact_invoices`: Invoice facts with aging, match status, payment info
# MAGIC - `gold_fact_payments`: Payment facts with timing metrics

# COMMAND ----------

dbutils.widgets.text("catalog", "hp_sf_test", "Unity Catalog")
dbutils.widgets.text("schema", "finance_and_accounting", "Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# COMMAND ----------

# MAGIC %md ## gold_dim_vendor

# COMMAND ----------

silver_vendors = spark.table(f"{CATALOG}.{SCHEMA}.silver_vendors")
p2p_invoices = spark.table(f"{CATALOG}.{SCHEMA}.silver_p2p_invoices")
p2p_payments = spark.table(f"{CATALOG}.{SCHEMA}.bronze_p2p_payments")

# Compute vendor-level aggregates
vendor_spend = (
    p2p_invoices
    .filter(F.col("status") != "REJECTED")
    .groupBy("vendor_id")
    .agg(
        F.count("invoice_id").alias("total_invoices"),
        F.sum("total_amount").alias("total_spend"),
        F.avg("total_amount").alias("avg_invoice_amount"),
        F.countDistinct("po_id").alias("total_pos"),
        F.sum(F.when(F.col("match_status") == "THREE_WAY_MATCHED", 1).otherwise(0)).alias("three_way_matched_count"),
        F.sum(F.when(F.col("match_status") == "AMOUNT_MISMATCH", 1).otherwise(0)).alias("amount_mismatch_count"),
        F.sum(F.when(F.col("status") == "PENDING", 1).otherwise(0)).alias("pending_invoices"),
        F.max("invoice_date").alias("last_invoice_date")
    )
)

vendor_payment_perf = (
    p2p_payments
    .filter(F.col("status") == "COMPLETED")
    .groupBy("vendor_id")
    .agg(
        F.count("payment_id").alias("total_payments",),
        F.sum("payment_amount").alias("total_paid_amount")
    )
)

gold_dim_vendor = (
    silver_vendors
    .join(vendor_spend, on="vendor_id", how="left")
    .join(vendor_payment_perf, on="vendor_id", how="left")
    .select(
        F.col("vendor_id"),
        F.col("vendor_name"),
        F.col("vendor_name_normalized"),
        F.col("vendor_category"),
        F.col("country"),
        F.col("city"),
        F.col("state"),
        F.col("payment_terms"),
        F.col("currency"),
        F.col("gstin"),
        F.col("is_gst_registered"),
        F.col("is_active"),
        F.coalesce(F.col("total_invoices"), F.lit(0)).alias("total_invoices"),
        F.coalesce(F.col("total_spend"), F.lit(0.0)).alias("total_spend_inr"),
        F.coalesce(F.col("avg_invoice_amount"), F.lit(0.0)).alias("avg_invoice_amount_inr"),
        F.coalesce(F.col("total_pos"), F.lit(0)).alias("total_purchase_orders"),
        F.coalesce(F.col("three_way_matched_count"), F.lit(0)).alias("three_way_matched_invoices"),
        F.coalesce(F.col("amount_mismatch_count"), F.lit(0)).alias("amount_mismatch_invoices"),
        F.coalesce(F.col("pending_invoices"), F.lit(0)).alias("pending_invoices"),
        F.coalesce(F.col("total_payments"), F.lit(0)).alias("total_payments_count"),
        F.coalesce(F.col("total_paid_amount"), F.lit(0.0)).alias("total_paid_amount_inr"),
        F.col("last_invoice_date"),
        # Payment compliance score
        F.when(
            F.col("total_invoices") > 0,
            F.round(
                F.coalesce(F.col("three_way_matched_count"), F.lit(0)) / F.col("total_invoices") * 100,
                1
            )
        ).alias("match_compliance_pct"),
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_dim_vendor.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_dim_vendor")

print(f"gold_dim_vendor: {gold_dim_vendor.count()} rows")

# COMMAND ----------

# MAGIC %md ## gold_fact_invoices

# COMMAND ----------

silver_invoices = spark.table(f"{CATALOG}.{SCHEMA}.silver_p2p_invoices")
silver_po = spark.table(f"{CATALOG}.{SCHEMA}.silver_po_header")
silver_grn = spark.table(f"{CATALOG}.{SCHEMA}.silver_grn")
dim_vendor = spark.table(f"{CATALOG}.{SCHEMA}.gold_dim_vendor")
bronze_payments = spark.table(f"{CATALOG}.{SCHEMA}.bronze_p2p_payments")

# Get payment info per invoice
payment_info = (
    bronze_payments
    .groupBy("invoice_id")
    .agg(
        F.min("payment_date").alias("payment_date"),
        F.sum("payment_amount").alias("paid_amount"),
        F.first("payment_method").alias("payment_method")
    )
)

# Get GRN info per PO
grn_info = (
    silver_grn
    .groupBy("po_id")
    .agg(
        F.max("grn_id").alias("grn_id"),
        F.max("grn_date").alias("grn_date"),
        F.max("received_amount").alias("grn_received_amount"),
        F.max("quality_check_status").alias("quality_check_status")
    )
)

gold_fact_invoices = (
    silver_invoices
    .join(payment_info, on="invoice_id", how="left")
    .join(grn_info, on="po_id", how="left")
    .join(dim_vendor.select("vendor_id", "vendor_name", "vendor_category", "vendor_name_normalized"), on="vendor_id", how="left")
    .join(silver_po.select("po_id", F.col("po_number"), F.col("po_date").alias("po_date_from_po")), on="po_id", how="left")
    .withColumn("payment_date", F.to_date("payment_date"))
    .withColumn("days_to_pay",
                F.when(
                    F.col("payment_date").isNotNull(),
                    F.datediff(F.col("payment_date"), F.col("invoice_date"))
                ))
    .withColumn("aging_days",
                F.when(F.col("status") != "PAID", F.datediff(F.current_date(), F.col("invoice_date")))
                 .otherwise(F.col("days_to_pay")))
    .withColumn("aging_bucket",
                F.when(F.col("aging_days") <= 30, "0-30 days")
                 .when(F.col("aging_days") <= 60, "31-60 days")
                 .when(F.col("aging_days") <= 90, "61-90 days")
                 .otherwise("90+ days"))
    .withColumn("payment_on_time",
                F.when(
                    F.col("payment_date").isNotNull(),
                    F.col("payment_date") <= F.col("due_date")
                ))
    .withColumn("invoice_year", F.year("invoice_date"))
    .withColumn("invoice_month", F.month("invoice_date"))
    .withColumn("invoice_quarter",
                F.concat(F.year("invoice_date").cast("string"), F.lit("-Q"),
                         F.ceil(F.month(F.col("invoice_date")) / 3).cast("string")))
    .select(
        # Keys
        F.col("invoice_id"),
        F.col("invoice_number"),
        F.col("po_id"),
        F.col("grn_id"),
        F.col("vendor_id"),
        # Vendor info
        F.col("vendor_name"),
        F.col("vendor_category"),
        F.col("vendor_name_normalized"),
        # Dates
        F.col("invoice_date"),
        F.col("due_date"),
        F.col("payment_date"),
        F.col("po_date_from_po").alias("po_date"),
        F.col("grn_date"),
        # Amounts
        F.col("invoice_amount"),
        F.col("tax_amount"),
        F.col("total_amount").alias("invoice_total_inr"),
        F.coalesce(F.col("paid_amount"), F.lit(0.0)).alias("paid_amount_inr"),
        # Status
        F.col("status").alias("invoice_status"),
        F.col("po_status"),
        F.col("match_status"),
        F.col("has_po_ref"),
        F.col("has_grn"),
        F.col("is_overdue"),
        F.col("quality_check_status").alias("grn_quality_status"),
        # Metrics
        F.col("aging_days"),
        F.col("aging_bucket"),
        F.col("days_to_pay"),
        F.col("payment_on_time"),
        F.col("days_outstanding"),
        F.col("payment_method"),
        # Time dimensions
        F.col("invoice_year"),
        F.col("invoice_month"),
        F.col("invoice_quarter"),
        # GST
        F.col("gstin_vendor"),
        F.col("tds_applicable"),
        F.col("tds_rate"),
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_fact_invoices.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .partitionBy("invoice_year", "invoice_month") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_fact_invoices")

print(f"gold_fact_invoices: {gold_fact_invoices.count()} rows")

# COMMAND ----------

# MAGIC %md ## gold_fact_payments

# COMMAND ----------

bronze_payments = spark.table(f"{CATALOG}.{SCHEMA}.bronze_p2p_payments")
silver_invoices = spark.table(f"{CATALOG}.{SCHEMA}.silver_p2p_invoices")

inv_for_pay = silver_invoices.select(
    "invoice_id",
    "invoice_date",
    "due_date",
    "total_amount",
    F.col("vendor_id").alias("inv_vendor_id"),
    "po_id",
    "match_status"
)

gold_fact_payments = (
    bronze_payments
    .join(inv_for_pay, on="invoice_id", how="left")
    .join(dim_vendor.select(F.col("vendor_id").alias("dv_vendor_id"), "vendor_name", "vendor_category"),
          F.col("inv_vendor_id") == F.col("dv_vendor_id"), how="left")
    .withColumn("payment_date", F.to_date("payment_date"))
    .withColumn("invoice_date", F.to_date("invoice_date"))
    .withColumn("due_date", F.to_date("due_date"))
    .withColumn("days_to_pay", F.datediff(F.col("payment_date"), F.col("invoice_date")))
    .withColumn("early_late_days", F.datediff(F.col("due_date"), F.col("payment_date")))
    .withColumn("payment_timing",
                F.when(F.col("early_late_days") > 0, "EARLY")
                 .when(F.col("early_late_days") == 0, "ON_TIME")
                 .otherwise("LATE"))
    .withColumn("payment_year", F.year("payment_date"))
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
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_fact_payments.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .partitionBy("payment_year", "payment_month") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_fact_payments")

print(f"gold_fact_payments: {gold_fact_payments.count()} rows")

# COMMAND ----------

# MAGIC %md ## P2P Summary Metrics

# COMMAND ----------

fact_invoices = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_invoices")
fact_payments = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_payments")

print("=" * 70)
print("P2P GOLD LAYER METRICS")
print("=" * 70)

total_spend = fact_invoices.agg(F.sum("invoice_total_inr")).collect()[0][0]
pending_invoices = fact_invoices.filter(F.col("invoice_status") == "PENDING").count()
overdue_invoices = fact_invoices.filter(F.col("is_overdue") == True).count()
three_way_matched = fact_invoices.filter(F.col("match_status") == "THREE_WAY_MATCHED").count()
total_inv = fact_invoices.count()

print(f"  Total Spend (INR):         {total_spend:>15,.2f}")
print(f"  Total Invoices:            {total_inv:>15,}")
print(f"  Pending Invoices:          {pending_invoices:>15,}")
print(f"  Overdue Invoices:          {overdue_invoices:>15,}")
print(f"  3-Way Matched:             {three_way_matched:>15,} ({three_way_matched/total_inv*100:.1f}%)")
print()

print("Top 5 Vendors by Spend:")
(fact_invoices.groupBy("vendor_name", "vendor_category")
    .agg(F.sum("invoice_total_inr").alias("total_spend"))
    .orderBy(F.desc("total_spend"))
    .limit(5)
    .show(truncate=False))

print("Invoice Aging Distribution:")
(fact_invoices.filter(F.col("invoice_status") != "PAID")
    .groupBy("aging_bucket")
    .agg(F.count("invoice_id").alias("count"), F.sum("invoice_total_inr").alias("amount"))
    .orderBy("aging_bucket")
    .show())
