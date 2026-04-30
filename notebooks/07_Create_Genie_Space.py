# Databricks notebook source
# MAGIC %md # Create Genie Space for Finance & Accounting Analytics

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower", "Unity Catalog")
dbutils.widgets.text("schema", "finance_and_accounting", "Schema")
dbutils.widgets.text("warehouse_id", "", "SQL Warehouse ID")

# COMMAND ----------

import json, requests
from databricks.sdk import WorkspaceClient

CATALOG = dbutils.widgets.get("catalog")
SCHEMA = dbutils.widgets.get("schema")
WAREHOUSE_ID = dbutils.widgets.get("warehouse_id")

ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
token = ctx.apiToken().get()
HOST = ctx.apiUrl().get().rstrip("/")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
w = WorkspaceClient()

SPACE_TITLE = "Finance & Accounting Analytics"
SPACE_DESC = "Real-time P2P, O2C, and R2R finance analytics for the Control Tower"

print(f"Host  : {HOST}")
print(f"Catalog: {CATALOG}.{SCHEMA}")
print(f"WH ID  : {WAREHOUSE_ID}")

# COMMAND ----------

# ── Step 1: Check if our Genie Space already exists ──────────────────────────
spaces_resp = requests.get(f"{HOST}/api/2.0/genie/spaces?page_size=50", headers=headers).json()
spaces = spaces_resp.get("spaces", [])
print(f"Found {len(spaces)} existing spaces")

space_id = None
for sp in spaces:
    if sp.get("title") == SPACE_TITLE:
        space_id = sp["space_id"]
        print(f"✓ Space already exists: {space_id}")
        break

# COMMAND ----------

# ── Step 2: Create the space if it doesn't exist ─────────────────────────────
if not space_id:
    # Approach A: Without serialized_space (field may be optional in newer API versions)
    body = {
        "title": SPACE_TITLE,
        "description": SPACE_DESC,
        "warehouse_id": WAREHOUSE_ID,
    }
    resp = requests.post(f"{HOST}/api/2.0/genie/spaces", headers=headers, json=body)
    print(f"Approach A (no serialized_space): {resp.status_code}")
    if resp.status_code in (200, 201):
        space_id = resp.json().get("space_id")
        print(f"✓ Created via Approach A: {space_id}")

# COMMAND ----------

if not space_id:
    # Approach B: Clone serialized_space from an existing space in this workspace
    template_serialized = None
    for sp in spaces[:10]:
        detail = requests.get(f"{HOST}/api/2.0/genie/spaces/{sp['space_id']}", headers=headers).json()
        serialized = detail.get("serialized_space", "")
        if serialized:
            template_serialized = serialized
            print(f"Got template from '{sp.get('title', '')}' ({len(serialized)} chars)")
            break

    if not template_serialized:
        # Try export endpoint
        for sp in spaces[:5]:
            r = requests.get(f"{HOST}/api/2.0/genie/spaces/{sp['space_id']}/export", headers=headers)
            if r.status_code == 200 and r.json().get("serialized_space"):
                template_serialized = r.json()["serialized_space"]
                print(f"Got template from export")
                break

    if template_serialized:
        body = {
            "title": SPACE_TITLE,
            "description": SPACE_DESC,
            "warehouse_id": WAREHOUSE_ID,
            "serialized_space": template_serialized,
        }
        resp = requests.post(f"{HOST}/api/2.0/genie/spaces", headers=headers, json=body)
        print(f"Approach B (template serialized_space): {resp.status_code}")
        if resp.status_code in (200, 201):
            space_id = resp.json().get("space_id")
            print(f"✓ Created via Approach B: {space_id}")
        else:
            print(f"  Response: {resp.text[:300]}")

# COMMAND ----------

if not space_id:
    # Approach C: SDK create_space with minimal serialized_space payloads
    for ss in ['{}', '{"tables":[]}', '{"version":1}', '{"content":[]}']:
        try:
            created = w.genie.create_space(
                warehouse_id=WAREHOUSE_ID,
                serialized_space=ss,
                title=SPACE_TITLE,
                description=SPACE_DESC,
            )
            space_id = created.space_id
            print(f"✓ Created via SDK (ss='{ss}'): {space_id}")
            break
        except Exception as e:
            print(f"SDK ss='{ss}': {str(e)[:120]}")

# COMMAND ----------

# ── Step 3: Publish result ────────────────────────────────────────────────────
output = {}

if space_id:
    output["space_id"] = space_id
    output["url"] = f"{HOST}/genie/spaces/{space_id}"
    output["status"] = "SUCCESS"
    print(f"\n✓ Genie Space ready: {output['url']}")

    # Publish as a task value so downstream tasks (08, 09) can consume it
    try:
        dbutils.jobs.taskValues.set(key="genie_space_id", value=space_id)
        print("✓ Published genie_space_id as task value")
    except Exception as e:
        print(f"Note: taskValues not available (interactive run): {e}")
else:
    output["space_id"] = ""
    output["status"] = "MANUAL_REQUIRED"
    print("\n⚠ Automated creation failed. Manual steps:")
    print(f"  1. Open {HOST}")
    print("  2. Sidebar → Genie → New Genie Space")
    print(f"  3. Title: {SPACE_TITLE}")
    print(f"  4. Warehouse: {WAREHOUSE_ID}")
    print(f"  5. After creation, re-run bundle deploy with the space ID")

    try:
        dbutils.jobs.taskValues.set(key="genie_space_id", value="")
    except Exception:
        pass

print(f"\nOutput: {json.dumps(output)}")
dbutils.notebook.exit(json.dumps(output))
