# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Layer - Order-to-Cash (O2C)
# MAGIC
# MAGIC Creates Gold tables for O2C analytics:
# MAGIC - `gold_dim_customer`: Enriched customer dimension with DSO
# MAGIC - `gold_fact_sales`: Sales order facts with product mix
# MAGIC - `gold_fact_collections`: Collection/AR facts with aging and DSO

# COMMAND ----------

CATALOG = "akash_s_demo"
SCHEMA = "finance_and_accounting"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# COMMAND ----------

silver_customers = spark.table(f"{CATALOG}.{SCHEMA}.silver_customers")
silver_sales_orders = spark.table(f"{CATALOG}.{SCHEMA}.silver_sales_orders")
silver_o2c_invoices = spark.table(f"{CATALOG}.{SCHEMA}.silver_o2c_invoices")
bronze_o2c_payments = spark.table(f"{CATALOG}.{SCHEMA}.bronze_o2c_payments")
bronze_so_lines = spark.table(f"{CATALOG}.{SCHEMA}.bronze_so_lines")

# COMMAND ----------

# MAGIC %md ## gold_dim_customer

# COMMAND ----------

# Compute DSO per customer
# DSO = (Accounts Receivable / Total Revenue) * Days in Period
# Using simplified: avg days to collect

customer_collection_metrics = (
    silver_o2c_invoices
    .join(
        bronze_o2c_payments.groupBy("o2c_invoice_id")
            .agg(F.min("payment_date").alias("first_payment_date")),
        on="o2c_invoice_id", how="left"
    )
    .withColumn("first_payment_date", F.to_date("first_payment_date"))
    .withColumn("days_to_collect",
                F.when(
                    F.col("first_payment_date").isNotNull(),
                    F.datediff(F.col("first_payment_date"), F.col("invoice_date"))
                ))
    .groupBy("customer_id")
    .agg(
        F.count("o2c_invoice_id").alias("total_invoices"),
        F.sum("total_amount").alias("total_billed"),
        F.sum(F.when(F.col("status") == "PAID", F.col("total_amount")).otherwise(0)).alias("total_collected"),
        F.sum(F.when(F.col("status").isin(["OUTSTANDING", "OVERDUE"]), F.col("total_amount")).otherwise(0)).alias("outstanding_ar"),
        F.avg("days_to_collect").alias("avg_days_to_collect"),
        F.sum(F.when(F.col("status") == "OVERDUE", 1).otherwise(0)).alias("overdue_invoice_count"),
        F.max("invoice_date").alias("last_invoice_date")
    )
    .withColumn("dso",
                F.when(F.col("total_billed") > 0,
                       F.round(F.col("outstanding_ar") / F.col("total_billed") * 90, 1)))  # 90-day period
    .withColumn("collection_rate",
                F.when(F.col("total_billed") > 0,
                       F.round(F.col("total_collected") / F.col("total_billed") * 100, 1)))
)

so_metrics = (
    silver_sales_orders
    .groupBy("customer_id")
    .agg(
        F.count("so_id").alias("total_orders"),
        F.sum("total_amount").alias("total_order_value"),
        F.avg("total_amount").alias("avg_order_value")
    )
)

