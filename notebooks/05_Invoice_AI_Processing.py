# Databricks notebook source
# MAGIC %md
# MAGIC # Invoice AI Processing - Structured Extraction with ai_parse_document
# MAGIC
# MAGIC Uses `ai_parse_document()` to extract text from raw invoice files in UC Volume,
# MAGIC then `ai_extract()` to pull structured fields from the parsed content.
# MAGIC
# MAGIC **Pipeline**:
# MAGIC ```
# MAGIC UC Volume (*.txt files)
# MAGIC   → ai_parse_document(binary_content)   # OCR / text extraction
# MAGIC   → ai_extract(parsed_text, fields)     # Structured field extraction
# MAGIC   → silver_invoice_extractions
# MAGIC ```

# COMMAND ----------

CATALOG = "akash_s_demo"
SCHEMA = "finance_and_accounting"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_invoices"

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")

from pyspark.sql import functions as F
from pyspark.sql.types import *

# COMMAND ----------

# MAGIC %md ## Step 1: Read Raw Invoice Files from UC Volume

# COMMAND ----------

# Read invoice files as binary from the UC volume (supports PDFs, images, text)
doc_files = (
    spark.read.format("binaryFile")
    .option("pathGlobFilter", "*.txt")
    .load(VOLUME_PATH)
    .select(
        F.col("path"),
        F.col("content"),   # BINARY - passed directly to ai_parse_document
        F.col("length").alias("file_size_bytes"),
        F.col("modificationTime").alias("file_modified_at")
    )
)

# Extract invoice_id from filename: /Volumes/.../INV000001.txt → INV000001
doc_files = doc_files.withColumn(
    "invoice_id",
    F.regexp_extract(F.col("path"), r"/(INV\d+)\.txt$", 1)
).filter(F.col("invoice_id") != "")

print(f"Invoice files found in volume: {doc_files.count()}")
doc_files.select("invoice_id", "path", "file_size_bytes").show(5, truncate=80)

# COMMAND ----------

# MAGIC %md ## Step 2: Join with Bronze Metadata

# COMMAND ----------

bronze_docs = spark.table(f"{CATALOG}.{SCHEMA}.bronze_raw_invoice_documents")

# Join file binary content with bronze metadata
docs_with_meta = (
    doc_files
    .join(
        bronze_docs.select("invoice_id", "vendor_id", "_ingested_at"),
        on="invoice_id",
        how="inner"
    )
)

print(f"Invoices matched with metadata: {docs_with_meta.count()}")
docs_with_meta.createOrReplaceTempView("invoice_binary_docs")

# COMMAND ----------

# MAGIC %md ## Step 3: ai_parse_document — Extract Text from Binary Content

# COMMAND ----------

# MAGIC %md
# MAGIC `ai_parse_document(content)` processes the binary document content (PDF, image, text)
# MAGIC and returns a VARIANT with:
# MAGIC - `content`: extracted plain text (access with `:content::string`)
# MAGIC - `metadata`: document metadata (page count, mime type, etc.)
# MAGIC
# MAGIC Note: Use `:field::type` colon notation for VARIANT field access in SQL.

# COMMAND ----------

parsed_docs = spark.sql("""
SELECT
    invoice_id,
    vendor_id,
    path          AS file_path,
    file_size_bytes,
    _ingested_at,
    ai_parse_document(content):content::string AS document_text
FROM invoice_binary_docs
""")

parsed_docs.createOrReplaceTempView("parsed_invoice_docs")

print("Sample parsed document output:")
parsed_docs.select(
    "invoice_id",
    F.col("document_text").substr(1, 200).alias("extracted_text_preview")
).show(3, truncate=False)

# COMMAND ----------

# MAGIC %md ## Step 4: ai_extract — Pull Structured Fields from Parsed Text

# COMMAND ----------

# MAGIC %md
# MAGIC `ai_extract(text, fields)` extracts named entities from the parsed text.
# MAGIC Returns a STRUCT with one STRING field per requested entity.

# COMMAND ----------

extracted_df = spark.sql("""
SELECT
    invoice_id,
    vendor_id,
    file_path,
    file_size_bytes,
    _ingested_at,
    document_text,
    ai_extract(
        document_text,
        ARRAY(
            'invoice_number',
            'vendor_name',
            'vendor_gstin',
            'invoice_date',
            'due_date',
            'po_reference',
            'subtotal_amount',
            'cgst_amount',
            'sgst_amount',
            'total_amount',
            'currency',
            'bank_account_number',
            'ifsc_code'
        )
    )                                               AS fields
FROM parsed_invoice_docs
""")

