#!/usr/bin/env python3
"""
Deployment script for Finance & Accounting Demo
Target: https://westus.azuredatabricks.net (org ID: 2338896885246877)
Catalog: akash_s_demo | Schema: finance_and_accounting
"""
import base64
import json
import os
import subprocess
import time
from pathlib import Path

import requests

# ── Config ─────────────────────────────────────────────────────────────────────
WORKSPACE_HOST = "https://westus.azuredatabricks.net"
ORG_ID = "2338896885246877"
CATALOG = "akash_s_demo"
SCHEMA = "finance_and_accounting"
WAREHOUSE_ID = "e69629978b5a7e40"
WORKSPACE_NOTEBOOK_DIR = "/Users/akash.s@databricks.com/finance-accounting-demo"
APP_NAME = "finance-accounting-demo"
PROJECT_DIR = Path(__file__).parent

SOURCE_CATALOG = "akash_s_demo"  # what notebooks currently reference


# ── Auth ────────────────────────────────────────────────────────────────────────
def get_azure_token() -> str:
    result = subprocess.run(
        ["az", "account", "get-access-token",
         "--resource", "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["accessToken"]


class DatabricksAPI:
    def __init__(self):
        self._token = None
        self._token_ts = 0
        self.session = requests.Session()
        self.session.headers["X-Databricks-Org-Id"] = ORG_ID

    def _refresh_token(self):
        now = time.time()
        if now - self._token_ts > 2400:  # refresh every 40 min
            print("  [auth] Refreshing Azure token...")
            self._token = get_azure_token()
            self._token_ts = now
            self.session.headers["Authorization"] = f"Bearer {self._token}"

    def get(self, path, **kwargs):
        self._refresh_token()
        r = self.session.get(f"{WORKSPACE_HOST}{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    def post(self, path, **kwargs):
        self._refresh_token()
        r = self.session.post(f"{WORKSPACE_HOST}{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    def put(self, path, **kwargs):
        self._refresh_token()
        r = self.session.put(f"{WORKSPACE_HOST}{path}", **kwargs)
        r.raise_for_status()
        return r.json()

    def delete(self, path, **kwargs):
        self._refresh_token()
        r = self.session.delete(f"{WORKSPACE_HOST}{path}", **kwargs)
        r.raise_for_status()
        return r.json()


api = DatabricksAPI()


# ── Step helpers ────────────────────────────────────────────────────────────────
def step(msg: str):
    print(f"\n{'='*60}\n{msg}\n{'='*60}")


def ensure_workspace_dir(path: str):
    try:
        api.post("/api/2.0/workspace/mkdirs", json={"path": path})
        print(f"  Created directory: {path}")
    except Exception as e:
        print(f"  Directory exists (or error): {e}")


def upload_notebook(local_path: Path, remote_path: str):
    content = local_path.read_text()
    # Patch catalog references
    content = content.replace(SOURCE_CATALOG, CATALOG)
    # Ensure schema creation before USE SCHEMA (in case it doesn't exist)
    content = content.replace(
        f'spark.sql(f"USE CATALOG {{{CATALOG}}}")\nspark.sql(f"USE SCHEMA {{{SCHEMA}}}")',
        f'spark.sql(f"USE CATALOG {{{CATALOG}}}")\nspark.sql(f"CREATE SCHEMA IF NOT EXISTS {{{CATALOG}}}.{{{SCHEMA}}}")\nspark.sql(f"USE SCHEMA {{{SCHEMA}}}")',
    )
    b64 = base64.b64encode(content.encode()).decode()
    api.post("/api/2.0/workspace/import", json={
        "path": remote_path,
        "language": "PYTHON",
        "format": "SOURCE",
        "content": b64,
        "overwrite": True,
    })
    print(f"  Uploaded: {remote_path}")


def run_notebook_job(notebook_path: str, job_name: str, params: dict = None,
                     timeout_minutes: int = 45) -> str:
    """Create one-time job, run it, wait, return run_id."""
    task = {
        "task_key": "main",
        "notebook_task": {
            "notebook_path": notebook_path,
            "base_parameters": params or {},
            "source": "WORKSPACE",
        },
        "new_cluster": {
            "num_workers": 0,
            "spark_version": "15.4.x-scala2.12",
            "node_type_id": "Standard_DS3_v2",
            "spark_conf": {"spark.databricks.cluster.profile": "singleNode"},
            "custom_tags": {"ResourceClass": "SingleNode"},
            "data_security_mode": "SINGLE_USER",
            "runtime_engine": "STANDARD",
        },
    }
    job = api.post("/api/2.1/jobs/create", json={
        "name": job_name,
        "tasks": [task],
        "max_concurrent_runs": 1,
    })
    job_id = job["job_id"]
    run = api.post("/api/2.1/jobs/run-now", json={"job_id": job_id})
    run_id = run["run_id"]
    print(f"  Job {job_id} started, run_id={run_id}")
    _wait_for_run(run_id, timeout_minutes)
    # Clean up job
    try:
        api.post("/api/2.1/jobs/delete", json={"job_id": job_id})
    except Exception:
        pass
    return run_id


def _wait_for_run(run_id: str, timeout_minutes: int = 45):
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        run = api.get(f"/api/2.1/jobs/runs/get?run_id={run_id}")
        state = run["state"]["life_cycle_state"]
        result = run["state"].get("result_state", "")
        print(f"    Run {run_id}: {state} {result}")
        if state in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            if result != "SUCCESS":
                raise RuntimeError(
                    f"Run {run_id} failed: {result} — "
                    f"{run['state'].get('state_message','')}"
                )
            print(f"  ✓ Run {run_id} completed successfully")
            return
        time.sleep(20)
    raise TimeoutError(f"Run {run_id} timed out after {timeout_minutes}m")


def create_dlt_pipeline(notebook_path: str) -> str:
    """Create DLT pipeline and return pipeline_id."""
    payload = {
        "name": "Finance Accounting DLT",
        "target": SCHEMA,
        "catalog": CATALOG,
        "libraries": [{"notebook": {"path": notebook_path}}],
        "serverless": True,
        "channel": "CURRENT",
        "development": False,
        "continuous": False,
    }
    try:
        result = api.post("/api/2.0/pipelines", json=payload)
        pipeline_id = result["pipeline_id"]
        print(f"  Created DLT pipeline: {pipeline_id}")
        return pipeline_id
    except requests.exceptions.HTTPError as e:
        # May already exist — search for it
        pipelines = api.get("/api/2.0/pipelines?max_results=50")
        for p in pipelines.get("statuses", []):
            if p["name"] == "Finance Accounting DLT":
                print(f"  Reusing existing DLT pipeline: {p['pipeline_id']}")
                return p["pipeline_id"]
        raise


def run_dlt_pipeline(pipeline_id: str, timeout_minutes: int = 60):
    update = api.post(f"/api/2.0/pipelines/{pipeline_id}/updates", json={
        "full_refresh": True
    })
    update_id = update["update_id"]
    print(f"  DLT update started: {update_id}")
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        status = api.get(f"/api/2.0/pipelines/{pipeline_id}/updates/{update_id}")
        state = status["update"]["state"]
        print(f"    DLT pipeline: {state}")
        if state == "COMPLETED":
            print(f"  ✓ DLT pipeline completed")
            return
        if state in ("FAILED", "CANCELED"):
            raise RuntimeError(f"DLT pipeline {state}: {status}")
        time.sleep(30)
    raise TimeoutError(f"DLT pipeline timed out after {timeout_minutes}m")


def get_or_create_lakebase():
    """Check for existing Lakebase instance or create one."""
    # List instances
    try:
        result = api.get("/api/2.0/database/instances")
        instances = result.get("instances", [])
        for inst in instances:
            if "finance" in inst.get("name", "").lower():
                print(f"  Found existing Lakebase: {inst['name']} ({inst['id']})")
                return inst
        # Create new
        inst = api.post("/api/2.0/database/instances", json={
            "name": "finance-ops-db",
            "capacity": {"storage_gb": 64}
        })
        print(f"  Created Lakebase: {inst['name']} ({inst['id']})")
        # Wait for it to be ready
        inst_id = inst["id"]
        for _ in range(30):
            time.sleep(10)
            inst = api.get(f"/api/2.0/database/instances/{inst_id}")
            if inst.get("state") == "RUNNING":
                print(f"  ✓ Lakebase is running")
                return inst
            print(f"    Lakebase state: {inst.get('state')}")
        return inst
    except Exception as e:
        print(f"  Lakebase not available or error: {e}")
        return None


def deploy_app(lakebase_instance=None):
    """Deploy Databricks App."""
    app_dir = PROJECT_DIR / "app"

    # Build frontend first
    step("Building React frontend")
    frontend_dir = app_dir / "frontend"
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=frontend_dir, capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  npm build stdout: {result.stdout[-2000:]}")
        print(f"  npm build stderr: {result.stderr[-2000:]}")
        raise RuntimeError("Frontend build failed")
    print("  ✓ Frontend built")

    # Update app.yaml
    _update_app_yaml(lakebase_instance)

    # Check if app exists
    try:
        existing = api.get(f"/api/2.0/apps/{APP_NAME}")
        print(f"  App {APP_NAME} exists, updating...")
        _update_and_start_app(app_dir)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  Creating new app: {APP_NAME}")
            _create_and_deploy_app(app_dir, lakebase_instance)
        else:
            raise


def _update_app_yaml(lakebase_instance=None):
    yaml_path = PROJECT_DIR / "app" / "app.yaml"
    content = yaml_path.read_text()
    content = content.replace("148ccb90800933a1", WAREHOUSE_ID)
    content = content.replace("akash_s_demo", CATALOG)
    # Update schema env var
    import re
    content = re.sub(
        r'(name: DATABRICKS_SCHEMA\s*\n\s*value:\s*)"[^"]*"',
        f'\\1"{SCHEMA}"',
        content
    )
    if lakebase_instance:
        lb_id = lakebase_instance.get("id", "")
        # Update lakebase resource ID
        content = re.sub(
            r'(database:\s*\n\s*id:\s*)"[^"]*"',
            f'\\1"{lb_id}"',
            content
        )
    yaml_path.write_text(content)
    print(f"  ✓ Updated app.yaml")


def _create_and_deploy_app(app_dir: Path, lakebase_instance=None):
    """Create app via API then deploy via CLI."""
    # Build resources list
    resources = [
        {
            "name": "sql-warehouse",
            "sql_warehouse": {"id": WAREHOUSE_ID, "permission": "CAN_USE"},
        },
        {
            "name": "claude-endpoint",
            "serving_endpoint": {"name": "databricks-claude-sonnet-4-5", "permission": "CAN_QUERY"},
        },
    ]
    if lakebase_instance:
        resources.append({
            "name": "finance-ops-lakebase",
            "database": {"id": lakebase_instance["id"], "permission": "CAN_CONNECT"},
        })

    payload = {
        "name": APP_NAME,
        "description": "Finance & Accounting Control Tower",
        "resources": resources,
    }
    app = api.post("/api/2.0/apps", json=payload)
    print(f"  ✓ App created: {app.get('url', APP_NAME)}")
    _wait_for_app_active(APP_NAME)
    _sync_app_files(app_dir)
    _start_app(APP_NAME)


def _update_and_start_app(app_dir: Path):
    _sync_app_files(app_dir)
    _start_app(APP_NAME)


def _sync_app_files(app_dir: Path):
    """Sync app files using Databricks CLI (still needed for file sync)."""
    # Use CLI with env vars for auth
    env = os.environ.copy()
    env["DATABRICKS_HOST"] = WORKSPACE_HOST
    env["DATABRICKS_TOKEN"] = get_azure_token()
    # Note: CLI doesn't support shared endpoint natively; use direct file upload API

    # Upload app files via workspace files API
    _upload_app_files_via_api(app_dir)


def _upload_app_files_via_api(app_dir: Path):
    """Upload all app source files to Databricks workspace for the app."""
    import mimetypes

    # Files to upload (relative to app_dir)
    skip_dirs = {'.venv', '__pycache__', 'node_modules', '.git', 'dist', '.databricks'}
    skip_exts = {'.pyc', '.pyo'}

    uploaded = 0
    for fpath in app_dir.rglob('*'):
        if fpath.is_dir():
            continue
        # Check if in skip dirs
        parts = fpath.relative_to(app_dir).parts
        if any(d in skip_dirs for d in parts):
            continue
        if fpath.suffix in skip_exts:
            continue
        # Skip frontend source (only upload dist)
        if 'frontend' in parts and 'dist' not in parts:
            continue

        rel = fpath.relative_to(app_dir)
        remote = f"/api/2.0/fs/files/apps/{APP_NAME}/{rel}"
        try:
            content = fpath.read_bytes()
            api.put(remote,
                    data=content,
                    headers={"Content-Type": "application/octet-stream"})
            uploaded += 1
        except Exception as e:
            print(f"    Warning uploading {rel}: {e}")

    print(f"  ✓ Uploaded {uploaded} app files")


def _wait_for_app_active(app_name: str, timeout: int = 120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app = api.get(f"/api/2.0/apps/{app_name}")
        state = app.get("compute_status", {}).get("state", app.get("status", ""))
        print(f"    App state: {state}")
        if state in ("ACTIVE", "RUNNING", "DEPLOYED"):
            return
        if state == "ERROR":
            raise RuntimeError(f"App in error state: {app}")
        time.sleep(10)


def _start_app(app_name: str):
    try:
        api.post(f"/api/2.0/apps/{app_name}/start", json={})
        print(f"  Started app: {app_name}")
    except Exception as e:
        print(f"  Start app (may already be running): {e}")


# ── Main deployment flow ────────────────────────────────────────────────────────
def main():
    # 1. Verify auth
    step("Step 0: Verify authentication")
    me = api.get("/api/2.0/preview/scim/v2/Me")
    print(f"  Authenticated as: {me.get('userName')}")

    # 2. Upload notebooks
    step("Step 1: Upload notebooks")
    ensure_workspace_dir(WORKSPACE_NOTEBOOK_DIR)
    notebooks_dir = PROJECT_DIR / "notebooks"
    notebook_files = sorted(notebooks_dir.glob("*.py"))
    notebook_paths = {}
    for nb in notebook_files:
        remote = f"{WORKSPACE_NOTEBOOK_DIR}/{nb.stem}"
        upload_notebook(nb, remote)
        notebook_paths[nb.stem] = remote
    print(f"  ✓ Uploaded {len(notebook_files)} notebooks")

    # 3. Data generation
    step("Step 2: Run data generation (notebook 00)")
    nb00 = notebook_paths.get("00_Setup_and_Data_Generation",
                               f"{WORKSPACE_NOTEBOOK_DIR}/00_Setup_and_Data_Generation")
    run_notebook_job(nb00, "Finance-00-DataGen", timeout_minutes=60)

    # 4. DLT pipeline
    step("Step 3: Create and run DLT pipeline (notebook 01)")
    nb01 = notebook_paths.get("01_DLT_Pipeline",
                               f"{WORKSPACE_NOTEBOOK_DIR}/01_DLT_Pipeline")
    pipeline_id = create_dlt_pipeline(nb01)
    run_dlt_pipeline(pipeline_id, timeout_minutes=60)

    # 5. Gold layer notebooks
    step("Step 4: Run Gold layer notebooks (02-04)")
    for name in ["02_Gold_Layer_P2P", "03_Gold_Layer_O2C", "04_Gold_Layer_R2R"]:
        nb = notebook_paths.get(name, f"{WORKSPACE_NOTEBOOK_DIR}/{name}")
        print(f"  Running {name}...")
        run_notebook_job(nb, f"Finance-{name[:2]}", timeout_minutes=30)

    # 6. AI processing
    step("Step 5: Run Invoice AI Processing (notebook 05)")
    nb05 = notebook_paths.get("05_Invoice_AI_Processing",
                               f"{WORKSPACE_NOTEBOOK_DIR}/05_Invoice_AI_Processing")
    run_notebook_job(nb05, "Finance-05-AIProc", timeout_minutes=30)

    # 7. Lakebase
    step("Step 6: Provision Lakebase")
    lakebase = get_or_create_lakebase()

    # 8. Deploy app
    step("Step 7: Update app.yaml + Build + Deploy App")
    deploy_app(lakebase)

    step("✅ Deployment Complete!")
    try:
        app = api.get(f"/api/2.0/apps/{APP_NAME}")
        url = app.get("url", "")
        print(f"\nApp URL: {url}")
    except Exception:
        print(f"\nApp deployed as: {APP_NAME}")


if __name__ == "__main__":
    main()
