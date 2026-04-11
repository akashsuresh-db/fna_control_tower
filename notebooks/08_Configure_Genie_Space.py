# Databricks notebook source
# MAGIC %md # Configure Genie Space - Add Tables and Instructions

# COMMAND ----------

# MAGIC %pip install databricks-sdk --upgrade -q

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json, requests
from databricks.sdk import WorkspaceClient

CATALOG = "hp_sf_test"
SCHEMA = "finance_and_accounting"
HOST = "https://adb-984752964297111.11.azuredatabricks.net"
SPACE_ID = "01f122c95c741815919b6457017f0899"

token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
w = WorkspaceClient()
warehouse_id = "148ccb90800933a1"

gold_tables = [
    f"{CATALOG}.{SCHEMA}.gold_dim_vendor",
    f"{CATALOG}.{SCHEMA}.gold_fact_invoices",
    f"{CATALOG}.{SCHEMA}.gold_fact_payments",
    f"{CATALOG}.{SCHEMA}.gold_dim_customer",
    f"{CATALOG}.{SCHEMA}.gold_fact_sales",
    f"{CATALOG}.{SCHEMA}.gold_fact_collections",
    f"{CATALOG}.{SCHEMA}.gold_fact_gl",
    f"{CATALOG}.{SCHEMA}.gold_fact_trial_balance",
]

output = {"space_id": SPACE_ID, "url": f"{HOST}/genie/spaces/{SPACE_ID}"}

# COMMAND ----------

# Get current space state
current = requests.get(f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}", headers=headers).json()
print("Current space:", json.dumps(current, indent=2))

# COMMAND ----------

# Inspect the serialized_space structure by trying to update with table references
# The serialized_space must include the version:1 + table metadata
# Try updating with table_identifiers via the correct JSON path in serialized_space

# Based on the format: {"version": 1} worked for creation
# Try adding table_identifiers within serialized_space
for tables_key in ["table_identifiers", "tables", "data_sources", "curated_tables"]:
    ss = json.dumps({"version": 1, tables_key: gold_tables})
    resp = requests.patch(
        f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}",
        headers=headers,
        json={
            "title": "Finance & Accounting Analytics",
            "warehouse_id": warehouse_id,
            "serialized_space": ss
        }
    )
    msg = resp.json().get("message", resp.text[:200])
    print(f"PATCH with {tables_key}: {resp.status_code} - {msg[:200]}")
    if resp.status_code in [200, 201]:
        output[f"update_status"] = f"SUCCESS_{tables_key}"
        break

# COMMAND ----------

# Try SDK update_space
try:
    updated = w.genie.update_space(
        space_id=SPACE_ID,
        warehouse_id=warehouse_id,
        serialized_space=json.dumps({"version": 1}),
        title="Finance & Accounting Analytics",
        description="""AI-powered analytics for Finance & Accounting (P2P, O2C, R2R).
Ask questions like: show invoices pending 7+ days, top vendors by spend, customers with overdue payments, monthly revenue growth."""
    )
    print("SDK update succeeded:", updated)
    output["sdk_update"] = "SUCCESS"
except Exception as e:
    print("SDK update error:", e)
    output["sdk_update_error"] = str(e)[:200]

# COMMAND ----------

# Try to add tables via a different API endpoint
# Check if there's a tables sub-resource
for method in ["POST", "PUT", "PATCH"]:
    resp = requests.request(
        method,
        f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}/tables",
        headers=headers,
        json={"table_identifiers": gold_tables}
    )
    print(f"{method} /tables: {resp.status_code} - {resp.text[:200]}")

# COMMAND ----------

# Try to update with proper table path in serialized_space
# After experimenting, try adding a "curated_questions" and "instructions" via update
INSTRUCTIONS = """You are a Finance & Accounting analytics assistant. Key context:
- All monetary amounts are in INR (Indian Rupees)
- invoice_total_inr includes 18% GST; revenue_excl_tax is net
- aging_bucket groups: 0-30 days (current), 31-60 (watch), 61-90 (concern), 90+ (critical)
- match_status: THREE_WAY_MATCHED=best, AMOUNT_MISMATCH=review, NO_PO_REFERENCE=risk
- DSO = Days Sales Outstanding (average days customers take to pay, lower=better)
- invoice_status: PENDING, APPROVED, PAID, REJECTED, UNDER_REVIEW
- For overdue: filter is_overdue=true or days_overdue>0"""

# Build serialized_space with instructions
ss_with_instructions = json.dumps({
    "version": 1,
    "instructions": INSTRUCTIONS,
    "curated_questions": [
        "Show invoices pending more than 7 days",
        "Top 10 vendors by spend last quarter",
        "Customers with overdue payments > 30 days",
        "Month-over-month revenue growth",
        "Invoice aging distribution by bucket",
        "DSO by customer segment",
        "Vendors with amount mismatches in 3-way matching",
        "Top 5 expense accounts this fiscal year",
        "Revenue breakdown by product category",
        "Total outstanding accounts receivable by region"
    ]
})

resp = requests.patch(
    f"{HOST}/api/2.0/genie/spaces/{SPACE_ID}",
    headers=headers,
    json={
        "title": "Finance & Accounting Analytics",
        "warehouse_id": warehouse_id,
        "serialized_space": ss_with_instructions
    }
)
print(f"Update with instructions: {resp.status_code} - {resp.text[:300]}")
if resp.status_code in [200, 201]:
    output["instructions_added"] = True

# COMMAND ----------

print(f"\n=== GENIE SPACE READY ===")
print(f"Space ID: {SPACE_ID}")
print(f"URL: {HOST}/genie/spaces/{SPACE_ID}")
print(f"\nNow manually add tables in the UI:")
for t in gold_tables:
    print(f"  - {t}")

output["final_url"] = f"{HOST}/genie/spaces/{SPACE_ID}"
dbutils.notebook.exit(json.dumps(output))