print("Extraction complete. Sample extracted fields:")
extracted_df.select(
    "invoice_id",
    "fields.invoice_number",
    "fields.vendor_name",
    "fields.total_amount"
).show(5, truncate=False)

# COMMAND ----------

# MAGIC %md ## Step 5: Write to silver_invoice_extractions

# COMMAND ----------

silver_extractions = (
    extracted_df
    .select(
        F.col("invoice_id"),
        F.col("vendor_id"),
        F.col("file_path"),
        F.col("file_size_bytes"),
        # Extracted fields (all STRING from ai_extract - cast numerics as needed)
        F.col("fields.invoice_number").alias("extracted_invoice_number"),
        F.col("fields.vendor_name").alias("extracted_vendor_name"),
        F.col("fields.vendor_gstin").alias("extracted_gstin"),
        F.to_date(F.col("fields.invoice_date"), "dd-MMM-yyyy").alias("extracted_invoice_date"),
        F.to_date(F.col("fields.due_date"), "dd-MMM-yyyy").alias("extracted_due_date"),
        F.col("fields.po_reference").alias("extracted_po_reference"),
        F.regexp_replace(F.col("fields.subtotal_amount"), "[^0-9.]", "").cast("double").alias("extracted_subtotal"),
        F.regexp_replace(F.col("fields.cgst_amount"), "[^0-9.]", "").cast("double").alias("extracted_cgst"),
        F.regexp_replace(F.col("fields.sgst_amount"), "[^0-9.]", "").cast("double").alias("extracted_sgst"),
        F.regexp_replace(F.col("fields.total_amount"), "[^0-9.]", "").cast("double").alias("extracted_total_amount"),
        F.col("fields.currency").alias("extracted_currency"),
        F.col("fields.bank_account_number").alias("extracted_bank_account"),
        F.col("fields.ifsc_code").alias("extracted_ifsc"),
        F.col("document_text").alias("parsed_document_text"),
        F.lit("ai_parse_document + ai_extract").alias("extraction_method"),
        F.lit("COMPLETED").alias("processing_status"),
        F.current_timestamp().alias("_processed_at"),
        F.col("_ingested_at")
    )
)

silver_extractions.write.format("delta").mode("overwrite").option("mergeSchema", "true") \
    .saveAsTable(f"{CATALOG}.{SCHEMA}.silver_invoice_extractions")

print(f"silver_invoice_extractions: {silver_extractions.count()} rows written")

# COMMAND ----------

# MAGIC %md ## Step 6: Validate Extractions Against Bronze Source

# COMMAND ----------

bronze_invoices = spark.table(f"{CATALOG}.{SCHEMA}.bronze_p2p_invoices")
extractions = spark.table(f"{CATALOG}.{SCHEMA}.silver_invoice_extractions")

validation = (
    extractions
    .join(bronze_invoices.select("invoice_id", "total_amount"), on="invoice_id", how="left")
    .withColumn("amount_diff",
                F.abs(F.col("extracted_total_amount") - F.col("total_amount")))
    .withColumn("amount_match",
                F.col("amount_diff") < F.col("total_amount") * 0.02)
    .withColumn("extraction_quality",
                F.when(
                    F.col("extracted_invoice_number").isNotNull() &
                    F.col("extracted_vendor_name").isNotNull() &
                    F.col("extracted_total_amount").isNotNull() &
                    F.col("amount_match"),
                    "HIGH"
                ).when(
                    F.col("extracted_invoice_number").isNotNull() &
                    F.col("extracted_total_amount").isNotNull(),
                    "MEDIUM"
                ).otherwise("LOW"))
)

print("Extraction Quality Distribution:")
validation.groupBy("extraction_quality").count().show()

print("Sample Validated Extractions:")
validation.select(
    "invoice_id",
    "extracted_invoice_number",
    "extracted_vendor_name",
    "extracted_total_amount",
    "total_amount",
    "amount_diff",
    "extraction_quality"
).show(10, truncate=False)

# COMMAND ----------

# MAGIC %md ## Step 7: Mark Processed in Bronze

# COMMAND ----------

from delta.tables import DeltaTable

processed_ids = [r["invoice_id"] for r in extractions.select("invoice_id").collect()]
bronze_raw = DeltaTable.forName(spark, f"{CATALOG}.{SCHEMA}.bronze_raw_invoice_documents")

bronze_raw.update(
    condition=F.col("invoice_id").isin(processed_ids),
    set={"processing_status": F.lit("PROCESSED")}
)

print(f"Marked {len(processed_ids)} invoices as PROCESSED in bronze")
