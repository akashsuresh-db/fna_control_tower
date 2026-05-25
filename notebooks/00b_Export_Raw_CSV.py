# Databricks notebook source
# MAGIC %md
# MAGIC # 00b - Export Bronze Tables to Raw CSV Volume
# MAGIC
# MAGIC Creates a new `raw_csv` UC Volume and exports each transactional bronze table as a CSV.
# MAGIC These CSVs become the **actual source** that the DLT pipeline ingests via Auto Loader,
# MAGIC removing the prior "bronze reads from bronze" duplication and giving the medallion
# MAGIC a real ingestion entry point.

# COMMAND ----------

CATALOG = "fna_control_tower_catalog"
SCHEMA = "finance_and_accounting"
RAW_CSV_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_csv"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_csv")
print(f"Volume ready: {RAW_CSV_PATH}")

# COMMAND ----------

# Each entity gets its own subdirectory so Auto Loader can ingest with per-stream schema location
TABLES = [
    "bronze_vendors",
    "bronze_customers",
    "bronze_po_header",
    "bronze_po_line",
    "bronze_grn",
    "bronze_p2p_invoices",
    "bronze_p2p_payments",
    "bronze_sales_orders",
    "bronze_so_lines",
    "bronze_o2c_invoices",
    "bronze_o2c_payments",
    "bronze_journal_entries",
    "bronze_je_lines",
    "bronze_chart_of_accounts",
    "bronze_cost_centers",
]

import os, shutil

results = []
for t in TABLES:
    entity = t.replace("bronze_", "")
    out_dir = f"{RAW_CSV_PATH}/{entity}"
    try:
        df = spark.table(f"{CATALOG}.{SCHEMA}.{t}")
        # Coalesce so each entity is a small number of CSV part files
        (df.coalesce(1).write
            .mode("overwrite")
            .option("header", "true")
            .option("escape", "\"")
            .csv(out_dir))
        cnt = df.count()
        results.append((t, entity, cnt, "OK"))
        print(f"  ✓ {t:30s} → {out_dir}  ({cnt} rows)")
    except Exception as e:
        results.append((t, entity, 0, str(e)[:200]))
        print(f"  ✗ {t:30s} FAILED: {str(e)[:120]}")

# COMMAND ----------

# MAGIC %md ## Verify

# COMMAND ----------

print("Listing /raw_csv contents:")
for d in dbutils.fs.ls(RAW_CSV_PATH):
    name = d.name.rstrip('/')
    sub_files = dbutils.fs.ls(d.path)
    csv_files = [f for f in sub_files if f.name.endswith('.csv')]
    print(f"  {name:35s}  {len(csv_files)} csv file(s)")

print()
print("Summary:")
for r in results:
    print(f"  {r[0]:30s} rows={r[2]:6d}  status={r[3]}")