gold_dim_customer = (
    silver_customers
    .join(customer_collection_metrics, on="customer_id", how="left")
    .join(so_metrics, on="customer_id", how="left")
    .select(
        "customer_id",
        "customer_name",
        "customer_name_normalized",
        "segment",
        "industry",
        "country",
        "city",
        "state",
        "payment_terms",
        "credit_limit",
        "currency",
        "account_manager",
        "is_active",
        "is_gst_registered",
        F.coalesce(F.col("total_orders"), F.lit(0)).alias("total_sales_orders"),
        F.coalesce(F.col("total_order_value"), F.lit(0.0)).alias("total_order_value_inr"),
        F.coalesce(F.col("avg_order_value"), F.lit(0.0)).alias("avg_order_value_inr"),
        F.coalesce(F.col("total_invoices"), F.lit(0)).alias("total_invoices"),
        F.coalesce(F.col("total_billed"), F.lit(0.0)).alias("total_billed_inr"),
        F.coalesce(F.col("total_collected"), F.lit(0.0)).alias("total_collected_inr"),
        F.coalesce(F.col("outstanding_ar"), F.lit(0.0)).alias("outstanding_ar_inr"),
        F.col("dso"),
        F.col("collection_rate").alias("collection_rate_pct"),
        F.coalesce(F.col("avg_days_to_collect"), F.lit(0.0)).alias("avg_days_to_collect"),
        F.coalesce(F.col("overdue_invoice_count"), F.lit(0)).alias("overdue_invoices"),
        # Credit utilization
        F.when(
            F.col("credit_limit") > 0,
            F.round(F.coalesce(F.col("outstanding_ar"), F.lit(0.0)) / F.col("credit_limit") * 100, 1)
        ).alias("credit_utilization_pct"),
        F.col("last_invoice_date"),
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_dim_customer.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_dim_customer")

print(f"gold_dim_customer: {gold_dim_customer.count()} rows")

# COMMAND ----------

# MAGIC %md ## gold_fact_sales

# COMMAND ----------

# Get product-level aggregation per SO
so_product_mix = (
    bronze_so_lines
    .groupBy("so_id")
    .agg(
        F.collect_list("category").alias("product_categories"),
        F.size(F.collect_set("product_code")).alias("unique_products"),
        F.sum(F.when(F.col("category") == "Software", F.col("total_line_amount")).otherwise(0)).alias("software_revenue"),
        F.sum(F.when(F.col("category") == "Services", F.col("total_line_amount")).otherwise(0)).alias("services_revenue"),
        F.sum(F.when(F.col("category") == "Support", F.col("total_line_amount")).otherwise(0)).alias("support_revenue"),
        F.sum(F.when(F.col("category") == "Infrastructure", F.col("total_line_amount")).otherwise(0)).alias("infra_revenue"),
        F.avg("discount_percentage").alias("avg_discount_pct")
    )
)

gold_fact_sales = (
    silver_sales_orders
    .join(gold_dim_customer.select("customer_id", "customer_name", "segment", "industry"), on="customer_id", how="left")
    .join(so_product_mix, on="so_id", how="left")
    .withColumn("so_year", F.year("so_date"))
    .withColumn("so_month", F.month("so_date"))
    .withColumn("so_quarter",
                F.concat(F.year("so_date").cast("string"), F.lit("-Q"),
                         F.ceil(F.month(F.col("so_date")) / 3).cast("string")))
    .withColumn("revenue_excl_tax",
                F.round(F.col("total_amount") / 1.18, 2))  # Remove 18% GST
    .withColumn("gst_amount",
                F.round(F.col("total_amount") - F.col("revenue_excl_tax"), 2))
    .select(
        "so_id",
        "so_number",
        "customer_id",
        "customer_name",
        "segment",
        "industry",
        "so_date",
        "expected_delivery_date",
        "actual_delivery_date",
        "status",
        "region",
        "sales_rep",
        F.col("total_amount").alias("so_total_inr"),
        "revenue_excl_tax",
        "gst_amount",
        "unique_products",
        F.coalesce(F.col("software_revenue"), F.lit(0.0)).alias("software_revenue_inr"),
        F.coalesce(F.col("services_revenue"), F.lit(0.0)).alias("services_revenue_inr"),
        F.coalesce(F.col("support_revenue"), F.lit(0.0)).alias("support_revenue_inr"),
        F.coalesce(F.col("infra_revenue"), F.lit(0.0)).alias("infrastructure_revenue_inr"),
        F.coalesce(F.col("avg_discount_pct"), F.lit(0.0)).alias("avg_discount_pct"),
        F.col("delivery_delay_days"),
        "so_year",
        "so_month",
        "so_quarter",
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_fact_sales.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .partitionBy("so_year", "so_month") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_fact_sales")

print(f"gold_fact_sales: {gold_fact_sales.count()} rows")

# COMMAND ----------

# MAGIC %md ## gold_fact_collections

# COMMAND ----------

gold_fact_collections = (
    silver_o2c_invoices
    .join(
        bronze_o2c_payments.groupBy("o2c_invoice_id").agg(
            F.sum("payment_amount").alias("total_received"),
            F.min("payment_date").alias("first_payment_date"),
            F.max("payment_date").alias("last_payment_date"),
            F.count("receipt_id").alias("payment_count"),
            F.first("payment_method").alias("payment_method")
        ),
        on="o2c_invoice_id", how="left"
    )
    .join(gold_dim_customer.select("customer_id", "customer_name", "segment", "industry"), on="customer_id", how="left")
    .join(
        silver_sales_orders.select("so_id", "region", "sales_rep"),
        on="so_id", how="left"
    )
    .withColumn("first_payment_date", F.to_date("first_payment_date"))
    .withColumn("days_to_collect",
                F.when(F.col("first_payment_date").isNotNull(),
                       F.datediff(F.col("first_payment_date"), F.col("invoice_date"))))
    .withColumn("balance_outstanding",
                F.col("total_amount") - F.coalesce(F.col("total_received"), F.lit(0.0)))
    .withColumn("is_fully_collected", F.col("balance_outstanding") <= 0)
    .withColumn("collection_year", F.year("invoice_date"))
    .withColumn("collection_month", F.month("invoice_date"))
    .withColumn("collection_quarter",
                F.concat(F.year("invoice_date").cast("string"), F.lit("-Q"),
                         F.ceil(F.month(F.col("invoice_date")) / 3).cast("string")))
    .select(
        "o2c_invoice_id",
        "invoice_number",
        "so_id",
        "customer_id",
        "customer_name",
        "segment",
        "industry",
        "region",
        "sales_rep",
        "invoice_date",
        "due_date",
        "first_payment_date",
        F.col("total_amount").alias("invoice_total_inr"),
        F.col("invoice_amount").alias("invoice_amount_excl_tax"),
        F.col("tax_amount"),
        F.coalesce(F.col("total_received"), F.lit(0.0)).alias("amount_collected_inr"),
        F.col("balance_outstanding"),
        F.col("status").alias("invoice_status"),
        "aging_bucket",
        "days_outstanding",
        "days_overdue",
        "days_to_collect",
        "is_fully_collected",
        F.col("payment_count").alias("payment_installments"),
        "payment_method",
        "collection_year",
        "collection_month",
        "collection_quarter",
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_fact_collections.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .partitionBy("collection_year", "collection_month") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_fact_collections")

print(f"gold_fact_collections: {gold_fact_collections.count()} rows")

# COMMAND ----------

# MAGIC %md ## O2C Summary Metrics

# COMMAND ----------

fact_sales = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_sales")
fact_collections = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_collections")
dim_customer = spark.table(f"{CATALOG}.{SCHEMA}.gold_dim_customer")

print("=" * 70)
print("O2C GOLD LAYER METRICS")
print("=" * 70)

total_revenue = fact_sales.agg(F.sum("revenue_excl_tax")).collect()[0][0]
total_orders = fact_sales.count()
avg_dso = dim_customer.filter(F.col("dso").isNotNull()).agg(F.avg("dso")).collect()[0][0]
overdue_ar = fact_collections.filter(F.col("invoice_status") == "OVERDUE").agg(F.sum("balance_outstanding")).collect()[0][0]

print(f"  Total Revenue (ex-GST INR): {total_revenue:>15,.2f}")
print(f"  Total Sales Orders:         {total_orders:>15,}")
print(f"  Average DSO (days):         {avg_dso:>15.1f}" if avg_dso else "  Average DSO: N/A")
print(f"  Overdue AR (INR):           {overdue_ar:>15,.2f}" if overdue_ar else "  Overdue AR: 0")
print()

print("Revenue by Segment:")
(fact_sales.groupBy("segment")
    .agg(F.sum("revenue_excl_tax").alias("revenue"), F.count("so_id").alias("orders"))
    .orderBy(F.desc("revenue"))
    .show())

print("Top 5 Customers by Revenue:")
(fact_sales.groupBy("customer_name", "segment")
    .agg(F.sum("revenue_excl_tax").alias("revenue"))
    .orderBy(F.desc("revenue"))
    .limit(5)
    .show(truncate=False))

print("MoM Revenue (Last 6 Months):")
(fact_sales
    .filter(F.col("so_date") >= F.add_months(F.current_date(), -6))
    .groupBy("so_year", "so_month")
    .agg(F.sum("revenue_excl_tax").alias("revenue"))
    .orderBy("so_year", "so_month")
    .show())
