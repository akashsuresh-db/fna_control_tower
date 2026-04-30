# Databricks notebook source
# MAGIC %md
# MAGIC # Invoice AI Processing — ai_parse_document + ai_extract
# MAGIC
# MAGIC Extracts structured fields from vendor-uploaded PDF invoices in the UC Volume.
# MAGIC This runs as a **batch step** in the ETL pipeline — after data generation, before DLT.
# MAGIC
# MAGIC **Why separate from DLT?**
# MAGIC `ai_parse_document` is a SQL warehouse function. It works in notebooks and SQL
# MAGIC warehouses but is not available in DLT's execution context. Running it here as a
# MAGIC pre-processing step gives DLT a clean Delta table to join on.
# MAGIC
# MAGIC **Pipeline position:**
# MAGIC ```
# MAGIC data_generation
# MAGIC   → 05_Invoice_AI_Processing  (this notebook)
# MAGIC       UC Volume PDFs → ai_parse_document → ai_extract → silver_invoice_extractions
# MAGIC   → dlt_bronze_to_silver
# MAGIC       reads silver_invoice_extractions via spark.read for EXTRACTION_MISMATCH detection
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower", "Unity Catalog")
dbutils.widgets.text("schema", "finance_and_accounting", "Schema")

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

from pyspark.sql import functions as F

# COMMAND ----------

# MAGIC %md ## Step 1: Read PDF Invoices from UC Volume

# COMMAND ----------

# Read PDF files as binary content from the UC Volume
doc_files = (
    spark.read.format("binaryFile")
    .option("pathGlobFilter", "*.pdf")
    .load(VOLUME_PATH)
    .select(
        F.col("path").alias("file_path"),
        F.col("content").alias("binary_content"),   # BINARY — passed to ai_parse_document
        F.col("length").alias("file_size_bytes"),
        F.col("modificationTime").alias("file_modified_at"),
    )
    .withColumn(
        "invoice_id",
        F.regexp_extract(F.col("file_path"), r"/([^/]+)\.pdf$", 1),
    )
    .filter(F.col("invoice_id") != "")
)

print(f"PDF files found in volume: {doc_files.count()}")
doc_files.select("invoice_id", "file_path", "file_size_bytes").show(5, truncate=80)

# COMMAND ----------

# MAGIC %md ## Step 2: ai_parse_document — Extract Text from PDF Binary

# COMMAND ----------

# MAGIC %md
# MAGIC `ai_parse_document(content)` processes binary document content (PDF, image, text)
# MAGIC and returns a VARIANT with:
# MAGIC - `:content::string` — extracted plain text
# MAGIC - `:metadata` — document metadata (page count, MIME type, etc.)
# MAGIC
# MAGIC **Note:** Use `:field::type` VARIANT access syntax in SQL, or `F.expr()` in PySpark.

# COMMAND ----------

doc_files.createOrReplaceTempView("invoice_pdf_binaries")

parsed_docs = spark.sql("""
    SELECT
        invoice_id,
        file_path,
        ai_parse_document(binary_content):content::string AS doc_text
    FROM invoice_pdf_binaries
""")

parsed_docs.createOrReplaceTempView("parsed_invoice_docs")

print("Sample parsed document:")
parsed_docs.select(
    "invoice_id",
    F.col("doc_text").substr(1, 300).alias("text_preview")
).show(3, truncate=False)

# COMMAND ----------

# MAGIC %md ## Step 3: ai_extract — Pull Structured Fields from Text

# COMMAND ----------

# MAGIC %md
# MAGIC `ai_extract(text, fields)` extracts named entities from the parsed text.
# MAGIC Returns a VARIANT with one field per requested entity.

# COMMAND ----------

extracted_df = spark.sql("""
    SELECT
        invoice_id,
        file_path,
        doc_text,
        ai_extract(doc_text, array(
            'vendor_name',
            'invoice_number',
            'invoice_date',
            'due_date',
            'total_amount',
            'gst_amount',
            'po_reference',
            'bank_account',
            'gstin'
        )) AS ext
    FROM parsed_invoice_docs
""")

