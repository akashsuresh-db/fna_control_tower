"""AP Exception Escalation via native Databricks SQL Alerts (V2).

Uses the Databricks SDK AlertsV2 API — no SMTP, no custom email.
Databricks sends the email natively when the alert condition is met.

Flow per Escalate click:
  1. Build SQL WHERE clause from selected exception_types
  2. Create AlertV2 (first call) or update its query_text + unpause (subsequent calls)
     - Alert has email subscription via notification destination
     - Schedule: every minute, UNPAUSED → fires within 60s
  3. Return immediately; alert fires within ~60 seconds
  4. Background task pauses the schedule after 90s to avoid repeat emails

State (alert_id) persisted in /tmp/fna_alert_state.json (recreated if app restarts).

ESCALATION_RECIPIENT env var sets the email address — not collected from UI.
"""
import asyncio
import json
import os
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import sql as dbsql

from backend.config import CATALOG, SCHEMA

# ── Config ────────────────────────────────────────────────────────────────────

ALERT_NAME   = "AP Exception Escalation — Finance Control Tower"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "4b9b953939869799")
RECIPIENT    = os.environ.get("ESCALATION_RECIPIENT", "akash.s@databricks.com")

_STATE_FILE  = Path("/tmp/fna_alert_state.json")

# ── Exception type definitions (mirrors streams.py exactly) ──────────────────

EXCEPTION_TYPES = {
    "AMOUNT_MISMATCH": {
        "label":  "Amount Mismatch",
        "filter": "match_status = 'AMOUNT_MISMATCH'",
    },
    "NO_PO_REFERENCE": {
        "label":  "No PO Reference",
        "filter": "match_status = 'NO_PO_REFERENCE'",
    },
    "CRITICAL_OVERDUE": {
        "label":  "Critical Overdue (>60 days)",
        "filter": "is_overdue = true AND CAST(aging_days AS INT) > 60",
    },
    "MISSING_GSTIN": {
        "label":  "Missing GSTIN",
        "filter": "gstin_vendor IS NULL",
    },
}


# ── SQL builder ───────────────────────────────────────────────────────────────

def build_alert_sql(exception_types: list[str]) -> str:
    """
    Build alert SQL for the selected exception types.
    Returns one summary row per type — clear in the Databricks alert email.

      exception_type      | severity | exception_count | total_amount_inr
      Amount Mismatch     | HIGH     | 5               | 12345678
      Critical Overdue    | CRITICAL | 3               | 9876543
    """
    keys = [k for k in exception_types if k in EXCEPTION_TYPES] or list(EXCEPTION_TYPES)

    severity_map = {
        "AMOUNT_MISMATCH":  "HIGH",
        "NO_PO_REFERENCE":  "HIGH",
        "CRITICAL_OVERDUE": "CRITICAL",
        "MISSING_GSTIN":    "MEDIUM",
    }

    type_case = "\n            ".join(
        f"WHEN {EXCEPTION_TYPES[k]['filter']} THEN '{EXCEPTION_TYPES[k]['label']}'"
        for k in keys
    )
    sev_case = "\n            ".join(
        f"WHEN {EXCEPTION_TYPES[k]['filter']} THEN '{severity_map[k]}'"
        for k in keys
    )
    where = " OR ".join(f"({EXCEPTION_TYPES[k]['filter']})" for k in keys)

    return f"""SELECT
    exception_type,
    severity,
    COUNT(*)                           AS exception_count,
    CAST(SUM(invoice_total_inr) AS BIGINT) AS total_amount_inr
FROM (
    SELECT
        invoice_total_inr,
        CASE {type_case}
        END AS exception_type,
        CASE {sev_case}
        END AS severity
    FROM `{CATALOG}`.`{SCHEMA}`.gold_fact_invoices
    WHERE {where}
) t
GROUP BY exception_type, severity
ORDER BY
    CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
    exception_count DESC"""


# ── State helpers ─────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        return json.loads(_STATE_FILE.read_text())
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    _STATE_FILE.write_text(json.dumps(state))


# ── Notification destination ──────────────────────────────────────────────────

