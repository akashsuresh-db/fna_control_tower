"""Finance AI Chat — MAS supervisor with client-side SQL execution.

Architecture:
  1. Call MAS endpoint (multi-agent supervisor) — it routes the query to the
     right domain agent (AP/AR/GL) and returns a structured function_call.
  2. Execute the referenced SQL query against the gold Delta Lake tables.
  3. Call Claude Sonnet 4.6 (via Databricks Foundation Models) with the real
     data as context to produce a natural-language, data-grounded answer.
  4. Stream the answer in ~40-char chunks for live typing-effect UX.

Session history is persisted to Lakebase (falls back to in-memory).
"""
import os
import json
import re
import aiohttp
from backend.config import get_workspace_host, get_token, CATALOG, SCHEMA, full_table

MAS_ENDPOINT = os.environ.get("SERVING_ENDPOINT_NAME", "mas-2dcd8d5a-endpoint")
AGENT_ENDPOINT = MAS_ENDPOINT  # backwards-compat
FMAPI_MODEL = MAS_ENDPOINT     # backwards-compat
_LLM_ENDPOINT = "databricks-claude-sonnet-4-6"


def _token(user_token: str | None = None) -> str:
    sp_token = get_token()
    if sp_token:
        return sp_token
    if user_token:
        return user_token
    return ""


# ── SQL context queries by domain ──────────────────────────────

_P2P_CONTEXT_SQL = f"""
SELECT
    COUNT(*) AS total_invoices,
    SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) AS three_way_matched,
    SUM(CASE WHEN match_status = 'TWO_WAY_MATCHED'   THEN 1 ELSE 0 END) AS two_way_matched,
    SUM(CASE WHEN match_status = 'AMOUNT_MISMATCH'   THEN 1 ELSE 0 END) AS amount_mismatch,
    SUM(CASE WHEN match_status = 'NO_PO_REFERENCE'   THEN 1 ELSE 0 END) AS no_po_reference,
    SUM(CASE WHEN match_status = 'EXTRACTION_MISMATCH' THEN 1 ELSE 0 END) AS extraction_mismatch,
    SUM(CASE WHEN is_overdue = true THEN 1 ELSE 0 END) AS overdue_invoices,
    ROUND(SUM(invoice_total_inr) / 1e7, 2) AS total_value_cr,
    ROUND(SUM(CASE WHEN is_overdue THEN invoice_total_inr ELSE 0 END) / 1e7, 2) AS overdue_value_cr,
    ROUND(AVG(aging_days), 1) AS avg_aging_days,
    ROUND(SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS touchless_rate_pct
FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_invoices`
"""

_P2P_EXCEPTIONS_SQL = f"""
SELECT match_status, COUNT(*) AS count,
       ROUND(SUM(invoice_total_inr)/1e7, 2) AS value_cr
FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_invoices`
WHERE match_status NOT IN ('THREE_WAY_MATCHED', 'TWO_WAY_MATCHED')
GROUP BY match_status ORDER BY count DESC
"""

_O2C_CONTEXT_SQL = f"""
SELECT
    COUNT(*) AS total_invoices,
    SUM(CASE WHEN is_fully_collected THEN 1 ELSE 0 END) AS collected,
    SUM(CASE WHEN days_overdue > 0 THEN 1 ELSE 0 END) AS overdue_count,
    ROUND(SUM(balance_outstanding)/1e7, 2) AS outstanding_cr,
    ROUND(SUM(amount_collected_inr)/1e7, 2) AS collected_cr,
    ROUND(AVG(days_outstanding), 1) AS avg_dso
FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_collections`
"""

_O2C_RISK_SQL = f"""
SELECT customer_name, ROUND(outstanding_ar_inr/1e7,2) AS outstanding_cr,
       credit_utilization_pct AS utilization_pct, dso, overdue_invoices
FROM `{CATALOG}`.`{SCHEMA}`.`gold_dim_customer`
WHERE credit_utilization_pct > 100
ORDER BY credit_utilization_pct DESC LIMIT 5
"""

