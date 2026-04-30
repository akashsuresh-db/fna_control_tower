-- Databricks notebook source
-- MAGIC %md
-- MAGIC # Invoice AI Extraction — Silver Layer
-- MAGIC
-- MAGIC Defines `silver_invoice_extractions` as a SQL DLT table.
-- MAGIC SQL DLT handles VARIANT return types from `ai_parse_document` and `ai_extract` natively
-- MAGIC at analysis time. Python DLT cannot resolve VARIANT types during the analysis phase.
-- MAGIC
-- MAGIC **Pipeline**:
-- MAGIC ```
-- MAGIC bronze_invoice_pdfs (Python DLT)
-- MAGIC   → ai_parse_document(binary_content)   # Extract full text from PDF
-- MAGIC   → ai_extract(doc_text, fields)         # Structure named fields from text
-- MAGIC   → silver_invoice_extractions            # Joined into silver_p2p_invoices for
-- MAGIC                                           # EXTRACTION_MISMATCH detection
-- MAGIC ```

-- COMMAND ----------

CREATE OR REFRESH LIVE TABLE silver_invoice_extractions (
  invoice_id           STRING  COMMENT 'Invoice ID — matches bronze_p2p_invoices.invoice_id',
  file_path            STRING  COMMENT 'UC Volume path to source PDF',
  doc_text             STRING  COMMENT 'Full text extracted from the PDF via ai_parse_document',
  vendor_name          STRING  COMMENT 'AI-extracted vendor name from PDF text',
  invoice_number       STRING  COMMENT 'AI-extracted invoice number from PDF text',
  invoice_date         STRING  COMMENT 'AI-extracted invoice date from PDF text',
  due_date             STRING  COMMENT 'AI-extracted payment due date from PDF text',
  total_amount         STRING  COMMENT 'AI-extracted total amount — may differ from ERP for tampered invoices',
  gst_amount           STRING  COMMENT 'AI-extracted GST/tax amount',
  po_reference         STRING  COMMENT 'AI-extracted PO reference number',
  bank_account         STRING  COMMENT 'AI-extracted bank account details',
  gstin                STRING  COMMENT 'AI-extracted GSTIN',
  _silver_processed_at TIMESTAMP
)
COMMENT 'AI-extracted structured invoice fields from PDF documents via ai_parse_document + ai_extract'
TBLPROPERTIES ('quality' = 'silver', 'domain' = 'P2P')
AS
WITH parsed AS (
  -- Step 1: Parse raw PDF binary → selectable plain text
  SELECT
    invoice_id,
    file_path,
    ai_parse_document(binary_content):content::string AS doc_text
  FROM LIVE.bronze_invoice_pdfs
),
extracted AS (
  -- Step 2: Extract structured named fields from the plain text
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
  FROM parsed
)
SELECT
  invoice_id,
  file_path,
  doc_text,
  ext:vendor_name::string    AS vendor_name,
  ext:invoice_number::string AS invoice_number,
  ext:invoice_date::string   AS invoice_date,
  ext:due_date::string       AS due_date,
  ext:total_amount::string   AS total_amount,
  ext:gst_amount::string     AS gst_amount,
  ext:po_reference::string   AS po_reference,
  ext:bank_account::string   AS bank_account,
  ext:gstin::string          AS gstin,
  current_timestamp()        AS _silver_processed_at
FROM extracted
