# Finance & Accounting Data Platform Demo

## Overview
A production-grade Finance & Accounting data platform on Databricks covering the three core financial processes:
- **P2P (Procure-to-Pay)**: Vendor management, purchase orders, goods receipts, invoice processing, payments
- **O2C (Order-to-Cash)**: Customer management, sales orders, customer invoices, collections
- **R2R (Record-to-Report)**: Chart of accounts, journal entries, general ledger, trial balance

## Target Environment
- **Workspace**: https://adb-984752964297111.11.azuredatabricks.net/
- **Profile**: field-east
- **Catalog**: akash_s_demo
- **Schema**: finance_and_accounting

## Architecture

### Lakehouse Layers
All tables in `akash_s_demo.finance_and_accounting` with layer prefixes:

```
bronze_*  →  silver_*  →  gold_*
```

#### Bronze (Raw Ingestion)
- bronze_vendors, bronze_po_header, bronze_po_line
- bronze_grn, bronze_p2p_invoices, bronze_p2p_payments
- bronze_customers, bronze_sales_orders, bronze_o2c_invoices, bronze_o2c_payments
- bronze_chart_of_accounts, bronze_journal_entries, bronze_cost_centers
- bronze_raw_invoice_documents (raw invoice text/JSON)

#### Silver (Cleaned & Validated)
- silver_vendors, silver_customers
- silver_po_header, silver_po_line
- silver_grn
- silver_p2p_invoices (deduplicated, validated, 3-way matched)
- silver_p2p_payments
- silver_o2c_invoices, silver_o2c_payments
- silver_journal_entries
- silver_invoice_extractions (AI-parsed invoice fields)
- silver_invoice_exceptions (quarantined bad records)

#### Gold (Business Models)
P2P:
- gold_dim_vendor
- gold_fact_invoices (with aging, match status)
- gold_fact_payments

O2C:
- gold_dim_customer
- gold_fact_sales
- gold_fact_collections (with DSO)

R2R:
- gold_fact_gl
- gold_fact_trial_balance

### Key Features
1. **DLT Pipeline**: Bronze → Silver with expectations & quarantine
2. **AI Invoice Processing**: Simulated LLM extraction from raw invoice text
3. **3-Way Matching**: PO ↔ Invoice ↔ GRN reconciliation
4. **Business Metrics**: Invoice aging, DSO, spend analytics
5. **Genie Space**: "Finance & Accounting Analytics" for NL querying

## Notebooks Structure
```
/Finance & Accounting Demo/
├── 00_Setup_and_Data_Generation
├── 01_DLT_Pipeline (Bronze + Silver DLT)
├── 02_Gold_Layer_P2P
├── 03_Gold_Layer_O2C
├── 04_Gold_Layer_R2R
├── 05_Invoice_AI_Processing
└── 06_Genie_Space_Setup
```