_R2R_CONTEXT_SQL = f"""
SELECT
    COUNT(DISTINCT je_id) AS total_jes,
    COUNT(*) AS total_lines,
    COUNT(DISTINCT CASE WHEN status='POSTED' THEN je_id END) AS posted_jes,
    COUNT(DISTINCT CASE WHEN status='PENDING' THEN je_id END) AS pending_jes,
    ROUND(SUM(debit_inr)/1e7, 2) AS total_debits_cr,
    ROUND(SUM(credit_inr)/1e7, 2) AS total_credits_cr
FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_gl`
"""

_TB_CONTEXT_SQL = f"""
SELECT account_code, account_name, account_type, balance_type,
       ROUND(closing_balance_inr/1e7, 2) AS balance_cr, transaction_count
FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_trial_balance`
WHERE period = (SELECT MAX(period) FROM `{CATALOG}`.`{SCHEMA}`.`gold_fact_trial_balance`)
ORDER BY account_code LIMIT 10
"""


def _get_domain_context(domain: str) -> str:
    """Run SQL queries and build a rich context string for the LLM."""
    from backend import db

    if domain in ("P2P", "AP", "ap"):
        rows = db.query(_P2P_CONTEXT_SQL)
        exc = db.query(_P2P_EXCEPTIONS_SQL)
        if not rows:
            return "No AP data available."
        r = rows[0]
        ctx = f"""AP/P2P Invoice Summary (INR values in Crores):
- Total invoices in queue: {r.get('total_invoices', 0)}
- THREE_WAY_MATCHED (touchless): {r.get('three_way_matched', 0)} ({r.get('touchless_rate_pct', 0)}% touchless rate)
- TWO_WAY_MATCHED: {r.get('two_way_matched', 0)}
- AMOUNT_MISMATCH exceptions: {r.get('amount_mismatch', 0)}
- NO_PO_REFERENCE exceptions: {r.get('no_po_reference', 0)}
- EXTRACTION_MISMATCH (PDF vs ERP fraud flags): {r.get('extraction_mismatch', 0)}
- Overdue invoices: {r.get('overdue_invoices', 0)}
- Total value in queue: ₹{r.get('total_value_cr', 0)} Cr
- Overdue value: ₹{r.get('overdue_value_cr', 0)} Cr
- Average aging: {r.get('avg_aging_days', 0)} days
Exception breakdown:
""" + "\n".join([f"  - {e.get('match_status')}: {e.get('count')} invoices (₹{e.get('value_cr',0)} Cr)" for e in exc])
        return ctx

    elif domain in ("O2C", "AR", "ar"):
        rows = db.query(_O2C_CONTEXT_SQL)
        risk = db.query(_O2C_RISK_SQL)
        if not rows:
            return "No AR data available."
        r = rows[0]
        ctx = f"""AR/O2C Collections Summary (INR values in Crores):
- Total AR invoices: {r.get('total_invoices', 0)}
- Fully collected: {r.get('collected', 0)}
- Overdue invoices: {r.get('overdue_count', 0)}
- Outstanding AR: ₹{r.get('outstanding_cr', 0)} Cr
- Total collected: ₹{r.get('collected_cr', 0)} Cr
- Average DSO: {r.get('avg_dso', 0)} days
Top customers over credit limit:
""" + "\n".join([f"  - {c.get('customer_name')}: ₹{c.get('outstanding_cr',0)} Cr outstanding, {c.get('utilization_pct',0)}% utilization, DSO={c.get('dso',0)}" for c in risk])
        return ctx

    elif domain in ("R2R", "GL", "gl"):
        rows = db.query(_R2R_CONTEXT_SQL)
        tb = db.query(_TB_CONTEXT_SQL)
        if not rows:
            return "No GL data available."
        r = rows[0]
        ctx = f"""R2R/GL Journal Entry Summary (INR values in Crores):
- Total journal entries: {r.get('total_jes', 0)}
- Total lines: {r.get('total_lines', 0)}
- Posted: {r.get('posted_jes', 0)}, Pending: {r.get('pending_jes', 0)}
- Total debits: ₹{r.get('total_debits_cr', 0)} Cr
- Total credits: ₹{r.get('total_credits_cr', 0)} Cr (balanced: {abs((r.get('total_debits_cr',0) or 0) - (r.get('total_credits_cr',0) or 0)) < 0.01})
Trial Balance (top accounts):
""" + "\n".join([f"  - {t.get('account_code')} {t.get('account_name')} ({t.get('account_type')}): ₹{t.get('balance_cr',0)} Cr {t.get('balance_type')}" for t in tb])
        return ctx

    # Generic: pull all three summaries
    return _get_domain_context("P2P") + "\n\n" + _get_domain_context("O2C") + "\n\n" + _get_domain_context("R2R")


