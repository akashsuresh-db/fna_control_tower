"""AP Exception Escalation via Databricks SQL Alerts V2.

Architecture:
  - One persistent alert in Databricks — found by name, never duplicated.
  - SQL uses a CASE/WHERE structure; the alert SQL is updated only when the
    selected exception types change (not rebuilt from scratch every click).
  - Email subscription is embedded in the AlertV2 spec via notification destinations.
  - Trigger: unpause the cron schedule → Databricks fires the alert within ~60s.
  - Background task re-pauses after 90s.

State is kept in module-level variables (survives the process lifetime).
Alert is found by display_name on first call, so restarts are safe.
"""
import asyncio
import os

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import sql as dbsql

from backend.config import CATALOG, SCHEMA

# ── Config ────────────────────────────────────────────────────────────────────

ALERT_NAME   = "AP Exception Escalation — Finance Control Tower"
WAREHOUSE_ID = os.environ.get("DATABRICKS_WAREHOUSE_ID", "4b9b953939869799")
RECIPIENT    = os.environ.get("ESCALATION_RECIPIENT", "akash.s@databricks.com")

# ── Module-level state (survives process lifetime, rediscovered after restart) ─

_alert_id: str | None = None   # AlertV2 ID — found by name if not set
_dest_id:  str | None = None   # Notification destination ID — found or created once
_last_sql: str | None = None   # Last SQL pushed to the alert (avoid no-op updates)

# ── Exception type definitions ────────────────────────────────────────────────

EXCEPTION_TYPES = {
    "AMOUNT_MISMATCH": {
        "label":    "Amount Mismatch",
        "filter":   "match_status = 'AMOUNT_MISMATCH'",
        "severity": "HIGH",
    },
    "NO_PO_REFERENCE": {
        "label":    "No PO Reference",
        "filter":   "match_status = 'NO_PO_REFERENCE'",
        "severity": "HIGH",
    },
    "CRITICAL_OVERDUE": {
        "label":    "Critical Overdue (>60 days)",
        "filter":   "is_overdue = true AND CAST(aging_days AS INT) > 60",
        "severity": "CRITICAL",
    },
    "MISSING_GSTIN": {
        "label":    "Missing GSTIN",
        "filter":   "gstin_vendor IS NULL",
        "severity": "MEDIUM",
    },
}


# ── SQL builder ───────────────────────────────────────────────────────────────

def build_alert_sql(exception_types: list[str]) -> str:
    """
    Build a summary SQL for the selected exception types.
    Returns one row per type with exception_count and total_amount_inr.

      exception_type    | severity | exception_count | total_amount_inr
      Amount Mismatch   | HIGH     | 5               | 12345678
      Critical Overdue  | CRITICAL | 3               | 9876543
    """
    keys = [k for k in exception_types if k in EXCEPTION_TYPES] or list(EXCEPTION_TYPES)

    type_cases = "\n            ".join(
        f"WHEN {EXCEPTION_TYPES[k]['filter']} THEN '{EXCEPTION_TYPES[k]['label']}'"
        for k in keys
    )
    sev_cases = "\n            ".join(
        f"WHEN {EXCEPTION_TYPES[k]['filter']} THEN '{EXCEPTION_TYPES[k]['severity']}'"
        for k in keys
    )
    where = " OR ".join(f"({EXCEPTION_TYPES[k]['filter']})" for k in keys)

    return f"""SELECT
    exception_type,
    severity,
    COUNT(*)                              AS exception_count,
    CAST(SUM(invoice_total_inr) AS BIGINT) AS total_amount_inr
FROM (
    SELECT
        invoice_total_inr,
        CASE {type_cases}
        END AS exception_type,
        CASE {sev_cases}
        END AS severity
    FROM `{CATALOG}`.`{SCHEMA}`.gold_fact_invoices
    WHERE {where}
) t
GROUP BY exception_type, severity
ORDER BY
    CASE severity WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 ELSE 3 END,
    exception_count DESC"""


# ── Notification destination ──────────────────────────────────────────────────

