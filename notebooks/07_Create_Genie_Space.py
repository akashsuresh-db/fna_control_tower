# Databricks notebook source
# MAGIC %md # Create Genie Space - Use serialized_space from existing space as template

# COMMAND ----------

# MAGIC %pip install databricks-sdk --upgrade -q

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

import json, requests
from databricks.sdk import WorkspaceClient

CATALOG = "akash_s_demo"
SCHEMA = "finance_and_accounting"
HOST = "https://adb-984752964297111.11.azuredatabricks.net"
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
w = WorkspaceClient()
warehouse_id = "148ccb90800933a1"  # Shared Endpoint

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

output = {}

# COMMAND ----------

# Step 1: Get serialized_space from an existing space
spaces_resp = requests.get(f"{HOST}/api/2.0/genie/spaces?page_size=10", headers=headers).json()
spaces = spaces_resp.get("spaces", [])
print(f"Found {len(spaces)} spaces")

# Get our own space if available (created by akash.s)
# Use any space to get the serialized_space template
sample_space_id = spaces[0]["space_id"] if spaces else None

# Get full details including serialized_space via different endpoint
for sp in spaces[:5]:
    space_id_to_check = sp["space_id"]
    detail = requests.get(f"{HOST}/api/2.0/genie/spaces/{space_id_to_check}", headers=headers).json()
    serialized = detail.get("serialized_space", "")
    if serialized:
        print(f"Got serialized_space from: {sp.get('title','')}, length: {len(serialized)}")
        # Parse and understand structure
        try:
            parsed = json.loads(serialized)
            print("Top level keys:", list(parsed.keys()))
            output["template_keys"] = list(parsed.keys())
            output["template_space_id"] = space_id_to_check
            output["template_serialized"] = serialized[:500]
        except:
            print("Not JSON:", serialized[:200])
        break
else:
    print("No space has serialized_space in GET response")
    # Try to export a space
    for sp in spaces[:3]:
        export_resp = requests.get(f"{HOST}/api/2.0/genie/spaces/{sp['space_id']}/export", headers=headers)
        print(f"Export {sp['space_id']}: {export_resp.status_code}")
        if export_resp.status_code == 200:
            print("Export response keys:", list(export_resp.json().keys()))

# COMMAND ----------

# Step 2: Create space using the template serialized_space
# If we have a template, modify it; otherwise use minimal JSON

serialized_space_template = output.get("template_serialized")

if not serialized_space_template:
    # Build a minimal serialized_space based on what we know about GenieSpaceExport proto
    # Common protobuf field names for title: "name", "room_name", "display_name"
    # We'll try different structures to find what works
    candidates = [
        {"room_name": "Finance & Accounting Analytics", "warehouse_id": warehouse_id},
        {"name": "Finance & Accounting Analytics", "default_warehouse_id": warehouse_id},
        {"title": "Finance & Accounting Analytics", "warehouseId": warehouse_id},
        {"genie_space": {"title": "Finance & Accounting Analytics"}},
        {},  # completely empty
    ]
    for candidate in candidates:
        resp = requests.post(
            f"{HOST}/api/2.0/genie/spaces",
            headers=headers,
            json={
                "title": "Finance & Accounting Analytics",
                "warehouse_id": warehouse_id,
                "serialized_space": json.dumps(candidate)
            }
        )
        msg = resp.json().get("message", "")
        print(f"Candidate {list(candidate.keys())}: {resp.status_code} - {msg[:200]}")
        if resp.status_code in [200, 201]:
            output["space_id"] = resp.json().get("space_id")
            output["status"] = "SUCCESS"
            break

# COMMAND ----------

# Step 3: Use SDK with positional args
if "space_id" not in output:
    # The create_space signature is: create_space(warehouse_id, serialized_space, ...)
    # serialized_space must be a non-empty string
    # Try various serialization formats
    for ss_format in [
        '{"tables": []}',  # minimal with tables
        '{"instructions": ""}',  # minimal with instructions
        '{"content": []}',  # content-based
        '{"version": 1}',  # version-based
        '{"id": ""}',  # id-based
    ]:
        try:
            created = w.genie.create_space(
                warehouse_id=warehouse_id,
                serialized_space=ss_format,
                title="Finance & Accounting Analytics",
                description="Analytics for P2P, O2C, and R2R Finance."
            )
            output["space_id"] = created.space_id
            output["status"] = f"SUCCESS_ss_{ss_format[:30]}"
            print(f"Created with: {ss_format[:30]}")
            break
        except Exception as e:
            err = str(e)
            print(f"ss={ss_format[:30]}: {err[:150]}")
            if "space_id" not in output and "Cannot find field" in err:
                # Extract the field name from error
                import re
                match = re.search(r"Cannot find field: (\w+)", err)
                if match:
                    output[f"missing_field_for_{ss_format[:20]}"] = match.group(1)

# COMMAND ----------

space_id = output.get("space_id")
if space_id:
    output["url"] = f"{HOST}/genie/spaces/{space_id}"
    print(f"GENIE SPACE CREATED! URL: {output['url']}")
else:
    print("API creation failed - need manual creation via UI")
    print("Manual steps:")
    print("1. Go to: https://adb-984752964297111.11.azuredatabricks.net")
    print("2. Navigate to: Genie (left sidebar)")
    print("3. Click: New Genie Space")
    print("4. Title: Finance & Accounting Analytics")
    print("5. Add tables: akash_s_demo.finance_and_accounting.gold_*")

dbutils.notebook.exit(json.dumps(output))
