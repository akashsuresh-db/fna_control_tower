"""LLM-powered top-of-tab summary card.

Each tab (AP / AR / GL) gets a tight summary that highlights:
  - the vendors / customers / accounts to prioritise today
  - the dominant issue patterns
  - the action the user should take next

Strict output contract: ≤4 bullets, each ≤ ~15 words. The card is meant to fit
in a single glance.
"""
from __future__ import annotations

import json
import aiohttp

from backend import db
from backend.config import get_workspace_host, get_token, CATALOG, SCHEMA

LLM_ENDPOINT = "databricks-claude-sonnet-4-6"


# ─── Per-tab signal queries ──────────────────────────────────────────────────
# Each query returns one small JSON-friendly dict that the LLM summarises.

_P2P_SIGNALS_SQL = f"""
WITH inv AS (
  SELECT * FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_invoices`
),
ex AS (
  SELECT exception_type, COUNT(*) AS n
    FROM `{CATALOG}`.`{SCHEMA}`.`silver_invoice_exceptions`
   GROUP BY exception_type
),
top_vendors AS (
  SELECT vendor_name, SUM(invoice_total_inr) AS overdue_value,
         COUNT(*) AS overdue_count
    FROM inv
   WHERE is_overdue = true
   GROUP BY vendor_name
   ORDER BY overdue_value DESC
   LIMIT 3
),
top_amt_mismatch AS (
  SELECT vendor_name, COUNT(*) AS mismatches
    FROM inv WHERE match_status = 'AMOUNT_MISMATCH'
   GROUP BY vendor_name ORDER BY mismatches DESC LIMIT 3
)
SELECT
  (SELECT COUNT(*) FROM inv) AS total_invoices,
  (SELECT COUNT(*) FROM inv WHERE match_status = 'THREE_WAY_MATCHED') AS touchless,
  (SELECT COUNT(*) FROM inv WHERE is_overdue) AS overdue_count,
  (SELECT ROUND(SUM(invoice_total_inr)/1e7, 2) FROM inv WHERE is_overdue) AS overdue_value_cr,
  (SELECT to_json(collect_list(named_struct('type', exception_type, 'count', n))) FROM ex) AS exceptions_json,
  (SELECT to_json(collect_list(named_struct(
            'vendor', vendor_name,
            'overdue_count', overdue_count,
            'overdue_value_cr', ROUND(overdue_value/1e7, 2)
          ))) FROM top_vendors) AS top_vendors_json,
  (SELECT to_json(collect_list(named_struct(
            'vendor', vendor_name, 'mismatches', mismatches
          ))) FROM top_amt_mismatch) AS top_mismatch_json
"""

_O2C_SIGNALS_SQL = f"""
WITH col AS (
  SELECT * FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_collections`
),
overdue AS (
  SELECT * FROM col WHERE balance_outstanding > 0 AND days_outstanding > 0
),
top_customers AS (
  SELECT customer_name,
         SUM(balance_outstanding) AS outstanding,
         COUNT(*) AS overdue_invoices,
         MAX(days_outstanding) AS max_days_outstanding
    FROM overdue
   GROUP BY customer_name
   ORDER BY outstanding DESC
   LIMIT 3
),
aging AS (
  SELECT aging_bucket, ROUND(SUM(balance_outstanding)/1e7, 2) AS bucket_cr
    FROM col WHERE balance_outstanding > 0 GROUP BY aging_bucket
)
SELECT
  (SELECT COUNT(DISTINCT customer_id) FROM overdue) AS overdue_customers,
  (SELECT ROUND(SUM(balance_outstanding)/1e7, 2) FROM col WHERE balance_outstanding > 0) AS total_outstanding_cr,
  (SELECT ROUND(AVG(days_outstanding), 1) FROM overdue) AS avg_days_outstanding,
  (SELECT to_json(collect_list(named_struct(
            'customer', customer_name,
            'outstanding_cr', ROUND(outstanding/1e7, 2),
            'overdue_invoices', overdue_invoices,
            'max_days_outstanding', max_days_outstanding
          ))) FROM top_customers) AS top_customers_json,
  (SELECT to_json(collect_list(named_struct(
            'bucket', aging_bucket, 'value_cr', bucket_cr
          ))) FROM aging) AS aging_json
"""

_R2R_SIGNALS_SQL = f"""
WITH gl AS (SELECT * FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_gl`),
tb AS (SELECT * FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_trial_balance`),
je_summary AS (
  SELECT je_id,
         SUM(debit_inr) AS jed,
         SUM(credit_inr) AS jec
    FROM gl GROUP BY je_id
),
unbalanced AS (
  SELECT je_id, ABS(jed - jec) AS diff
    FROM je_summary
   WHERE ABS(jed - jec) > 0.01
   ORDER BY diff DESC LIMIT 3
),
top_accounts AS (
  SELECT account_name, ROUND(SUM(closing_balance_inr)/1e7, 2) AS balance_cr
    FROM tb
   WHERE account_type = 'Expense'
   GROUP BY account_name
   ORDER BY ABS(SUM(closing_balance_inr)) DESC
   LIMIT 3
)
SELECT
  (SELECT COUNT(DISTINCT je_id) FROM gl) AS total_je,
  (SELECT COUNT(*) FROM unbalanced) AS unbalanced_count,
  (SELECT ROUND(SUM(diff)/1e5, 2) FROM unbalanced) AS unbalanced_value_l,
  (SELECT to_json(collect_list(named_struct(
            'je_id', je_id, 'difference', diff
          ))) FROM unbalanced) AS top_unbalanced_json,
  (SELECT ROUND(SUM(CASE WHEN account_type = 'Asset'     THEN closing_balance_inr END)/1e7, 2) FROM tb) AS total_assets_cr,
  (SELECT ROUND(SUM(CASE WHEN account_type = 'Liability' THEN closing_balance_inr END)/1e7, 2) FROM tb) AS total_liabilities_cr,
  (SELECT to_json(collect_list(named_struct(
            'account', account_name, 'balance_cr', balance_cr
          ))) FROM top_accounts) AS top_expenses_json
"""