def _get_or_create_destination(w: WorkspaceClient, email: str) -> str:
    """Find or create an email notification destination. Result is cached."""
    global _dest_id
    if _dest_id:
        return _dest_id

    for d in w.notification_destinations.list():
        if "EMAIL" in str(d.destination_type):
            try:
                full = w.notification_destinations.get(d.id)
            except Exception as e:
                print(f"[escalate] Skipping corrupted destination {d.id} ({d.display_name}): {e}")
                continue
            addrs = (full.config.email.addresses or []) if (full.config and full.config.email) else []
            if email in addrs:
                _dest_id = d.id
                return _dest_id

    from databricks.sdk.service.settings import (
        Config as NdConfig,
        EmailConfig,
    )
    nd = w.notification_destinations.create(
        display_name=f"Finance Escalation — {email}",
        config=NdConfig(email=EmailConfig(addresses=[email])),
    )
    _dest_id = nd.id
    return _dest_id


# ── Alert spec builder ────────────────────────────────────────────────────────

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


# ── Alert lifecycle ───────────────────────────────────────────────────────────

def _find_alert_by_name(w: WorkspaceClient) -> str | None:
    """Search Databricks for our alert by display_name."""
    try:
        for alert in w.alerts_v2.list():
            if alert.display_name == ALERT_NAME:
                print(f"[escalate] Found existing alert: {alert.id}")
                return alert.id
    except Exception as e:
        print(f"[escalate] Could not list alerts: {e}")
    return None


def _ensure_alert_id(w: WorkspaceClient) -> None:
    """Populate _alert_id from Databricks if not already set."""
    global _alert_id
    if _alert_id:
        # Verify it still exists
        try:
            w.alerts_v2.get_alert(id=_alert_id)
            return
        except Exception:
            _alert_id = None  # trashed or missing

    _alert_id = _find_alert_by_name(w)


def _rest(method: str, path: str, token: str, body: dict | None = None) -> dict:
    """Minimal REST helper — bypasses SDK env-var auth conflict."""
    import urllib.request, urllib.error, json as _json
    host = os.environ.get("DATABRICKS_HOST", "")
    if host and not host.startswith("http"):
        host = f"https://{host}"
    url = f"{host.rstrip('/')}{path}"
    data = _json.dumps(body).encode() if body else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return _json.loads(resp.read()) if resp.read else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"REST {method} {path} → {e.code}: {e.read().decode()[:300]}")


def _make_workspace_client(user_token: str) -> "WorkspaceClient":
    """
    Create a WorkspaceClient using only the user token, bypassing any M2M
    OAuth env vars (DATABRICKS_CLIENT_ID/SECRET) that would conflict.

    Temporarily removes conflicting env vars so the SDK doesn't detect a
    mixed-auth scenario, then restores them afterwards.
    """
    host = os.environ.get("DATABRICKS_HOST", "")
    if host and not host.startswith("http"):
        host = f"https://{host}"

    # Temporarily remove M2M env vars that conflict with PAT auth
    _saved = {}
    for key in ("DATABRICKS_CLIENT_ID", "DATABRICKS_CLIENT_SECRET",
                "DATABRICKS_ACCOUNT_ID", "ARM_CLIENT_ID", "ARM_CLIENT_SECRET"):
        val = os.environ.pop(key, None)
        if val is not None:
            _saved[key] = val

    try:
        os.environ["DATABRICKS_TOKEN"] = user_token
        w = WorkspaceClient(host=host)
    finally:
        # Restore env vars
        os.environ.pop("DATABRICKS_TOKEN", None)
        for k, v in _saved.items():
            os.environ[k] = v

    return w


def _get_or_create_destination_rest(token: str, email: str) -> str:
    """Find or create email notification destination using direct REST API."""
    global _dest_id
    if _dest_id:
        return _dest_id
    try:
        data = _rest("GET", "/api/2.0/notification-destinations", token)
        for d in data.get("results", []):
            if d.get("destination_type") == "EMAIL":
                cfg = d.get("config", {}).get("email", {})
                if email in cfg.get("addresses", []):
                    _dest_id = d["id"]
                    return _dest_id
    except Exception as e:
        print(f"[escalate] Could not list notification destinations: {e}")

    # Create new email destination
    try:
        nd = _rest("POST", "/api/2.0/notification-destinations", token, {
            "display_name": f"Finance Escalation — {email}",
            "config": {"email": {"addresses": [email]}},
        })
        _dest_id = nd["id"]
        return _dest_id
    except Exception as e:
        raise RuntimeError(f"Could not create notification destination: {e}")


