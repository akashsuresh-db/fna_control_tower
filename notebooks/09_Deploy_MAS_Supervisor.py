# Databricks notebook source
# MAGIC %md
# MAGIC # Deploy MAS (Multi-Agent Supervisor) Endpoint
# MAGIC
# MAGIC This notebook:
# MAGIC 1. Reads the Genie Space ID created by task 07 (via task values)
# MAGIC 2. Builds a LangGraph agent that combines Claude + Genie for finance analytics
# MAGIC 3. Registers the agent in Unity Catalog as an MLflow model
# MAGIC 4. Deploys it as a Databricks Model Serving endpoint
# MAGIC 5. Publishes the endpoint name as a task value for the setup script

# COMMAND ----------

dbutils.widgets.text("catalog", "fna_control_tower", "Unity Catalog")
dbutils.widgets.text("schema", "finance_and_accounting", "Schema")
dbutils.widgets.text("serving_endpoint_name", "mas-fna-supervisor", "MAS Endpoint Name")
dbutils.widgets.text("claude_endpoint_name", "fna-claude-sonnet-4-5", "Claude LLM Endpoint")
dbutils.widgets.text("genie_space_id", "", "Genie Space ID (override; uses task value if empty)")

# COMMAND ----------
# Dependencies are pre-installed via the job's environment spec (fna_etl_job.yml)
# databricks-agents, langchain-databricks, langgraph are cached between runs.

# COMMAND ----------

import json, time
import mlflow
import mlflow.langchain
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
)

CATALOG         = dbutils.widgets.get("catalog")
SCHEMA          = dbutils.widgets.get("schema")
ENDPOINT_NAME   = dbutils.widgets.get("serving_endpoint_name")
CLAUDE_ENDPOINT = dbutils.widgets.get("claude_endpoint_name")
_genie_override = dbutils.widgets.get("genie_space_id")

ctx = dbutils.notebook.entry_point.getDbutils().notebook().getContext()
HOST = ctx.apiUrl().get().rstrip("/")

w = WorkspaceClient()

# ── Read Genie Space ID ───────────────────────────────────────────────────────
# Priority: widget override → task value from create_genie_space (task 07)
if _genie_override:
    GENIE_SPACE_ID = _genie_override
    print(f"Genie Space ID from widget: {GENIE_SPACE_ID}")
else:
    try:
        GENIE_SPACE_ID = dbutils.jobs.taskValues.get(
            taskKey="create_genie_space",
            key="genie_space_id",
            default="",
        )
        print(f"Genie Space ID from task values: {GENIE_SPACE_ID}")
    except Exception as e:
        GENIE_SPACE_ID = ""
        print(f"Note: Not running in a job context ({e})")

if not GENIE_SPACE_ID:
    print("⚠ No Genie Space ID — supervisor will be deployed without Genie tool.")
    print("  After creating a Genie Space, re-deploy with --var=genie_space_id=<ID>")

MODEL_NAME = f"{CATALOG}.{SCHEMA}.mas_fna_supervisor"
print(f"\nDeploying: {MODEL_NAME}  →  endpoint: {ENDPOINT_NAME}")

# COMMAND ----------

# ── Build the LangGraph finance supervisor agent ──────────────────────────────
from langchain_core.messages import SystemMessage
from langchain_databricks import ChatDatabricks
from langgraph.prebuilt import create_react_agent

SYSTEM_PROMPT = f"""You are the Finance & Accounting Control Tower supervisor agent.
You have deep expertise in Procure-to-Pay (P2P), Order-to-Cash (O2C), and Record-to-Report (R2R).

Your responsibilities:
- Monitor AP/AR aging, cash flow, GL balances, and exception queues
- Surface anomalies: duplicate invoices, overdue AR, unusual GL postings
- Support drill-down analysis on specific vendors, customers, or time periods
- Recommend escalation actions for critical exceptions

Data access: Use the Genie analytics tool to query the finance data warehouse.
Always ground responses in actual data. Be concise, highlight exceptions proactively.
Genie Space ID: {GENIE_SPACE_ID or 'Not configured — data queries unavailable'}
"""

tools = []

if GENIE_SPACE_ID:
    try:
        from langchain_databricks.genie import GenieTool
        genie_tool = GenieTool(space_id=GENIE_SPACE_ID)
        tools.append(genie_tool)
        print(f"✓ Genie tool attached (space: {GENIE_SPACE_ID})")
    except ImportError:
        print("⚠ langchain_databricks.genie not available — deploy langchain-databricks>=0.3")

llm = ChatDatabricks(endpoint=CLAUDE_ENDPOINT, temperature=0.1)

agent = create_react_agent(
    model=llm,
    tools=tools,
    state_modifier=SYSTEM_PROMPT,
)

print("✓ Agent built")

# COMMAND ----------

# ── Register agent in Unity Catalog ──────────────────────────────────────────
mlflow.set_registry_uri("databricks-uc")
mlflow.langchain.autolog(disable=True)

with mlflow.start_run(run_name=f"mas-fna-supervisor-v{int(time.time())}"):
    model_info = mlflow.langchain.log_model(
        lc_model=agent,
        artifact_path="agent",
        model_config={
            "genie_space_id": GENIE_SPACE_ID,
            "claude_endpoint": CLAUDE_ENDPOINT,
            "catalog": CATALOG,
            "schema": SCHEMA,
        },
        pip_requirements=[
            "mlflow>=2.13",
            "langchain>=0.2",
            "langchain-databricks>=0.3",
            "langgraph>=0.1",
        ],
        input_example={
            "messages": [{"role": "user", "content": "Show me the top overdue invoices"}]
        },
    )
    print(f"✓ Model logged: {model_info.model_uri}")

registered = mlflow.register_model(model_uri=model_info.model_uri, name=MODEL_NAME)
version = registered.version
print(f"✓ Registered: {MODEL_NAME} v{version}")

# COMMAND ----------

# ── Deploy the serving endpoint ───────────────────────────────────────────────
# Try Databricks Agents SDK first (preferred — adds review app, trace UI, etc.)
deployed_endpoint = None

try:
    from databricks import agents as dbx_agents
    deployment = dbx_agents.deploy(
        model_name=MODEL_NAME,
        model_version=int(version),
        endpoint_name=ENDPOINT_NAME,
        environment_vars={
            "GENIE_SPACE_ID": GENIE_SPACE_ID,
            "DATABRICKS_HOST": HOST,
        },
        scale_to_zero=True,
    )
    deployed_endpoint = deployment.endpoint_name
    print(f"✓ Deployed via agents SDK: {deployed_endpoint}")

except Exception as e:
    print(f"agents.deploy() failed ({e}), falling back to serving_endpoints SDK")

    served_entity = ServedEntityInput(
        entity_name=MODEL_NAME,
        entity_version=str(version),
        workload_size="Small",
        scale_to_zero_enabled=True,
        environment_vars={"GENIE_SPACE_ID": GENIE_SPACE_ID},
    )
    config = EndpointCoreConfigInput(served_entities=[served_entity])

    try:
        # Update if exists, create otherwise
        w.serving_endpoints.get(name=ENDPOINT_NAME)
        print(f"Updating existing endpoint: {ENDPOINT_NAME}")
        w.serving_endpoints.update_config_and_wait(name=ENDPOINT_NAME, served_entities=[served_entity])
    except Exception:
        print(f"Creating new endpoint: {ENDPOINT_NAME}")
        w.serving_endpoints.create_and_wait(name=ENDPOINT_NAME, config=config)

    deployed_endpoint = ENDPOINT_NAME
    print(f"✓ Endpoint ready: {deployed_endpoint}")

# COMMAND ----------

# ── Publish outputs ───────────────────────────────────────────────────────────
try:
    dbutils.jobs.taskValues.set(key="mas_endpoint_name", value=deployed_endpoint)
    print(f"✓ Published mas_endpoint_name={deployed_endpoint} as task value")
except Exception as e:
    print(f"Note: taskValues not available (interactive run): {e}")

print(f"\n{'='*60}")
print(f"  MAS Supervisor deployed: {deployed_endpoint}")
print(f"  Genie Space            : {GENIE_SPACE_ID or 'not configured'}")
print(f"  Model in UC            : {MODEL_NAME} v{version}")
print(f"{'='*60}")

dbutils.notebook.exit(deployed_endpoint)