def _get_or_create_destination(w: WorkspaceClient, email: str) -> str:
    """Find or create an email notification destination for the recipient."""
    dests = list(w.notification_destinations.list())

    # Look for an existing email destination for this address
    for d in dests:
        if "EMAIL" in str(d.destination_type):
            full = w.notification_destinations.get(d.id)
            addrs = []
            if full.config and full.config.email:
                addrs = full.config.email.addresses or []
            if email in addrs:
                return d.id

    # Create one
    from databricks.sdk.service.settings import (
        CreateNotificationDestinationRequest,
        Config as NdConfig,
        EmailConfig,
    )
    nd = w.notification_destinations.create(CreateNotificationDestinationRequest(
        display_name=f"Finance Escalation — {email}",
        config=NdConfig(email=EmailConfig(addresses=[email])),
    ))
    return nd.id


# ── Alert lifecycle ───────────────────────────────────────────────────────────

def _alert_spec(query_text: str, dest_id: str, paused: bool) -> dbsql.AlertV2:
    """Build the AlertV2 spec."""
    pause_status = (
        dbsql.SchedulePauseStatus.PAUSED
        if paused
        else dbsql.SchedulePauseStatus.UNPAUSED
    )
    return dbsql.AlertV2(
        display_name=ALERT_NAME,
        query_text=query_text,
        warehouse_id=WAREHOUSE_ID,
        evaluation=dbsql.AlertV2Evaluation(
            source=dbsql.AlertV2OperandColumn(name="exception_count"),
            comparison_operator=dbsql.ComparisonOperator.GREATER_THAN,
            threshold=dbsql.AlertV2Operand(
                value=dbsql.AlertV2OperandValue(double_value=0)
            ),
            notification=dbsql.AlertV2Notification(
                subscriptions=[dbsql.AlertV2Subscription(destination_id=dest_id)],
                retrigger_seconds=0,
            ),
        ),
        schedule=dbsql.CronSchedule(
            quartz_cron_schedule="0 * * * * ?",  # every minute
            timezone_id="Asia/Kolkata",
            pause_status=pause_status,
        ),
    )


def create_or_update_alert(exception_types: list[str]) -> dict:
    """
    Create or update the SQL Alert with the selected exception_types SQL.
    Unpauses the schedule so it fires within ~60 seconds.
    Returns state dict with alert_id.
    """
    w = WorkspaceClient()
    state = _load_state()

    sql = build_alert_sql(exception_types)
    dest_id = _get_or_create_destination(w, RECIPIENT)

    # Check if existing alert is still alive
    alert_id = state.get("alert_id")
    if alert_id:
        try:
            w.alerts_v2.get_alert(id=alert_id)
        except Exception:
            alert_id = None  # trashed or missing — recreate

    if not alert_id:
        a = w.alerts_v2.create_alert(alert=_alert_spec(sql, dest_id, paused=False))
        alert_id = a.id
        print(f"[escalate] Created alert {alert_id}")
    else:
        w.alerts_v2.update_alert(
            id=alert_id,
            alert=_alert_spec(sql, dest_id, paused=False),
            update_mask="query_text,evaluation,schedule",
        )
        print(f"[escalate] Updated alert {alert_id}, unpaused")

    state["alert_id"] = alert_id
    state["dest_id"] = dest_id
    _save_state(state)
    return state


def pause_alert(alert_id: str, dest_id: str, sql: str) -> None:
    """Pause the alert after it has fired (called from background task)."""
    try:
        w = WorkspaceClient()
        w.alerts_v2.update_alert(
            id=alert_id,
            alert=_alert_spec(sql, dest_id, paused=True),
            update_mask="schedule",
        )
        print(f"[escalate] Paused alert {alert_id}")
    except Exception as e:
        print(f"[escalate] Could not pause alert: {e}")


# ── Public entry point ────────────────────────────────────────────────────────

def run_escalation(exception_types: list[str]) -> dict:
    """
    Configure and arm the SQL Alert for the selected exception types.
    The alert evaluates within ~60 seconds and Databricks sends the email.

    Returns {"status", "alert_id", "recipient", "exception_types"}
    """
    state = create_or_update_alert(exception_types)
    return {
        "status":          "scheduled",
        "alert_id":        state["alert_id"],
        "recipient":       RECIPIENT,
        "exception_types": exception_types,
        "message":         f"SQL Alert armed — email to {RECIPIENT} within ~60 seconds.",
    }