_SQL_BY_TAB = {
    "P2P": _P2P_SIGNALS_SQL,
    "O2C": _O2C_SIGNALS_SQL,
    "R2R": _R2R_SIGNALS_SQL,
}


def _fetch_signals(tab: str) -> dict:
    """Run the signal SQL for the tab; return a dict of named columns."""
    sql_text = _SQL_BY_TAB.get(tab.upper())
    if not sql_text:
        return {}
    rows = db.query(sql_text)
    if not rows:
        return {}
    row = rows[0]
    out = {}
    for k, v in row.items():
        # parse JSON columns
        if isinstance(v, str) and (v.startswith("[") or v.startswith("{")):
            try:
                v = json.loads(v)
            except Exception:
                pass
        out[k] = v
    return out


# ─── LLM call ────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are a senior finance operations analyst writing a glance-card for a CFO dashboard.

Hard formatting rules — these are constraints, not suggestions:
- Output exactly 3 to 4 bullet points, no more
- Each bullet starts with a dash and a space ("- ")
- Each bullet is ≤ 14 words
- Use ₹X Cr for currency (crores)
- To bold a name use EXACTLY this pattern with both delimiters present: **Name Here**
  Wrong: Name Here**         (closing without opening — never do this)
  Wrong: **Name Here          (opening without closing — never do this)
  Right: **Name Here**        (paired, both sides present)
  Every `**` must come in a matched pair on the same line.
- Only bold vendor names, customer names, or account names — nothing else
- No headers, no intro line, no closing line, no markdown other than the paired bold

Voice: direct, prioritised, action-oriented. Lead with the single most urgent item.
Mention the specific vendor/customer/account when relevant. Reference exception types or
match statuses by name only when they are the bullet's point.
"""

import re as _re


_ORPHAN_CLOSE_RE = _re.compile(r"([A-Z][\w'.,&-]*(?:\s+[A-Z][\w'.,&-]*)*)\*\*")
_ORPHAN_OPEN_RE = _re.compile(r"\*\*([A-Z][\w'.,&-]*(?:\s+[A-Z][\w'.,&-]*)*)(?!\*\*)")


def _fix_orphan_bold(line: str) -> str:
    """
    Normalise unbalanced bold markers Claude occasionally emits.
    If the line has an odd number of `**`, pair each orphan close (`Name**`)
    with an opening `**Name**`; same for orphan opens.
    """
    if line.count("**") % 2 == 0:
        return line  # already balanced

    # First pass: convert "Name**" (closing-only) into "**Name**"
    out = _ORPHAN_CLOSE_RE.sub(lambda m: f"**{m.group(1)}**", line)

    # If still odd, drop any remaining stray `**` so the frontend doesn't render literal *
    if out.count("**") % 2 != 0:
        out = out.replace("**", "", 1)
    return out


_TAB_LABEL = {
    "P2P": "Accounts Payable (Procure-to-Pay)",
    "O2C": "Accounts Receivable (Order-to-Cash)",
    "R2R": "General Ledger (Record-to-Report)",
}


async def generate_summary(tab: str) -> dict:
    """Returns {"tab": ..., "bullets": ["- ...", "- ..."], "as_of": <iso>}."""
    import asyncio
    from datetime import datetime, timezone

    tab_u = tab.upper()
    label = _TAB_LABEL.get(tab_u, tab_u)

    # 1. Pull live signals
    try:
        signals = await asyncio.to_thread(_fetch_signals, tab_u)
    except Exception as e:
        return {"tab": tab_u, "bullets": [f"- Could not load summary signals: {e}"],
                "as_of": datetime.now(timezone.utc).isoformat()}

    # 2. Compose user message with structured signals
    user_msg = (
        f"Tab: {label}\n"
        f"Live signals (JSON):\n{json.dumps(signals, indent=2, default=str)}\n\n"
        f"Write the glance-card now. Follow the formatting rules exactly."
    )

    host = get_workspace_host()
    token = get_token()
    url = f"{host}/serving-endpoints/{LLM_ENDPOINT}/invocations"
    payload = {
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "max_tokens": 280,
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp_body = await resp.text()
                if resp.status != 200:
                    return {"tab": tab_u, "bullets": [f"- LLM error HTTP {resp.status}"],
                            "as_of": datetime.now(timezone.utc).isoformat()}
                data = json.loads(resp_body)
    except Exception as e:
        return {"tab": tab_u, "bullets": [f"- LLM call failed: {str(e)[:120]}"],
                "as_of": datetime.now(timezone.utc).isoformat()}

    # 3. Extract content
    text = ""
    for c in data.get("choices", []) or []:
        text = c.get("message", {}).get("content", "")
        if text: break
    if not text:
        text = data.get("content", "") or ""

    # 4. Normalise to a list of bullet lines, hard-cap at 4
    bullets: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if not (s.startswith("- ") or s.startswith("• ") or s.startswith("* ")):
            continue
        s = "- " + s.lstrip("-*• ").strip()
        bullets.append(_fix_orphan_bold(s))
        if len(bullets) >= 4:
            break

    if not bullets:
        # Fallback: split sentences if the LLM didn't use bullets
        for sent in text.split("."):
            s = sent.strip()
            if s and len(bullets) < 4:
                bullets.append(_fix_orphan_bold("- " + s))

    return {
        "tab": tab_u,
        "bullets": bullets,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }
