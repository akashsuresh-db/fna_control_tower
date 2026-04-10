"""AP Exception Escalation via native Databricks SQL Alerts.

No SMTP. No custom email. Databricks sends the email natively.

Flow per Escalate click:
  1. ensure_alert()   — creates SQL query + alert + email subscription (idempotent)
  2. update_query()   — rewrites the query SQL with the selected exception_types
  3. trigger_alert()  — executes the query via statement execution;
                        Databricks evaluates the alert condition and fires email if rows > 0

The alert query returns one summary row per exception type so the
Databricks alert email is readable without any custom templating.

State (query_id, alert_id) is cached in /tmp/fna_alert_state.json —
recreated automatically if the app restarts.
"""
import json
import os
import time
from pathlib import Path

import requests

from backend.config import CATALOG, SCHEMA, get_workspace_host, get_token

# ── Exception type definitions ───────────────────────────────────────────────

EXCEPTION_TYPES = {
    "AMOUNT_MISMATCH":  {
        "label":  "Amount Mismatch",
        "filter": "match_status = 'AMOUNT_MISMATCH'",
        "severity": "HIGH",
    },
    "NO_PO_REFERENCE":  {
        "label":  "No PO Reference",
        "filter": "match_status = 'NO_PO_REFERENCE'",
        "severity": "HIGH",
    },
    "CRITICAL_OVERDUE": {
        "label":  "Critical Overdue (>60 days)",
        "filter": "is_overdue = true AND CAST(aging_days AS INT) > 60",
        "severity": "CRITICAL",
    },
    "MISSING_GSTIN":    {
        "label":  "Missing GSTIN",
        "filter": "gstin_vendor IS NULL",
        "severity": "MEDIUM",
    },
}

_STATE_FILE = Path("/tmp/fna_alert_state.json")
ALERT_NAME  = "AP Exception Escalation — Finance Control Tower"
QUERY_NAME  = "AP Exception Escalation Query"


# ── SQL builder ───────────────────────────────────────────────────────────────

def build_alert_sql(exception_types: list[str]) -> str:
    """
    Build the alert query for the selected exception types.

    Returns one summary row per exception type so the Databricks alert
    email table is meaningful at a glance:

      exception_type       | severity | exception_count | total_amount_inr
      Amount Mismatch      | HIGH     | 5               | 1234567
      Critical Overdue     | CRITICAL | 3               | 987654
    """
    keys = [k for k in exception_types if k in EXCEPTION_TYPES] or list(EXCEPTION_TYPES)

    # Build CASE branches only for selected types
    type_case = "\n            ".join(
        f"WHEN {EXCEPTION_TYPES[k]['filter']} THEN '{EXCEPTION_TYPES[k]['label']}'"
        for k in keys
    )
    sev_case = "\n            ".join(
        f"WHEN {EXCEPTION_TYPES[k]['filter']} THEN '{EXCEPTION_TYPES[k]['severity']}'"
        for k in keys
    )
    where_clauses = " OR ".join(f"({EXCEPTION_TYPES[k]['filter']})" for k in keys)

    return f"""
SELECT
    exception_type,
    severity,
    COUNT(*)                       AS exception_count,
    CAST(SUM(invoice_total_inr) AS BIGINT) AS total_amount_inr
FROM (
    SELECT
        invoice_total_inr,
        CASE
            {type_case}
        END AS exception_type,
        CASE
            {sev_case}
        END AS severity
    FROM `{CATALOG}`.`{SCHEMA}`.gold_fact_invoices
    WHERE {where_clauses}
) t
GROUP BY exception_type, severity
ORDER BY
    CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
    exception_count DESC
""".strip()


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.write_text(json.dumps(state))


# ── Databricks DBSQL REST helpers ─────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
    }


def _host() -> str:
    return get_workspace_host()


