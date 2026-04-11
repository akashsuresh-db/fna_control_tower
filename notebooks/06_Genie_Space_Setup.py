# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Space Setup - Finance & Accounting Analytics
# MAGIC
# MAGIC Creates a Genie Space for natural language querying of the Finance & Accounting Gold layer.
# MAGIC
# MAGIC Includes:
# MAGIC - Gold table registration
# MAGIC - Semantic descriptions
# MAGIC - Sample questions / curated queries
# MAGIC - Metric definitions

# COMMAND ----------

CATALOG = "hp_sf_test"
SCHEMA = "finance_and_accounting"
WORKSPACE_URL = "https://adb-984752964297111.11.azuredatabricks.net"

# COMMAND ----------

import requests
import json

token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def api_call(method, path, payload=None):
    url = f"{WORKSPACE_URL}/api/2.0{path}"
    resp = requests.request(method, url, headers=headers, json=payload)
    if resp.status_code not in [200, 201]:
        print(f"ERROR {resp.status_code}: {resp.text}")
        return None
    return resp.json()

# COMMAND ----------

# MAGIC %md ## Step 1: Add Table Descriptions (Semantic Layer)

# COMMAND ----------

table_descriptions = {
    "gold_dim_vendor": {
        "description": "Vendor dimension table containing enriched vendor master data with aggregated P2P spend metrics. Use this for vendor analysis, spend categorization, and compliance reporting.",
        "columns": {
            "vendor_id": "Unique vendor identifier (e.g., VND0001)",
            "vendor_name": "Legal vendor/supplier name",
            "vendor_category": "Vendor business category (IT Services, Manufacturing, Logistics, etc.)",
            "total_spend_inr": "Cumulative total amount paid to this vendor in INR",
            "total_invoices": "Total number of invoices received from this vendor",
            "three_way_matched_invoices": "Count of invoices that passed PO + GRN + Invoice 3-way match",
            "match_compliance_pct": "Percentage of invoices that achieved 3-way match (higher is better)",
            "pending_invoices": "Number of invoices currently in PENDING status awaiting approval",
            "payment_terms": "Standard payment terms agreed with vendor (e.g., NET30, NET45)",
            "is_gst_registered": "Whether the vendor is registered for GST",
        }
    },
    "gold_fact_invoices": {
        "description": "P2P Invoice fact table containing all vendor invoices with matching status, aging, and payment details. Central table for AP analytics, invoice aging, and spend management.",
        "columns": {
            "invoice_id": "Unique invoice identifier",
            "invoice_number": "Vendor-assigned invoice number",
            "vendor_name": "Name of the supplying vendor",
            "vendor_category": "Category of the vendor",
            "invoice_date": "Date the invoice was issued",
            "due_date": "Payment due date for the invoice",
            "invoice_total_inr": "Total invoice amount including GST in INR",
            "invoice_status": "Current status: PENDING, APPROVED, PAID, REJECTED, UNDER_REVIEW",
            "match_status": "3-way match result: THREE_WAY_MATCHED, TWO_WAY_MATCHED, AMOUNT_MISMATCH, NO_PO_REFERENCE",
            "aging_days": "Number of days since invoice date (for unpaid invoices)",
            "aging_bucket": "Aging category: 0-30 days, 31-60 days, 61-90 days, 90+ days",
            "is_overdue": "True if the payment due date has passed and invoice is unpaid",
            "days_to_pay": "Number of days taken to pay the invoice (for paid invoices)",
            "payment_on_time": "True if payment was made on or before the due date",
            "invoice_year": "Year of invoice date (for time-based filtering)",
            "invoice_quarter": "Fiscal quarter of invoice (e.g., 2024-Q1)",
        }
    },
    "gold_fact_payments": {
        "description": "P2P Payment fact table tracking all vendor payments with timing analysis. Use for payment performance, cash flow, and DPO analysis.",
        "columns": {
            "payment_id": "Unique payment identifier",
            "vendor_name": "Vendor receiving the payment",
            "payment_date": "Date payment was processed",
            "payment_amount_inr": "Amount paid in INR",
            "payment_method": "Payment method: NEFT, RTGS, CHEQUE, WIRE",
            "payment_timing": "EARLY, ON_TIME, or LATE relative to due date",
            "days_to_pay": "Days from invoice date to payment date",
            "early_late_days": "Positive = early, negative = late (days relative to due date)",
            "payment_status": "COMPLETED, FAILED, or PENDING",
        }
    },
    "gold_dim_customer": {
        "description": "Customer dimension with enriched O2C metrics including DSO, collection rates, and credit utilization. Use for customer segmentation, AR management, and credit risk analysis.",
        "columns": {
            "customer_id": "Unique customer identifier",
            "customer_name": "Legal customer entity name",
            "segment": "Customer segment: Enterprise, Mid-Market, SMB, Startup, Government",
            "industry": "Customer industry vertical",
            "dso": "Days Sales Outstanding - average days to collect payment (lower is better)",
            "outstanding_ar_inr": "Total accounts receivable currently outstanding",
            "collection_rate_pct": "Percentage of billed amount successfully collected",
            "credit_limit": "Approved credit limit for the customer",
            "credit_utilization_pct": "Current AR as % of credit limit",
            "overdue_invoices": "Count of invoices past their due date",
            "avg_days_to_collect": "Average number of days taken to collect payment",
        }
    },
    "gold_fact_sales": {
        "description": "O2C Sales Order fact table with revenue breakdown by product category and customer. Use for revenue analytics, regional performance, and sales trends.",
        "columns": {
            "so_id": "Sales order identifier",
            "customer_name": "Ordering customer name",
            "segment": "Customer segment",
            "industry": "Customer industry",
            "region": "Sales region (North, South, East, West, Central)",
            "sales_rep": "Assigned sales representative",
            "so_date": "Sales order creation date",
            "revenue_excl_tax": "Net revenue excluding GST in INR",
            "so_total_inr": "Total order value including GST",
            "software_revenue_inr": "Revenue from software license products",
            "services_revenue_inr": "Revenue from professional services",
            "support_revenue_inr": "Revenue from support/maintenance contracts",
            "avg_discount_pct": "Average discount percentage applied on the order",
            "status": "Order status: CONFIRMED, SHIPPED, DELIVERED, INVOICED, CANCELLED",
            "so_quarter": "Fiscal quarter of order (e.g., 2024-Q1)",
        }
    },
    "gold_fact_collections": {
        "description": "O2C Collections/AR fact table with invoice-level aging and collection status. Use for DSO analysis, overdue tracking, and collection efficiency.",
        "columns": {
            "o2c_invoice_id": "Customer invoice identifier",
            "customer_name": "Customer name",
            "segment": "Customer segment",
            "invoice_date": "Invoice issue date",
            "due_date": "Payment due date",
            "invoice_total_inr": "Total invoice amount including GST",
            "amount_collected_inr": "Amount received against this invoice",
            "balance_outstanding": "Remaining unpaid amount",
            "invoice_status": "OUTSTANDING, PAID, OVERDUE, PARTIAL_PAID, WRITTEN_OFF",
            "aging_bucket": "Aging category: 0-30 days, 31-60 days, 61-90 days, 90+ days",
            "days_outstanding": "Days since invoice was issued",
            "days_overdue": "Days past due date (0 if not overdue)",
            "days_to_collect": "Days taken to collect payment (for collected invoices)",
            "is_fully_collected": "True if invoice is fully paid",
        }
    },
    "gold_fact_gl": {
        "description": "General Ledger fact table with all posted journal entry lines classified by account type and cost center. Use for financial reporting, expense analysis, and trial balance.",
        "columns": {
            "je_id": "Journal entry identifier",
            "account_code": "GL account code (e.g., 5100 = Salaries)",
            "account_name": "Descriptive account name",
            "account_type": "Asset, Liability, Equity, Revenue, or Expense",
            "account_subtype": "Detailed account classification",
            "cost_center_name": "Business cost center (Engineering, Sales, Marketing, etc.)",
            "department": "Department name",
            "je_date": "Journal entry posting date",
            "period": "Accounting period (YYYY-MM format)",
            "fiscal_year": "Fiscal year",
            "debit_inr": "Debit amount in INR",
            "credit_inr": "Credit amount in INR",
            "net_amount_inr": "Net amount (debit minus credit)",
            "je_type": "MANUAL, ACCRUAL, REVERSAL, SYSTEM_AUTO, PAYROLL, DEPRECIATION",
        }
    },
    "gold_fact_trial_balance": {
        "description": "Period-end trial balance showing opening balances, period movements, and closing balances for all GL accounts. Foundation for financial statements (P&L, Balance Sheet).",
        "columns": {
            "fiscal_year": "Fiscal year",
            "fiscal_quarter": "Fiscal quarter (e.g., 2024-Q1)",
            "period": "Accounting period (YYYY-MM)",
            "account_code": "GL account code",
            "account_name": "Account description",
            "account_type": "Asset, Liability, Equity, Revenue, or Expense",
            "period_debit": "Total debits posted in this period",
            "period_credit": "Total credits posted in this period",
            "ytd_debit": "Year-to-date cumulative debits",
            "ytd_credit": "Year-to-date cumulative credits",
            "closing_balance_inr": "Closing balance at end of period in INR",
            "balance_type": "DR (debit balance) or CR (credit balance)",
            "transaction_count": "Number of transactions in the period",
        }
    }
}

