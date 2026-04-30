#!/usr/bin/env python3
"""
FnA Control Tower - Automated Demo Setup
=========================================

Orchestrates the full demo in the correct dependency order:

  Phase 1 │ bundle deploy
           │  └─ Creates: warehouse (Serverless PRO), DLT pipeline, ETL job, App
           │              Catalog/schema referenced via ${var.catalog}/${var.schema}
           │
  Phase 2  │ bundle run fna_etl_workflow
           │  ├─ task 00: data generation (bronze tables + PDF invoices in UC Volume)
           │  ├─ task 01: DLT pipeline (bronze → silver, including
           │  │            bronze_invoice_pdfs + silver_invoice_extractions via ai_parse_document)
           │  ├─ tasks 02-04: gold layer (P2P / O2C / R2R, parallel)
           │  └─ task 05: KPI view
           │
  Phase 3  │ Create MAS supervisor agent via REST API
           │  POST /api/2.1/supervisor-agents
           │  ├─ Creates endpoint: mas-<uuid>-endpoint (READY in ~2 min)
           │  └─ Optionally links a Genie Space (--genie-space-id)
           │
           │  Note on Genie Space: Databricks does not support programmatic
           │  creation of Genie Spaces from scratch (API requires serialized_space
           │  from an existing space). Create one manually in the Databricks UI:
           │    AI/BI → Genie → New Space → add tables from fna_control_tower
           │  Then pass its ID with --genie-space-id <id>.
           │
  Phase 4  │ bundle deploy --var serving_endpoint_name=<mas-endpoint>
           │  └─ Wires the MAS endpoint name into app config.env

Usage:
  python3 scripts/setup.py [target] [--profile PROFILE] [--skip-etl] [--skip-deploy]
  python3 scripts/setup.py [target] --genie-space-id <space_id>
  python3 scripts/setup.py [target] --extract-only   # re-wire from last run

Examples:
  python3 scripts/setup.py fevm
  python3 scripts/setup.py fevm --genie-space-id 01f04ddd1d4918b4aecb5e0b9c4e4ce2
  python3 scripts/setup.py fevm --skip-etl          # re-run phases 3+4 only
"""

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent  # repo root

# ── Try to import Databricks SDK ──────────────────────────────────────────────
try:
    from databricks.sdk import WorkspaceClient
    HAS_SDK = True
except ImportError:
    HAS_SDK = False
    print("⚠ databricks-sdk not installed — using REST API directly")
    print("  Install with: pip install databricks-sdk")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    cmd_str = " ".join(cmd)
    print(f"\n  $ {cmd_str}")
    result = subprocess.run(cmd, cwd=ROOT, **kwargs)
    if result.returncode != 0:
        print(f"\n✗ Command failed (exit {result.returncode}): {cmd_str}", file=sys.stderr)
        sys.exit(result.returncode)
    return result


def section(title: str) -> None:
    print(f"\n{'═'*60}")
    print(f"  {title}")
    print(f"{'═'*60}")


def _get_host_and_token(profile: str | None = None) -> tuple[str, str]:
    """Get workspace host and OAuth token from the Databricks CLI."""
    env_cmd = ["databricks", "auth", "env"]
    if profile:
        env_cmd += ["--profile", profile]

    r = subprocess.run(env_cmd, capture_output=True, text=True, cwd=ROOT)
    host = ""
    try:
        # Output is JSON: {"env": {"DATABRICKS_HOST": "...", ...}}
        # Strip any leading warning lines before the JSON object
        stdout = r.stdout.strip()
        json_start = stdout.find("{")
        if json_start != -1:
            env_data = json.loads(stdout[json_start:])
            host = env_data.get("env", {}).get("DATABRICKS_HOST", "")
    except Exception:
        pass

    if not host:
        # Fallback: read profile directly from config
        import configparser, os
        cfg_path = Path.home() / ".databrickscfg"
        if cfg_path.exists():
            cfg = configparser.ConfigParser()
            cfg.read(cfg_path)
            section = profile or "DEFAULT"
            host = cfg.get(section, "host", fallback="")

    tok_cmd = ["databricks", "auth", "token"]
    if profile:
        tok_cmd += ["--profile", profile]
    r2 = subprocess.run(tok_cmd, capture_output=True, text=True, cwd=ROOT)
    try:
        tok_data = json.loads(r2.stdout)
        token = tok_data.get("access_token", "")
    except Exception:
        token = ""

    return host.rstrip("/"), token