print("Sample extracted fields:")
extracted_df.selectExpr(
    "invoice_id",
    "ext:vendor_name::string AS vendor_name",
    "ext:total_amount::string AS total_amount",
    "ext:po_reference::string AS po_reference"
).show(5, truncate=False)

# COMMAND ----------

# MAGIC %md ## Step 4: Write to silver_invoice_extractions

# COMMAND ----------

silver_extractions = extracted_df.selectExpr(
    "invoice_id",
    "file_path",
    "doc_text",
    "ext:vendor_name::string    AS vendor_name",
    "ext:invoice_number::string AS invoice_number",
    "ext:invoice_date::string   AS invoice_date",
    "ext:due_date::string       AS due_date",
    "ext:total_amount::string   AS total_amount",   # PDF-stated total (tampered for ~5% of invoices)
    "ext:gst_amount::string     AS gst_amount",
    "ext:po_reference::string   AS po_reference",
    "ext:bank_account::string   AS bank_account",
    "ext:gstin::string          AS gstin",
    "current_timestamp()        AS _silver_processed_at",
)

silver_extractions.write \
    .format("delta") \
    .mode("overwrite") \
    .option("mergeSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.silver_invoice_extractions")

print(f"silver_invoice_extractions: {silver_extractions.count()} rows written")

# COMMAND ----------

# MAGIC %md ## Step 5: Cross-validate Against ERP Amounts

# COMMAND ----------

bronze_invoices = spark.table(f"{CATALOG}.{SCHEMA}.bronze_p2p_invoices")
extractions = spark.table(f"{CATALOG}.{SCHEMA}.silver_invoice_extractions")

validation = (
    extractions
    .join(bronze_invoices.select("invoice_id", F.col("total_amount").alias("erp_total")), on="invoice_id", how="left")
    .withColumn("pdf_total_numeric",
                F.regexp_replace(F.col("total_amount"), r"[^0-9.]", "").cast("double"))
    .withColumn("amount_diff",
                F.abs(F.col("pdf_total_numeric") - F.col("erp_total")))
    .withColumn("extraction_mismatch",
                (F.col("amount_diff") / F.col("erp_total") > 0.02))
)

mismatch_count = validation.filter(F.col("extraction_mismatch")).count()
total_count = validation.count()
print(f"EXTRACTION_MISMATCH detected: {mismatch_count} / {total_count} invoices ({100*mismatch_count/max(total_count,1):.1f}%)")

validation.select(
    "invoice_id", "vendor_name", "total_amount", "erp_total", "amount_diff", "extraction_mismatch"
).filter(F.col("extraction_mismatch")).show(10, truncate=False)

# COMMAND ----------

# MAGIC %md ## Step 6: Update bronze_raw_invoice_documents with AI-extracted totals

# COMMAND ----------

# Update pdf_stated_total in bronze_raw_invoice_documents with the AI-extracted values.
# This allows DLT's silver_p2p_invoices to use real AI extraction results for EXTRACTION_MISMATCH.
from delta.tables import DeltaTable

extracted_totals = extractions.select(
    "invoice_id",
    F.regexp_replace(F.col("total_amount"), r"[^0-9.]", "").cast("double").alias("ai_extracted_total"),
).filter(F.col("ai_extracted_total").isNotNull())

bronze_raw = DeltaTable.forName(spark, f"{CATALOG}.{SCHEMA}.bronze_raw_invoice_documents")

bronze_raw.alias("b").merge(
    extracted_totals.alias("ai"),
    "b.invoice_id = ai.invoice_id"
).whenMatchedUpdate(set={
    "pdf_stated_total": "ai.ai_extracted_total",
    "processing_status": F.lit("PROCESSED"),
}).execute()

updated_count = extracted_totals.count()
print(f"Updated {updated_count} rows in bronze_raw_invoice_documents with AI-extracted totals")
print("DLT silver_p2p_invoices will now use real AI extraction results for EXTRACTION_MISMATCH detection")