# Apply descriptions via ALTER TABLE / COMMENT ON COLUMN
for table_name, meta in table_descriptions.items():
    full_name = f"{CATALOG}.{SCHEMA}.{table_name}"

    # Table-level comment
    spark.sql(f"ALTER TABLE {full_name} SET TBLPROPERTIES ('comment' = '{meta['description'].replace(chr(39), chr(39)+chr(39))}')")

    # Column-level comments
    for col_name, col_desc in meta.get("columns", {}).items():
        safe_desc = col_desc.replace("'", "''")
        try:
            spark.sql(f"ALTER TABLE {full_name} ALTER COLUMN {col_name} COMMENT '{safe_desc}'")
        except Exception as e:
            print(f"  Column comment error {table_name}.{col_name}: {e}")

    print(f"  Applied descriptions to: {table_name}")

print("\nTable descriptions applied successfully.")

# COMMAND ----------

# MAGIC %md ## Step 2: Create Genie Space via API

# COMMAND ----------

# Get table IDs for the gold layer
gold_tables = [
    "gold_dim_vendor",
    "gold_fact_invoices",
    "gold_fact_payments",
    "gold_dim_customer",
    "gold_fact_sales",
    "gold_fact_collections",
    "gold_fact_gl",
    "gold_fact_trial_balance"
]

