# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Layer - Record-to-Report (R2R)
# MAGIC
# MAGIC Creates Gold tables for R2R analytics:
# MAGIC - `gold_fact_gl`: General Ledger entries with account classification
# MAGIC - `gold_fact_trial_balance`: Period-end trial balance by account

# COMMAND ----------

CATALOG = "akash_s_demo"
SCHEMA = "finance_and_accounting"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# COMMAND ----------

silver_je = spark.table(f"{CATALOG}.{SCHEMA}.silver_journal_entries")
bronze_je_lines = spark.table(f"{CATALOG}.{SCHEMA}.bronze_je_lines")
bronze_coa = spark.table(f"{CATALOG}.{SCHEMA}.bronze_chart_of_accounts")
bronze_cc = spark.table(f"{CATALOG}.{SCHEMA}.bronze_cost_centers")

# COMMAND ----------

# MAGIC %md ## gold_fact_gl

# COMMAND ----------

gold_fact_gl = (
    bronze_je_lines
    .join(
        silver_je.select("je_id", "je_number", "je_date", "je_type", "period",
                          "fiscal_year", "fiscal_quarter", "status", "posted_by"),
        on="je_id", how="inner"  # inner join to only include posted entries
    )
    .join(
        bronze_coa.select(
            F.col("account_code"),
            F.col("account_name"),
            F.col("account_type"),
            F.col("account_subtype")
        ),
        on="account_code", how="left"
    )
    .join(
        bronze_cc.select(F.col("cost_center_code").alias("cost_center"),
                          F.col("cost_center_name"),
                          F.col("department")),
        on="cost_center", how="left"
    )
    .withColumn("je_date", F.to_date("je_date"))
    .withColumn("amount",
                F.col("debit_amount") - F.col("credit_amount"))  # signed amount
    .withColumn("gl_year", F.year("je_date"))
    .withColumn("gl_month", F.month("je_date"))
    .withColumn("gl_quarter",
                F.concat(F.year("je_date").cast("string"), F.lit("-Q"),
                         F.ceil(F.month(F.col("je_date")) / 3).cast("string")))
    .withColumn("normal_balance",
                F.when(F.col("account_type").isin(["Asset", "Expense"]), "DEBIT")
                 .otherwise("CREDIT"))
    .select(
        "je_id",
        "je_number",
        F.col("line_number").alias("gl_line_number"),
        "account_code",
        "account_name",
        "account_type",
        "account_subtype",
        "cost_center",
        "cost_center_name",
        "department",
        "je_date",
        "period",
        "fiscal_year",
        "fiscal_quarter",
        "gl_year",
        "gl_month",
        "gl_quarter",
        "je_type",
        "status",
        "posted_by",
        F.col("debit_amount").alias("debit_inr"),
        F.col("credit_amount").alias("credit_inr"),
        F.col("amount").alias("net_amount_inr"),
        "normal_balance",
        F.col("description").alias("gl_description"),
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_fact_gl.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .partitionBy("gl_year", "gl_month") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_fact_gl")

print(f"gold_fact_gl: {gold_fact_gl.count()} rows")

# COMMAND ----------

# MAGIC %md ## gold_fact_trial_balance

# COMMAND ----------

# Compute running balances per account per period
gl_data = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_gl")

period_balances = (
    gl_data
    .groupBy("fiscal_year", "fiscal_quarter", "period", "account_code", "account_name",
             "account_type", "account_subtype")
    .agg(
        F.sum("debit_inr").alias("period_debit"),
        F.sum("credit_inr").alias("period_credit"),
        F.count("je_id").alias("transaction_count")
    )
    .withColumn("period_net",
                F.col("period_debit") - F.col("period_credit"))
)

# Compute cumulative (YTD) balances using window function
ytd_window = (
    Window
    .partitionBy("account_code", "fiscal_year")
    .orderBy("period")
    .rowsBetween(Window.unboundedPreceding, Window.currentRow)
)

gold_fact_trial_balance = (
    period_balances
    .withColumn("ytd_debit", F.sum("period_debit").over(ytd_window))
    .withColumn("ytd_credit", F.sum("period_credit").over(ytd_window))
    .withColumn("ytd_net", F.col("ytd_debit") - F.col("ytd_credit"))
    .withColumn("closing_balance",
                # Assets and Expenses: debit balance
                F.when(F.col("account_type").isin(["Asset", "Expense"]),
                       F.col("ytd_net"))
                # Liabilities, Equity, Revenue: credit balance
                .otherwise(-F.col("ytd_net")))
    .withColumn("balance_type",
                F.when(F.col("closing_balance") >= 0, "DR")
                 .otherwise("CR"))
    .select(
        "fiscal_year",
        "fiscal_quarter",
        "period",
        "account_code",
        "account_name",
        "account_type",
        "account_subtype",
        "period_debit",
        "period_credit",
        "period_net",
        "ytd_debit",
        "ytd_credit",
        "ytd_net",
        F.abs("closing_balance").alias("closing_balance_inr"),
        "balance_type",
        "transaction_count",
        F.current_timestamp().alias("_gold_processed_at")
    )
)

gold_fact_trial_balance.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .partitionBy("fiscal_year") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.gold_fact_trial_balance")

print(f"gold_fact_trial_balance: {gold_fact_trial_balance.count()} rows")

# COMMAND ----------

# MAGIC %md ## R2R Summary

# COMMAND ----------

fact_gl = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_gl")
trial_balance = spark.table(f"{CATALOG}.{SCHEMA}.gold_fact_trial_balance")

print("=" * 70)
print("R2R GOLD LAYER METRICS")
print("=" * 70)

total_debits = fact_gl.agg(F.sum("debit_inr")).collect()[0][0]
total_credits = fact_gl.agg(F.sum("credit_inr")).collect()[0][0]
print(f"  Total Debits (INR):     {total_debits:>15,.2f}")
print(f"  Total Credits (INR):    {total_credits:>15,.2f}")
print(f"  Balanced (diff):        {abs(total_debits - total_credits):>15,.2f}")

print("\nGL by Account Type:")
(fact_gl.groupBy("account_type")
    .agg(F.sum("debit_inr").alias("total_debit"),
         F.sum("credit_inr").alias("total_credit"))
    .orderBy("account_type")
    .show())

print("Spend by Cost Center (Top 5):")
(fact_gl.filter(F.col("account_type") == "Expense")
    .groupBy("cost_center_name", "department")
    .agg(F.sum("debit_inr").alias("total_expense"))
    .orderBy(F.desc("total_expense"))
    .limit(5)
    .show())

print("Latest Trial Balance (Current FY):")
current_year = spark.sql("SELECT year(current_date())").collect()[0][0]
(trial_balance
    .filter(F.col("fiscal_year") == current_year)
    .groupBy("period")
    .agg(
        F.sum(F.when(F.col("account_type") == "Asset", F.col("closing_balance_inr"))).alias("total_assets"),
        F.sum(F.when(F.col("account_type") == "Liability", F.col("closing_balance_inr"))).alias("total_liabilities"),
        F.sum(F.when(F.col("account_type") == "Revenue", F.col("closing_balance_inr"))).alias("total_revenue"),
        F.sum(F.when(F.col("account_type") == "Expense", F.col("closing_balance_inr"))).alias("total_expenses")
    )
    .orderBy("period")
    .show())