def _extract_mas_answer(body: str) -> str:
    """
    Extract the final human-readable answer from a MAS Agents API response.

    Handles multiple response formats produced by different deployment paths:
      - databricks.agents.deploy()  → {"output": {"messages": [{"type":"ai","content":"..."}]}}
      - serving_endpoints SDK        → {"output": [{"type":"message","content":[{"text":"..."}]}]}
      - OpenAI-compat                → {"choices": [{"message":{"content":"..."}}]}

    Returns empty string if the response contains only tool-routing XML (incomplete execution)
    or could not be parsed.
    """
    try:
        d = json.loads(body)

        # Format 1: agents.deploy() — LangGraph output with messages list
        output = d.get("output", {})
        if isinstance(output, dict):
            for msg in reversed(output.get("messages", [])):
                content = msg.get("content", "")
                if content and "<function_calls>" not in str(content):
                    return content if isinstance(content, str) else str(content)

        # Format 2: output is a plain string (simple agent response)
        if isinstance(output, str) and "<function_calls>" not in output and output.strip():
            return output

        # Format 3: serving_endpoints list-of-messages format
        if isinstance(output, list):
            for item in reversed(output):
                if item.get("type") == "message":
                    for c in item.get("content", []):
                        text = c.get("text", "")
                        if text and "<function_calls>" not in text:
                            return text

        # Format 4: OpenAI-compatible choices
        for choice in d.get("choices", []):
            content = choice.get("message", {}).get("content", "")
            if content and "<function_calls>" not in content:
                return content

    except Exception:
        pass
    return ""


def _extract_mas_tool_call(text: str) -> dict | None:
    """Parse <function_calls> XML to get the routing intent tool name."""
    m = re.search(r'<invoke\s+name="([^"]+)">', text)
    if not m:
        return None
    name = m.group(1)
    q_match = re.search(r'<parameter\s+name="(?:query|input)">(.*?)</parameter>', text, re.DOTALL)
    query = q_match.group(1).strip() if q_match else ""
    return {"name": name, "query": query}


def _domain_from_tool_name(tool_name: str, active_tab: str) -> str:
    """Infer the finance domain from the MAS tool name."""
    low = tool_name.lower()
    if "ap" in low or "p2p" in low or "payable" in low:
        return "P2P"
    if "ar" in low or "o2c" in low or "receivable" in low or "collection" in low:
        return "O2C"
    return active_tab or "P2P"