# Build table FQNs
table_fqns = [f"{CATALOG}.{SCHEMA}.{t}" for t in gold_tables]

# Create Genie Space
genie_payload = {
    "display_name": "Finance & Accounting Analytics",
    "description": "AI-powered natural language analytics for Finance & Accounting covering Procure-to-Pay (P2P), Order-to-Cash (O2C), and Record-to-Report (R2R) workflows. Ask questions in plain English to get instant insights on invoices, vendors, customers, revenue, and GL data.",
    "tables": [{"name": fqn} for fqn in table_fqns],
    "sample_questions": [
        "Show me all invoices pending for more than 7 days",
        "What are the top 10 vendors by total spend in the last quarter?",
        "Which customers have overdue payments greater than 30 days?",
        "What is the month-over-month revenue growth for this year?",
        "Show invoice aging distribution by aging bucket",
        "What is the average Days Sales Outstanding (DSO) by customer segment?",
        "Which vendors have the most amount mismatches in 3-way matching?",
        "Show me all invoices with AMOUNT_MISMATCH status",
        "What is the total spend by vendor category this year?",
        "Which customers are close to their credit limit?",
        "Show revenue breakdown by product category (software vs services vs support)",
        "What is the total outstanding accounts receivable by region?",
        "Show me unbalanced or failed journal entries",
        "What are the top 5 expense accounts by amount this fiscal year?",
        "Show me payments that were made late (after due date)",
        "What is the trial balance for the current period?",
        "Which invoices have no PO reference?",
        "Show me vendors with more than 5 pending invoices",
        "What is the collection rate by customer segment?",
        "Show spend by cost center and department"
    ],
    "instructions": """You are a Finance & Accounting data analyst assistant with expertise in P2P, O2C, and R2R processes.

Key context:
- All monetary amounts are in INR (Indian Rupees)
- invoice_total_inr and total_spend_inr include 18% GST
- revenue_excl_tax is net revenue excluding GST
- DSO (Days Sales Outstanding) measures how quickly customers pay (lower is better)
- aging_bucket groups outstanding invoices: 0-30 days (current), 31-60 days (watch), 61-90 days (concern), 90+ days (critical)
- match_status: THREE_WAY_MATCHED = best quality, AMOUNT_MISMATCH = needs review, NO_PO_REFERENCE = potential fraud risk
- payment_timing: EARLY = paid before due date, ON_TIME = paid on due date, LATE = paid after due date

Key metrics:
- Invoice Aging = age in days since invoice_date for unpaid invoices (gold_fact_invoices.aging_days)
- DSO = average days to collect from customers (gold_dim_customer.dso or compute from gold_fact_collections)
- Spend by Vendor = sum of invoice_total_inr grouped by vendor_name (gold_fact_invoices)
- Revenue = sum of revenue_excl_tax from gold_fact_sales
- Outstanding AR = sum of balance_outstanding from gold_fact_collections where is_fully_collected = false

When asked about "pending invoices", filter on invoice_status = 'PENDING'.
When asked about "overdue", filter on is_overdue = true or days_overdue > 0.
When asked about "last quarter", use invoice_quarter or so_quarter.
"""
}

genie_result = api_call("POST", "/genie/spaces", genie_payload)
if genie_result:
    genie_space_id = genie_result.get("space_id") or genie_result.get("id")
    print(f"Genie Space created successfully!")
    print(f"Space ID: {genie_space_id}")
    print(f"Space Name: {genie_result.get('display_name', 'Finance & Accounting Analytics')}")
    print(f"\nAccess your Genie Space at:")
    print(f"{WORKSPACE_URL}/genie/spaces/{genie_space_id}")