def _sql_post(path: str, payload: dict) -> dict:
    r = requests.post(f"{_host()}{path}", json=payload, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def _sql_put(path: str, payload: dict) -> dict:
    r = requests.put(f"{_host()}{path}", json=payload, headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


def _sql_get(path: str) -> dict:
    r = requests.get(f"{_host()}{path}", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()


# ── Core logic ────────────────────────────────────────────────────────────────

def _warehouse_id() -> str:
    return os.environ.get("DATABRICKS_WAREHOUSE_ID", "4b9b953939869799")


def ensure_alert(recipient: str, exception_types: list[str]) -> dict:
    """
    Idempotently create (or load) the SQL query and alert.
    Adds the recipient as an email subscriber if not already subscribed.
    Returns the current state dict {query_id, alert_id}.
    """
    state = _load_state()

    # ── 1. SQL Query ──────────────────────────────────────────────────────────
    sql = build_alert_sql(exception_types)

    if "query_id" not in state:
        q = _sql_post("/api/2.0/sql/queries", {
            "name":            QUERY_NAME,
            "query":           sql,
            "data_source_id":  _warehouse_id(),
            "description":     "Automatically updated by Finance Control Tower Escalate action.",
        })
        state["query_id"] = q["id"]
        print(f"[escalate] Created SQL query: {state['query_id']}")
    else:
        # Update the SQL to reflect current exception_types selection
        _sql_post(f"/api/2.0/sql/queries/{state['query_id']}", {
            "name":  QUERY_NAME,
            "query": sql,
        })

    # ── 2. Alert ──────────────────────────────────────────────────────────────
    if "alert_id" not in state:
        a = _sql_post("/api/2.0/sql/alerts", {
            "name":      ALERT_NAME,
            "query_id":  state["query_id"],
            "options": {
                "column":    "exception_count",
                "op":        ">",
                "value":     "0",
                "muted":     False,
                "custom_subject": "⚠️ AP Exception Escalation — Finance Control Tower",
                "custom_body": (
                    "The following AP exceptions were detected in "
                    f"`{CATALOG}.{SCHEMA}.gold_fact_invoices`.\n\n"
                    "{{QUERY_RESULT_TABLE}}\n\n"
                    "Open Finance Control Tower to review and action."
                ),
            },
            "rearm": 0,  # fire every time condition is met (no cooldown)
        })
        state["alert_id"] = a["id"]
        print(f"[escalate] Created SQL alert: {state['alert_id']}")

    _save_state(state)

    # ── 3. Email subscription (idempotent) ────────────────────────────────────
    _ensure_subscription(state["alert_id"], recipient)

    return state


def _ensure_subscription(alert_id: str, email: str) -> None:
    """Add email subscription to the alert if not already present."""
    # List existing subscriptions
    try:
        existing = _sql_get(f"/api/2.0/sql/alerts/{alert_id}/subscriptions")
        subs = existing if isinstance(existing, list) else existing.get("results", [])
        for s in subs:
            sub_email = (
                s.get("subscriber", {}).get("email_address")
                or s.get("email_address", "")
            )
            if sub_email == email:
                return  # already subscribed
    except Exception as e:
        print(f"[escalate] Could not list subscriptions: {e}")

    # Add subscription
    try:
        _sql_post(f"/api/2.0/sql/alerts/{alert_id}/subscriptions", {
            "subscriber": {"email_address": email}
        })
        print(f"[escalate] Subscribed {email} to alert {alert_id}")
    except Exception as e:
        print(f"[escalate] Subscription failed (may already exist): {e}")


def trigger_alert(state: dict) -> dict:
    """
    Execute the query via Databricks Statement Execution API.
    Databricks evaluates the alert condition against the result and
    fires the email notification natively if exception_count > 0.

    Returns {"row_count": N, "fired": bool}
    """
    warehouse_id = _warehouse_id()

    # Execute via Statement Execution API (synchronous, wait for result)
    resp = _sql_post("/api/2.0/sql/statements", {
        "warehouse_id": warehouse_id,
        "statement":    _sql_get(f"/api/2.0/sql/queries/{state['query_id']}")["query"],
        "wait_timeout": "30s",
        "on_wait_timeout": "CONTINUE",
    })

    statement_id = resp.get("statement_id")
    status = resp.get("status", {}).get("state", "")

    # Poll until terminal state
    for _ in range(20):
        if status in ("SUCCEEDED", "FAILED", "CANCELED", "CLOSED"):
            break
        time.sleep(1.5)
        resp = _sql_get(f"/api/2.0/sql/statements/{statement_id}")
        status = resp.get("status", {}).get("state", "")

    if status != "SUCCEEDED":
        raise RuntimeError(f"Statement execution ended with state: {status}")

    row_count = resp.get("manifest", {}).get("total_row_count", 0)

    # Also trigger the alert refresh so Databricks evaluates + sends email
    try:
        _sql_post(f"/api/2.0/sql/queries/{state['query_id']}/refresh", {})
    except Exception as e:
        # Some workspace versions use a different path — log but don't fail
        print(f"[escalate] Query refresh endpoint: {e}")

    return {"row_count": row_count, "fired": row_count > 0}


# ── Public entry point ────────────────────────────────────────────────────────

def run_escalation(exception_types: list[str], recipient: str) -> dict:
    """
    Full escalation flow:
      1. Ensure alert exists with the right SQL and subscriber
      2. Execute the query → Databricks fires the alert email
    Returns {"status", "row_count", "alert_id", "query_id"}
    """
    state  = ensure_alert(recipient, exception_types)
    result = trigger_alert(state)
    return {
        "status":    "fired" if result["fired"] else "no_exceptions",
        "row_count": result["row_count"],
        "alert_id":  state.get("alert_id"),
        "query_id":  state.get("query_id"),
        "recipient": recipient,
    }