def _api(method: str, path: str, body: dict | None = None,
         host: str = "", token: str = "", timeout: int = 30) -> dict | str:
    url = f"{host.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body_text = e.read().decode()
        try:
            return json.loads(body_text)
        except Exception:
            return body_text
    except Exception as e:
        return {"error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1: Bundle deploy
# ─────────────────────────────────────────────────────────────────────────────

def _grant_catalog_permissions(host: str, token: str, catalog: str, schema: str,
                               sp_client_id: str) -> None:
    """
    Grant the app's service principal access to the Unity Catalog.

    The bundle cannot currently express UC permissions for a service principal
    (only IAM-level warehouse permissions are bundle-manageable). These grants
    must be applied via SQL after the bundle creates the catalog and schema.
    """
    if not sp_client_id:
        print("  ⚠ Could not determine app service principal — skipping UC grants")
        return

    warehouse_id = ""
    wh_resp = _api("GET", "/api/2.0/sql/warehouses", host=host, token=token)
    if isinstance(wh_resp, dict):
        for wh in wh_resp.get("warehouses", []):
            if "FnA Control Tower" in (wh.get("name") or ""):
                warehouse_id = wh.get("id", "")
                break

    if not warehouse_id:
        print("  ⚠ Could not find FnA warehouse for UC grants — skipping")
        return

    def sql(stmt: str) -> str:
        r = _api("POST", "/api/2.0/sql/statements", body={
            "statement": stmt,
            "warehouse_id": warehouse_id,
            "wait_timeout": "30s",
        }, host=host, token=token, timeout=60)
        if isinstance(r, dict):
            return r.get("status", {}).get("state", "UNKNOWN")
        return "ERROR"

    grants = [
        f"GRANT USE CATALOG ON CATALOG {catalog} TO `{sp_client_id}`",
        f"GRANT USE SCHEMA ON SCHEMA {catalog}.{schema} TO `{sp_client_id}`",
        f"GRANT SELECT ON SCHEMA {catalog}.{schema} TO `{sp_client_id}`",
        # Volume READ so the app can serve raw PDF files via /api/invoice/{id}/pdf
        f"GRANT READ VOLUME ON VOLUME {catalog}.{schema}.raw_invoices TO `{sp_client_id}`",
    ]
    for stmt in grants:
        state = sql(stmt)
        print(f"  {'✓' if state == 'SUCCEEDED' else '⚠'} {state}: {stmt[:70]}")


def _cli_flags(target: str, profile: str | None) -> list[str]:
    """Return common target + profile flags for CLI commands."""
    flags = ["-t", target]
    if profile:
        flags += ["--profile", profile]
    return flags


def _redeploy_app(host: str, token: str, target: str, profile: str | None) -> None:
    """
    Force the running app to restart with the latest uploaded source code.

    `databricks bundle deploy` uploads files but does NOT restart the running
    app process. An explicit `apps deploy` call is required to create a new
    snapshot deployment, which triggers a process restart.
    """
    app_info = _api("GET", "/api/2.0/apps/fna-control-tower", host=host, token=token)
    source_path = ""
    if isinstance(app_info, dict):
        source_path = app_info.get("default_source_code_path", "")

    if not source_path:
        print("  ⚠ Could not determine app source path — skipping app redeploy")
        return

    cmd = ["databricks", "apps", "deploy", "fna-control-tower",
           "--source-code-path", source_path] + _cli_flags(target, profile)
    # apps deploy doesn't take -t; remove it
    cmd = [c for c in cmd if c not in ("-t", target)]
    if profile:
        cmd += ["--profile", profile]
    # Rebuild cleanly
    cmd = (["databricks", "apps", "deploy", "fna-control-tower",
            "--source-code-path", source_path]
           + (["--profile", profile] if profile else []))
    run(cmd)
    print("  ✓ App restarted with updated source code")


def phase1_deploy(target: str, profile: str | None = None) -> None:
    section(f"Phase 1 — Bundle Deploy  [target: {target}]")
    print("  Creates: warehouse, Lakebase instance, DLT pipeline, ETL job, App")
    run(["databricks", "bundle", "deploy"] + _cli_flags(target, profile))
    print("\n  ✓ Bundle deployed")

    host, token = _get_host_and_token(profile)
    if not host or not token:
        print("  ⚠ Could not get credentials — skipping UC grants and app redeploy")
        return

    # Grant the app's service principal access to the UC catalog/schema
    section("Phase 1b — Grant Unity Catalog Permissions to App")
    app_info = _api("GET", "/api/2.0/apps/fna-control-tower", host=host, token=token)
    sp_client_id = ""
    if isinstance(app_info, dict):
        sp_client_id = app_info.get("service_principal_client_id", "")
    if sp_client_id:
        print(f"  App service principal: {sp_client_id}")
    _grant_catalog_permissions(host, token, "fna_control_tower", "finance_and_accounting",
                               sp_client_id)

    # Force app restart so the new source code and resource bindings take effect
    section("Phase 1c — Restart App")
    _redeploy_app(host, token, target, profile)


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2: Run ETL workflow
# ─────────────────────────────────────────────────────────────────────────────

def phase2_etl(target: str, profile: str | None = None) -> None:
    section("Phase 2 — Run ETL Workflow")
    print("  Tasks: data gen → DLT (bronze→silver + PDF ai_parse_document) → gold (P2P/O2C/R2R) → KPI view")
    print("\n  This takes 20-40 min. Streaming logs below...\n")
    run(["databricks", "bundle", "run", "fna_etl_workflow"] + _cli_flags(target, profile))
    print("\n  ✓ ETL workflow complete")


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3: Create MAS supervisor agent via REST API
# ─────────────────────────────────────────────────────────────────────────────

def phase3_create_supervisor(
    target: str,
    profile: str | None,
    genie_space_id: str,
) -> str:
    """
    Creates a Databricks Supervisor Agent via POST /api/2.1/supervisor-agents.

    Returns the endpoint name (e.g. 'mas-<uuid>-endpoint') or '' on failure.

    Note on Genie Space:
      Genie Spaces cannot be created programmatically from scratch — the API
      requires a serialized_space from an existing space. To add Genie:
        1. Create a Genie Space in the Databricks UI (AI/BI → Genie → New Space)
           Add the tables: gold_fact_invoices, gold_fact_gl, gold_fact_ar_aging,
                           gold_dim_vendor, gold_dim_customer, gold_finance_kpis
        2. Pass --genie-space-id <space_id> to this script
    """
    section("Phase 3 — Create MAS Supervisor Agent")

    host, token = _get_host_and_token(profile)
    if not host or not token:
        print("  ✗ Could not get workspace credentials — skipping supervisor agent creation")
        return ""

    # Check if a supervisor agent already exists with our display name
    existing = _api("GET", "/api/2.1/supervisor-agents", host=host, token=token)
    existing_agents = existing.get("supervisor_agents", []) if isinstance(existing, dict) else []
    existing_endpoint = ""
    for agent in existing_agents:
        if agent.get("display_name") == "FnA Control Tower Supervisor":
            existing_endpoint = agent.get("endpoint_name", "")
            agent_id = agent.get("supervisor_agent_id", "")
            print(f"  Found existing supervisor agent: {agent_id}")
            print(f"  Endpoint: {existing_endpoint}")
            if genie_space_id and not agent.get("genie_space_ids"):
                print(f"  ℹ  Genie Space provided but agent has no spaces linked.")
                print(f"     Delete and recreate via: python3 scripts/setup.py {target} --genie-space-id {genie_space_id} --skip-deploy --skip-etl")
            return existing_endpoint

    # Create new supervisor agent
    print("  Creating supervisor agent via POST /api/2.1/supervisor-agents...")
    body: dict = {
        "display_name": "FnA Control Tower Supervisor",
        "description": (
            "Multi-agent supervisor for Finance & Accounting analytics. "
            "Covers Procure-to-Pay (P2P), Order-to-Cash (O2C), and Record-to-Report (R2R) workflows."
        ),
    }
    if genie_space_id:
        body["genie_space_ids"] = [genie_space_id]
        print(f"  Linking Genie Space: {genie_space_id}")

    result = _api("POST", "/api/2.1/supervisor-agents", body=body, host=host, token=token, timeout=60)

    if isinstance(result, dict) and result.get("endpoint_name"):
        endpoint_name = result["endpoint_name"]
        agent_id = result["supervisor_agent_id"]
        print(f"  ✓ Supervisor agent created: {agent_id}")
        print(f"  ✓ Endpoint name: {endpoint_name}")
        print("  ℹ  Endpoint provisioning may take 2-5 minutes...")
        return endpoint_name
    else:
        error_msg = result.get("message", str(result)) if isinstance(result, dict) else str(result)
        print(f"  ✗ Failed to create supervisor agent: {error_msg[:200]}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: Final bundle deploy with runtime variables
# ─────────────────────────────────────────────────────────────────────────────

def _update_app_yaml(mas_endpoint_name: str, genie_space_id: str) -> bool:
    """
    Update app/app.yaml env vars directly.

    The Databricks Apps bundle `config.env` mechanism does not inject env vars
    into the running container (the vars are stored in bundle state but do not
    reach the app process). Writing them directly into app.yaml is the reliable
    approach — the values are part of the uploaded source snapshot.

    Returns True if app.yaml was modified.
    """
    import re as _re

    app_yaml_path = ROOT / "app" / "app.yaml"
    content = app_yaml_path.read_text()
    original = content

    def set_env(name: str, value: str, text: str) -> str:
        # Match "  - name: NAME\n    value: ..." and replace value
        pattern = rf'(  - name: {_re.escape(name)}\n    value: ")[^"]*(")'
        return _re.sub(pattern, rf'\g<1>{value}\g<2>', text)

    def set_resource_name(res_name: str, value: str, text: str) -> str:
        # Match "  - name: <res_name>\n    serving_endpoint:\n      name: ..." and replace
        pattern = rf'(  - name: {_re.escape(res_name)}\n    serving_endpoint:\n      name: ")[^"]*(")'
        return _re.sub(pattern, rf'\g<1>{value}\g<2>', text)

    if mas_endpoint_name:
        content = set_env("SERVING_ENDPOINT_NAME", mas_endpoint_name, content)
        content = set_resource_name("mas-supervisor", mas_endpoint_name, content)

    if genie_space_id:
        if "GENIE_SPACE_ID" in content:
            content = set_env("GENIE_SPACE_ID", genie_space_id, content)
        else:
            # Insert GENIE_SPACE_ID after LAKEBASE_INSTANCE_NAME
            content = content.replace(
                '  - name: LAKEBASE_INSTANCE_NAME',
                f'  - name: GENIE_SPACE_ID\n    value: "{genie_space_id}"\n  - name: LAKEBASE_INSTANCE_NAME'
            )

    if content != original:
        app_yaml_path.write_text(content)
        return True
    return False


def phase4_finalize(target: str, mas_endpoint_name: str, genie_space_id: str,
                    profile: str | None = None) -> None:
    section("Phase 4 — Wire Runtime Variables into App")

    # Update app.yaml directly (config.env injection doesn't reach the container)
    changed = _update_app_yaml(mas_endpoint_name, genie_space_id)

    if mas_endpoint_name:
        print(f"  serving_endpoint_name = {mas_endpoint_name}")
    else:
        print("  ⚠ MAS endpoint not available — app will use current app.yaml endpoint")

    if genie_space_id:
        print(f"  genie_space_id        = {genie_space_id}")

    # Always redeploy to upload updated app.yaml and apply any var changes
    deploy_cmd = ["databricks", "bundle", "deploy"] + _cli_flags(target, profile)
    if mas_endpoint_name:
        deploy_cmd.append(f"--var=serving_endpoint_name={mas_endpoint_name}")
    if genie_space_id:
        deploy_cmd.append(f"--var=genie_space_id={genie_space_id}")

    run(deploy_cmd)

    # Force app restart so updated app.yaml takes effect immediately
    host, token = _get_host_and_token(profile)
    if host and token:
        _redeploy_app(host, token, target, profile)

    print("\n  ✓ App config updated and restarted")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="FnA Control Tower demo setup")
    parser.add_argument("target", nargs="?", default="dev",
                        help="Bundle target (default: dev)")
    parser.add_argument("--profile", default=None,
                        help="Databricks CLI profile to use for REST API calls")
    parser.add_argument("--skip-deploy", action="store_true",
                        help="Skip Phase 1 (bundle deploy)")
    parser.add_argument("--skip-etl", action="store_true",
                        help="Skip Phase 2 (ETL workflow run)")
    parser.add_argument("--extract-only", action="store_true",
                        help="Only run Phase 3+4 (re-create supervisor and wire variables)")
    parser.add_argument("--genie-space-id", default="",
                        help=(
                            "Genie Space ID to link to the supervisor agent. "
                            "Create manually in the Databricks UI (AI/BI → Genie → New Space), "
                            "then pass the ID here."
                        ))
    args = parser.parse_args()

    target = args.target
    genie_space_id = args.genie_space_id.strip()

    print(f"\n{'█'*60}")
    print(f"  FnA Control Tower — Full Demo Setup")
    print(f"  Target       : {target}")
    if genie_space_id:
        print(f"  Genie Space  : {genie_space_id}")
    print(f"{'█'*60}")

    if not args.skip_deploy and not args.extract_only:
        phase1_deploy(target, args.profile)

    if not args.skip_etl and not args.extract_only:
        phase2_etl(target, args.profile)

    mas_endpoint_name = phase3_create_supervisor(target, args.profile, genie_space_id)
    phase4_finalize(target, mas_endpoint_name, genie_space_id, args.profile)

    print(f"\n{'█'*60}")
    print(f"  ✓ FnA Control Tower demo setup complete!")
    if not genie_space_id:
        print()
        print("  To add Genie Space integration later:")
        print("    1. Create a Genie Space in Databricks UI (AI/BI → Genie → New Space)")
        print(f"       Add tables from {target} catalog: gold_fact_invoices, gold_fact_gl,")
        print("       gold_fact_ar_aging, gold_dim_vendor, gold_dim_customer, gold_finance_kpis")
        print("    2. Copy the space ID from the URL")
        print(f"    3. Run: python3 scripts/setup.py {target} --genie-space-id <space_id> --skip-deploy --skip-etl")
    print(f"{'█'*60}\n")


if __name__ == "__main__":
    main()