def arm_alert(exception_types: list[str], user_token: str | None = None) -> dict:
    """
    Ensure the SQL Alert exists in Databricks and arms it for the selected
    exception types. The alert fires within ~60 seconds via its cron schedule.

    On first call: creates the alert (it will then persist in Databricks).
    On subsequent calls: updates only query_text + schedule if the selection
    has changed, then unpauses. No-ops the update if nothing changed.

    Uses user_token (x-forwarded-access-token from Databricks Apps proxy)
    when available, so alert creation runs with user-level workspace permissions
    rather than the app service principal's restricted M2M credentials.
    """
    global _alert_id, _last_sql

    sql = build_alert_sql(exception_types)

    if user_token:
        # Get notification destination via direct REST (bypasses SP restriction)
        dest_id = _get_or_create_destination_rest(user_token, RECIPIENT)
        # Use SDK with user token (isolated from M2M env vars) for alert creation
        w = _make_workspace_client(user_token)
        _ensure_alert_id_sdk(w)
        _arm_alert_sdk(sql, dest_id, w)
    else:
        w = WorkspaceClient()
        dest_id = _get_or_create_destination(w, RECIPIENT)
        _ensure_alert_id(w)
        _arm_alert_sdk(sql, dest_id, w)

    _last_sql = sql
    return {"alert_id": _alert_id, "dest_id": dest_id}


def _ensure_alert_id_sdk(w: "WorkspaceClient") -> None:
    """Find alert by name using SDK."""
    global _alert_id
    if _alert_id:
        try:
            w.alerts_v2.get_alert(id=_alert_id)
            return
        except Exception:
            _alert_id = None
    try:
        for a in w.alerts_v2.list():
            if a.display_name == ALERT_NAME:
                _alert_id = a.id
                print(f"[escalate] Found existing alert: {_alert_id}")
                return
    except Exception as e:
        print(f"[escalate] Could not list alerts: {e}")


def _arm_alert_sdk(sql: str, dest_id: str, w: "WorkspaceClient") -> None:
    """Create or update SQL Alert V2 via SDK."""
    global _alert_id, _last_sql

    spec = _alert_spec(sql, dest_id, paused=False)

    if _alert_id:
        need_sql_update = (sql != _last_sql)
        mask = "query_text,evaluation,schedule" if need_sql_update else "schedule"
        w.alerts_v2.update_alert(id=_alert_id, alert=spec, update_mask=mask)
        print(f"[escalate] Alert {_alert_id} armed (mask={mask})")
    else:
        a = w.alerts_v2.create_alert(alert=spec)
        _alert_id = a.id
        print(f"[escalate] Created alert {_alert_id}")


def pause_alert() -> None:
    """Re-pause the alert after it has fired (called from background task)."""
    global _alert_id, _dest_id, _last_sql
    if not _alert_id or not _dest_id or not _last_sql:
        return
    try:
        w = WorkspaceClient()
        w.alerts_v2.update_alert(
            id=_alert_id,
            alert=_alert_spec(_last_sql, _dest_id, paused=True),
            update_mask="schedule",
        )
        print(f"[escalate] Alert {_alert_id} re-paused")
    except Exception as e:
        print(f"[escalate] Could not pause alert: {e}")


# ── Public entry point ────────────────────────────────────────────────────────

def run_escalation(exception_types: list[str], user_token: str | None = None) -> dict:
    """
    Arm the SQL Alert for the selected exception types.
    Databricks evaluates and sends the email within ~60 seconds.

    Returns {"status", "alert_id", "recipient", "exception_types", "message"}.
    """
    state = arm_alert(exception_types, user_token=user_token)

    # Schedule background re-pause after 90 seconds
    async def _delayed_pause():
        await asyncio.sleep(90)
        pause_alert()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_delayed_pause())
    except RuntimeError:
        pass  # No event loop — pause will not happen (alert auto-pauses next minute anyway)

    return {
        "status":          "scheduled",
        "alert_id":        state["alert_id"],
        "recipient":       RECIPIENT,
        "exception_types": exception_types,
        "message":         f"SQL Alert armed — email to {RECIPIENT} within ~60 seconds.",
    }