async def stream_mas_agent(
    messages: list[dict],
    user_token: str | None = None,
    previous_response_id: str | None = None,
    active_tab: str = "P2P",
):
    """
    Call MAS supervisor (LangGraph + GenieTool) and stream the answer.

    Flow:
      1. POST to MAS endpoint — with GenieTool wired, the supervisor executes
         the full Genie query server-side and returns a complete answer.
      2. If MAS returns a complete answer: stream it in chunks for typing effect.
      3. If MAS returns only routing XML (incomplete execution / Genie unavailable):
         fall through to direct SQL + Claude synthesis as a degraded fallback.

    Yields dicts:
      {"type": "chunk",  "text": "..."}
      {"type": "done",   "response_id": None, "tool": None}
      {"type": "error",  "message": "..."}
    """
    import asyncio

    token = _token(user_token)
    host = get_workspace_host()
    mas_url = f"{host}/serving-endpoints/{MAS_ENDPOINT}/invocations"
    llm_url = f"{host}/serving-endpoints/{_LLM_ENDPOINT}/invocations"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # ── Step 1: Call MAS supervisor (LangGraph agent with GenieTool) ───────────
    # Use messages format — required by LangGraph agents deployed via agents.deploy()
    mas_payload = {"messages": list(messages)}
    mas_answer = ""
    tool_call = None

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                mas_url, json=mas_payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    body = await resp.text()
                    mas_answer = _extract_mas_answer(body)
                    if not mas_answer:
                        # Try parsing routing XML for domain detection (fallback path)
                        try:
                            d = json.loads(body)
                            raw = ""
                            output = d.get("output", [])
                            if isinstance(output, list):
                                for item in output:
                                    if item.get("type") == "message":
                                        for c in item.get("content", []):
                                            raw += c.get("text", "")
                            tool_call = _extract_mas_tool_call(raw)
                        except Exception:
                            pass
                else:
                    print(f"[chat] MAS returned HTTP {resp.status}")
    except Exception as e:
        print(f"[chat] MAS call failed: {e}")

    # ── Step 2: Stream the MAS answer directly if Genie returned a full response ─
    if mas_answer:
        chunk_size = 40
        for i in range(0, len(mas_answer), chunk_size):
            yield {"type": "chunk", "text": mas_answer[i:i + chunk_size]}
            await asyncio.sleep(0.02)
        yield {"type": "done", "response_id": None, "tool": "genie_agent"}
        return

    # ── Step 3: Fallback — MAS did not return a complete answer (Genie unavailable)
    # Use direct SQL context + Claude synthesis. This path should not trigger once
    # the MAS supervisor is deployed with GenieTool pointing at an active Genie Space.
    print(f"[chat] MAS did not return a complete answer — falling back to SQL+Claude")
    domain = active_tab
    if tool_call:
        domain = _domain_from_tool_name(tool_call["name"], active_tab)

    try:
        context = await asyncio.to_thread(_get_domain_context, domain)
    except Exception as e:
        context = f"(Could not fetch live data: {e})"

    # ── Step 3: Build LLM prompt with real data context ────────
    # Peel off the last user message to use as the question
    user_question = ""
    conversation_history = []
    for msg in messages:
        if msg.get("role") == "user":
            user_question = msg.get("content", "")
            conversation_history = [m for m in messages if m != msg]

    system_prompt = f"""You are an expert CFO assistant for an Indian enterprise.
You have access to real-time financial data from the company's Delta Lake data platform.

Current live data context ({domain} domain):
{context}

Instructions:
- Answer the user's question using ONLY the data provided above
- Be concise but specific — use actual numbers from the data
- Format currency as ₹X Cr (crores)
- Highlight critical issues (high exception rates, overdue amounts, fraud flags)
- For EXTRACTION_MISMATCH items, mention these are PDF-vs-ERP discrepancies (potential fraud)
- Keep response under 200 words unless asked for detail
"""

    llm_messages = [{"role": "system", "content": system_prompt}]
    # Add relevant conversation history (last 6 turns)
    for msg in conversation_history[-6:]:
        llm_messages.append(msg)
    llm_messages.append({"role": "user", "content": user_question})

    # ── Step 4: Stream answer from Claude ──────────────────────
    llm_payload = {
        "messages": llm_messages,
        "max_tokens": 512,
        "stream": True,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                llm_url, json=llm_payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=90),
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    yield {"type": "error", "message": f"LLM HTTP {resp.status}: {error_text[:200]}"}
                    return

                # Stream SSE chunks from Claude
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            chunk = json.loads(line[6:])
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                yield {"type": "chunk", "text": delta}
                        except Exception:
                            pass

        yield {"type": "done", "response_id": None, "tool": tool_call["name"] if tool_call else None}

    except Exception as e:
        yield {"type": "error", "message": str(e)}


async def handle_chat(
    question: str,
    active_tab: str = "P2P",
    user_token: str | None = None,
    history: list[dict] | None = None,
    previous_response_id: str | None = None,
) -> dict:
    """Send a question to the finance agent and return a structured result."""
    result = {
        "question": question,
        "domain": active_tab,
        "routing": {
            "domain": "MAS Supervisor",
            "explanation": f"Routed via {MAS_ENDPOINT} → {_LLM_ENDPOINT}",
        },
        "genie_response": None,
        "sql": None,
        "data": None,
        "answer": None,
        "error": None,
        "agent": MAS_ENDPOINT,
        "previous_response_id": None,
    }

    messages = list(history[-20:]) if history else []
    messages.append({"role": "user", "content": question})

    full_answer = ""
    async for event in stream_mas_agent(messages, user_token=user_token, active_tab=active_tab):
        if event["type"] == "chunk":
            full_answer += event["text"]
        elif event["type"] == "error":
            result["error"] = event["message"]
            return result

    result["answer"] = full_answer.strip() or "No answer returned. Please try again."
    return result