else:
    print("Note: Genie space API may require specific permissions. Manual setup instructions below.")

# COMMAND ----------

# MAGIC %md ## Step 3: Sample Queries for Demonstration

# COMMAND ----------

print("=" * 70)
print("SAMPLE QUERIES FOR GENIE DEMONSTRATION")
print("=" * 70)

print("""
1. Show invoices pending more than 7 days
""")
spark.sql(f"""
SELECT invoice_id, vendor_name, invoice_date, invoice_total_inr, aging_days, match_status
FROM {CATALOG}.{SCHEMA}.gold_fact_invoices
WHERE invoice_status = 'PENDING' AND aging_days > 7
ORDER BY aging_days DESC
LIMIT 20
""").show(truncate=False)

# COMMAND ----------

print("""
2. Top 10 vendors by spend last quarter
""")
spark.sql(f"""
SELECT
    vendor_name,
    vendor_category,
    COUNT(invoice_id) AS invoice_count,
    SUM(invoice_total_inr) AS total_spend_inr,
    ROUND(AVG(aging_days), 1) AS avg_aging_days
FROM {CATALOG}.{SCHEMA}.gold_fact_invoices
WHERE invoice_quarter = CONCAT(YEAR(ADD_MONTHS(CURRENT_DATE(), -3)), '-Q',
      CEIL(MONTH(ADD_MONTHS(CURRENT_DATE(), -3)) / 3))
GROUP BY vendor_name, vendor_category
ORDER BY total_spend_inr DESC
LIMIT 10
""").show(truncate=False)

# COMMAND ----------

print("""
3. Customers with overdue payments > 30 days
""")
spark.sql(f"""
SELECT
    customer_name,
    segment,
    industry,
    COUNT(o2c_invoice_id) AS overdue_invoices,
    SUM(balance_outstanding) AS total_overdue_amount_inr,
    MAX(days_overdue) AS max_days_overdue
FROM {CATALOG}.{SCHEMA}.gold_fact_collections
WHERE invoice_status = 'OVERDUE' AND days_overdue > 30
GROUP BY customer_name, segment, industry
ORDER BY total_overdue_amount_inr DESC
LIMIT 15
""").show(truncate=False)

# COMMAND ----------

print("""
4. Month-over-Month Revenue Growth
""")
spark.sql(f"""
WITH monthly_revenue AS (
    SELECT
        so_year,
        so_month,
        so_quarter,
        SUM(revenue_excl_tax) AS monthly_revenue
    FROM {CATALOG}.{SCHEMA}.gold_fact_sales
    WHERE so_date >= ADD_MONTHS(CURRENT_DATE(), -12)
    GROUP BY so_year, so_month, so_quarter
),
with_lag AS (
    SELECT *,
        LAG(monthly_revenue) OVER (ORDER BY so_year, so_month) AS prev_month_revenue
    FROM monthly_revenue
)
SELECT
    so_year,
    so_month,
    ROUND(monthly_revenue, 2) AS revenue_inr,
    ROUND(prev_month_revenue, 2) AS prev_month_revenue_inr,
    ROUND((monthly_revenue - prev_month_revenue) / NULLIF(prev_month_revenue, 0) * 100, 1) AS mom_growth_pct
FROM with_lag
ORDER BY so_year, so_month
""").show(20)

# COMMAND ----------

print("""
5. Invoice Aging Analysis
""")
spark.sql(f"""
SELECT
    aging_bucket,
    COUNT(invoice_id) AS invoice_count,
    ROUND(SUM(invoice_total_inr), 2) AS total_amount_inr,
    ROUND(AVG(aging_days), 1) AS avg_aging_days,
    COUNT(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 END) AS three_way_matched
FROM {CATALOG}.{SCHEMA}.gold_fact_invoices
WHERE invoice_status NOT IN ('PAID', 'REJECTED')
GROUP BY aging_bucket
ORDER BY aging_bucket
""").show()

# COMMAND ----------

print("""
6. DSO by Customer Segment
""")
spark.sql(f"""
SELECT
    segment,
    COUNT(customer_id) AS customer_count,
    ROUND(AVG(dso), 1) AS avg_dso_days,
    ROUND(SUM(outstanding_ar_inr), 2) AS total_outstanding_ar,
    ROUND(AVG(collection_rate_pct), 1) AS avg_collection_rate_pct
FROM {CATALOG}.{SCHEMA}.gold_dim_customer
WHERE dso IS NOT NULL
GROUP BY segment
ORDER BY avg_dso_days DESC
""").show()

# COMMAND ----------

print("All sample queries executed successfully!")
print(f"\nGenie Space is ready at: {WORKSPACE_URL}/genie/spaces/")
print("Tables registered:")
for t in gold_tables:
    print(f"  - {CATALOG}.{SCHEMA}.{t}")
