"""Finance Operations App — FastAPI backend."""
import json
import asyncio
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend import db
from backend.streams import stream_p2p, stream_o2c, stream_r2r
from backend.chat import stream_mas_agent, AGENT_ENDPOINT
from backend import lakebase
from backend.invoice_pdf import build_invoice_pdf
from backend import escalate


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: verify DB connectivity
    try:
        result = db.query("SELECT 1 as ok")
        print(f"Database connection verified: {result}")
    except Exception as e:
        print(f"WARNING: Database connection failed: {e}")
    # Initialize Lakebase schema
    try:
        lakebase.init_schema()
        print("Lakebase schema initialized successfully")
    except Exception as e:
        print(f"WARNING: Lakebase init failed (will use demo mode): {e}")
    yield


app = FastAPI(title="Finance Operations App", lifespan=lifespan)

# ─── API Routes ──────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "healthy", "app": "finance-operations"}


@app.get("/api/debug/status")
async def debug_status():
    """Diagnostics: Lakebase mode, escalate alert state."""
    from backend import escalate as _esc
    return {
        "lakebase": lakebase.get_status(),
        "escalate": {
            "alert_id": _esc._alert_id,
            "dest_id": _esc._dest_id,
            "recipient": _esc.RECIPIENT,
            "sql_cached": bool(_esc._last_sql),
        },
    }


# ── User Identity ──

@app.get("/api/me")
async def me(request: Request):
    email = request.headers.get("x-forwarded-email", "")
    raw = request.headers.get("x-forwarded-preferred-username", "") or email.split("@")[0]
    # "akash.s" -> "Akash", "akash.suresh" -> "Akash"
    first = raw.replace(".", " ").split()[0].capitalize() if raw else "User"
    return {"name": first, "email": email, "username": raw}


# ── Metrics ──

@app.get("/api/metrics/p2p")
async def metrics_p2p():
    try:
        metrics = await asyncio.to_thread(db.get_p2p_metrics)
        payment_run = await asyncio.to_thread(db.get_payment_run_data)
        return {"metrics": metrics, "payment_run": payment_run}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/metrics/o2c")
async def metrics_o2c():
    try:
        metrics = await asyncio.to_thread(db.get_o2c_metrics)
        return {"metrics": metrics}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/metrics/r2r")
async def metrics_r2r():
    try:
        metrics = await asyncio.to_thread(db.get_r2r_metrics)
        return {"metrics": metrics}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── SSE Streams ──
# Use StreamingResponse with X-Accel-Buffering: no so the Databricks Apps
# nginx proxy does not buffer events before delivering them to the browser.

_SSE_HEADERS = {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


@app.get("/stream/p2p")
async def sse_p2p(request: Request):
    async def generate():
        async for event in stream_p2p():
            if await request.is_disconnected():
                break
            yield f"data: {event}\n\n"
    return StreamingResponse(generate(), headers=_SSE_HEADERS)


@app.get("/stream/o2c")
async def sse_o2c(request: Request):
    async def generate():
        async for event in stream_o2c():
            if await request.is_disconnected():
                break
            yield f"data: {event}\n\n"
    return StreamingResponse(generate(), headers=_SSE_HEADERS)


@app.get("/stream/r2r")
async def sse_r2r(request: Request):
    async def generate():
        async for event in stream_r2r():
            if await request.is_disconnected():
                break
            yield f"data: {event}\n\n"
    return StreamingResponse(generate(), headers=_SSE_HEADERS)


# ── AI Chat ──

class ChatRequest(BaseModel):
    question: str
    active_tab: str = "P2P"
    session_id: str = ""   # client supplies UUID; server generates one if blank
    previous_response_id: str = ""  # Mosaic AI Agent response ID for stateful continuity


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """Stream the MAS response via Server-Sent Events.

    SSE event types:
      data: {"type": "chunk",  "text": "..."}
      data: {"type": "done",   "session_id": "...", "previous_response_id": "...", "routing": {...}}
      data: {"type": "error",  "message": "..."}
    """
    session_id = req.session_id.strip() or str(uuid.uuid4())
    prev_response_id = req.previous_response_id.strip() or None
    user_token = request.headers.get("x-forwarded-access-token")
    user_email = request.headers.get("x-forwarded-email", "anonymous")

    # Load Lakebase history to replay prior turns in the input array
    history = await asyncio.to_thread(lakebase.get_session_messages, session_id, 10)
    if history:
        messages = list(history[-20:])
        messages.append({"role": "user", "content": req.question})
    else:
        messages = [{"role": "user", "content": req.question}]

    async def generate():
        full_answer = ""
        response_id = None
        tool_name = None

        try:
            async for event in stream_mas_agent(messages, user_token=user_token, previous_response_id=prev_response_id):
                if event["type"] == "chunk":
                    full_answer += event["text"]
                    yield f"data: {json.dumps({'type': 'chunk', 'text': event['text']})}\n\n"
                elif event["type"] == "done":
                    response_id = event.get("response_id")
                    tool_name = event.get("tool")
                elif event["type"] == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': event['message']})}\n\n"
                    return
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return

        if not full_answer.strip():
            full_answer = "The agent returned no answer. Please try rephrasing."
            yield f"data: {json.dumps({'type': 'chunk', 'text': full_answer})}\n\n"

        # Persist this turn to Lakebase
        routing_info = {
            "domain": "Finance Agent",
            "explanation": f"Mosaic AI Agent → {tool_name}" if tool_name else "Routed via Mosaic AI Agent",
            "tool": tool_name,
        }
        await asyncio.to_thread(
            lakebase.log_chat,
            session_id, user_email, req.active_tab, req.question,
            AGENT_ENDPOINT, full_answer, "", routing_info, response_id,
        )

        done_payload = {
            "type": "done",
            "session_id": session_id,
            "previous_response_id": response_id or "",
            "routing": routing_info,
            "agent": AGENT_ENDPOINT,
        }
        yield f"data: {json.dumps(done_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Session History ──

@app.get("/api/my-sessions")
async def my_sessions(request: Request):
    """Return session cards for the current user, most recent first."""
    user = request.headers.get("x-forwarded-email", "anonymous")
    try:
        sessions = await asyncio.to_thread(lakebase.get_user_sessions, user)
        return {"sessions": sessions}
    except Exception as e:
        return {"sessions": [], "error": str(e)}


@app.get("/api/session/{session_id}")
async def get_session(session_id: str, request: Request):
    """Return full Q&A history + last previous_response_id for a session."""
    user = request.headers.get("x-forwarded-email", "anonymous")
    try:
        detail = await asyncio.to_thread(lakebase.get_session_detail, session_id, user)
        return {
            "session_id": session_id,
            "messages": detail.get("messages", []),
            "previous_response_id": detail.get("previous_response_id"),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Lakebase: AP Approvals ──

class ApprovalRequest(BaseModel):
    invoice_id: str
    action: str  # APPROVED, REJECTED, ESCALATED
    reason: str = ""

@app.post("/api/approve")
async def approve_invoice(req: ApprovalRequest, request: Request):
    user = request.headers.get("x-forwarded-email", "unknown")
    try:
        await asyncio.to_thread(lakebase.log_approval, req.invoice_id, req.action, req.reason, user)
        return {"status": "logged", "action": req.action, "invoice_id": req.invoice_id}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})



# ── Escalation: AP Exceptions via Databricks SQL Alert ───────────────────────

class EscalateRequest(BaseModel):
    exception_types: list[str]  # e.g. ["AMOUNT_MISMATCH", "NO_PO_REFERENCE"]

@app.post("/api/escalate/p2p")
async def escalate_p2p(req: EscalateRequest):
    """
    Create/update a Databricks SQL Alert for the selected exception types
    and unpause it so Databricks fires the email within ~60 seconds.
    Recipient is set via ESCALATION_RECIPIENT env var — not from the UI.
    """
    try:
        result = await asyncio.to_thread(escalate.run_escalation, req.exception_types)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Lakebase: AR Call Logs ──

class CallLogRequest(BaseModel):
    customer_id: str
    customer_name: str = ""
    outcome: str  # REACHED_PTP, REACHED_DISPUTE, VOICEMAIL, ESCALATE
    ptp_date: str | None = None
    notes: str = ""

@app.post("/api/call-log")
async def call_log(req: CallLogRequest, request: Request):
    user = request.headers.get("x-forwarded-email", "unknown")
    try:
        await asyncio.to_thread(
            lakebase.log_call, req.customer_id, req.customer_name,
            req.outcome, req.ptp_date, req.notes, user
        )
        return {"status": "logged", "outcome": req.outcome}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Lakebase: User History ──

@app.get("/api/my-approvals")
async def my_approvals(request: Request):
    user = request.headers.get("x-forwarded-email", "unknown")
    try:
        approvals = await asyncio.to_thread(lakebase.get_user_approvals, user)
        return {"approvals": approvals}
    except Exception as e:
        return {"approvals": [], "error": str(e)}


# ── Invoice Viewer ──

def _build_invoice_response(row: dict) -> dict:
    """Coerce a DB row or demo dict to the invoice response shape."""
    return {
        "invoice_id":        row.get("invoice_id"),
        "invoice_number":    row.get("invoice_number"),
        "quarantine_reason": row.get("quarantine_reason"),
        "vendor_id":         row.get("vendor_id"),
        "vendor_name":       row.get("vendor_name"),
        "po_id":             row.get("po_id"),
        "invoice_date":      str(row.get("invoice_date") or ""),
        "due_date":          str(row.get("due_date") or ""),
        "invoice_amount":    float(row.get("invoice_amount") or 0),
        "po_amount":         float(row.get("po_amount") or row.get("invoice_amount") or 0),
        "status":            row.get("status") or row.get("invoice_status"),
        "gstin":             row.get("gstin_vendor") or row.get("gstin"),
        "payment_terms":     row.get("payment_terms"),
        "raw_text":          row.get("raw_text") or "",
        "file_path":         row.get("file_path") or "",
    }


def _demo_invoice_fallback(invoice_id: str) -> dict | None:
    """Return a demo invoice when the warehouse is unavailable."""
    demo_pool = db._get_demo_invoices(200)
    for inv in demo_pool:
        if inv.get("invoice_id") == invoice_id or inv.get("invoice_number") == invoice_id:
            return {**inv, "quarantine_reason": inv.get("match_status") if inv.get("match_status") not in ("THREE_WAY_MATCHED", "TWO_WAY_MATCHED") else None, "raw_text": "", "file_path": ""}
    # Construct a plausible demo invoice for any unknown ID
    return {
        "invoice_id": invoice_id,
        "invoice_number": invoice_id if invoice_id.startswith("VINV-") else f"VINV-2025-{abs(hash(invoice_id)) % 99999:05d}",
        "quarantine_reason": "AMOUNT_MISMATCH",
        "vendor_id": "V001",
        "vendor_name": "Demo Vendor Co.",
        "po_id": "PO-2025-DEMO",
        "invoice_date": "2025-03-01",
        "due_date": "2025-04-01",
        "invoice_amount": 450000.0,
        "po_amount": 420000.0,
        "status": "PENDING",
        "gstin": "29AABCT1234H1Z2",
        "payment_terms": "Net 30",
        "raw_text": "",
        "file_path": "",
    }


@app.get("/api/invoice/{invoice_id}")
async def get_invoice(invoice_id: str):
    """
    Return full invoice details for any invoice ID or ERP invoice_number.
    Searches in order: gold_fact_invoices → silver_invoice_exceptions → bronze_p2p_invoices.
    Falls back to demo data when the warehouse is unavailable.
    """
    import re as _re
    is_erp_number = bool(_re.match(r'^VINV-\d{4}-\d+$', invoice_id))
    gold_col  = "i.invoice_number" if is_erp_number else "i.invoice_id"
    exc_col   = "e.invoice_number" if is_erp_number else "e.invoice_id"
    bronze_col = "b.invoice_number" if is_erp_number else "b.invoice_id"

    try:
        # 1️⃣ Primary: gold_fact_invoices (same table the SSE stream reads from)
        rows = await asyncio.to_thread(db.query, f"""
            SELECT
                i.invoice_id,
                i.invoice_number,
                CASE WHEN i.match_status NOT IN ('THREE_WAY_MATCHED','TWO_WAY_MATCHED')
                     THEN i.match_status ELSE NULL END AS quarantine_reason,
                i.vendor_id,
                v.vendor_name,
                i.po_id,
                i.invoice_date,
                i.due_date,
                i.invoice_amount,
                i.invoice_total_inr      AS po_amount,
                i.invoice_status         AS status,
                i.gstin_vendor,
                NULL                     AS payment_terms,
                r.raw_text,
                r.file_path
            FROM hp_sf_test.finance_and_accounting.gold_fact_invoices i
            LEFT JOIN hp_sf_test.finance_and_accounting.gold_dim_vendor v
                ON i.vendor_id = v.vendor_id
            LEFT JOIN hp_sf_test.finance_and_accounting.bronze_raw_invoice_documents r
                ON i.invoice_id = r.invoice_id
            WHERE {gold_col} = '{invoice_id}'
            LIMIT 1
        """)

        # 2️⃣ Fallback: silver_invoice_exceptions (has payment_terms + original amounts)
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    e.invoice_id,
                    e.invoice_number,
                    e.exception_type      AS quarantine_reason,
                    e.vendor_id,
                    v.vendor_name,
                    e.po_id,
                    e.invoice_date,
                    e.due_date,
                    e.invoice_amount,
                    e.total_amount        AS po_amount,
                    e.status,
                    e.gstin_vendor,
                    e.payment_terms,
                    r.raw_text,
                    r.file_path
                FROM hp_sf_test.finance_and_accounting.silver_invoice_exceptions e
                LEFT JOIN hp_sf_test.finance_and_accounting.bronze_raw_invoice_documents r
                    ON e.invoice_id = r.invoice_id
                LEFT JOIN hp_sf_test.finance_and_accounting.silver_vendors v
                    ON e.vendor_id = v.vendor_id
                WHERE {exc_col} = '{invoice_id}'
                LIMIT 1
            """)

        # 3️⃣ Last resort: bronze_p2p_invoices
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    b.invoice_id,
                    b.invoice_number,
                    NULL              AS quarantine_reason,
                    b.vendor_id,
                    v.vendor_name,
                    b.po_id,
                    b.invoice_date,
                    b.due_date,
                    b.invoice_amount,
                    b.total_amount    AS po_amount,
                    b.status,
                    b.gstin_vendor,
                    b.payment_terms,
                    r.raw_text,
                    r.file_path
                FROM hp_sf_test.finance_and_accounting.bronze_p2p_invoices b
                LEFT JOIN hp_sf_test.finance_and_accounting.bronze_raw_invoice_documents r
                    ON b.invoice_id = r.invoice_id
                LEFT JOIN hp_sf_test.finance_and_accounting.silver_vendors v
                    ON b.vendor_id = v.vendor_id
                WHERE {bronze_col} = '{invoice_id}'
                LIMIT 1
            """)

        if rows:
            return _build_invoice_response(rows[0])

        # 4️⃣ Demo fallback when warehouse is unreachable
        return _build_invoice_response(_demo_invoice_fallback(invoice_id))

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/invoice/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, download: bool = Query(False)):
    """
    Generate and stream a PDF for the given invoice.
    Searches gold_fact_invoices first, then silver_invoice_exceptions, then bronze_p2p_invoices.
    Falls back to demo data when the warehouse is unreachable.
    """
    import re as _re
    is_erp_number = bool(_re.match(r'^VINV-\d{4}-\d+$', invoice_id))
    gold_col   = "i.invoice_number" if is_erp_number else "i.invoice_id"
    exc_col    = "e.invoice_number" if is_erp_number else "e.invoice_id"
    bronze_col = "b.invoice_number" if is_erp_number else "b.invoice_id"

    try:
        # 1️⃣ gold_fact_invoices (primary — matches the SSE stream source)
        rows = await asyncio.to_thread(db.query, f"""
            SELECT
                i.invoice_id, i.invoice_number,
                CASE WHEN i.match_status NOT IN ('THREE_WAY_MATCHED','TWO_WAY_MATCHED')
                     THEN i.match_status ELSE NULL END AS quarantine_reason,
                i.vendor_id, v.vendor_name, i.po_id,
                i.invoice_date, i.due_date, i.invoice_amount, i.invoice_total_inr AS po_amount,
                i.invoice_status AS status, i.gstin_vendor, NULL AS payment_terms,
                r.raw_text, r.file_path
            FROM hp_sf_test.finance_and_accounting.gold_fact_invoices i
            LEFT JOIN hp_sf_test.finance_and_accounting.gold_dim_vendor v ON i.vendor_id = v.vendor_id
            LEFT JOIN hp_sf_test.finance_and_accounting.bronze_raw_invoice_documents r ON i.invoice_id = r.invoice_id
            WHERE {gold_col} = '{invoice_id}'
            LIMIT 1
        """)

        # 2️⃣ silver_invoice_exceptions
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    e.invoice_id, e.invoice_number, e.exception_type AS quarantine_reason,
                    e.vendor_id, v.vendor_name, e.po_id,
                    e.invoice_date, e.due_date, e.invoice_amount, e.total_amount AS po_amount,
                    e.status, e.gstin_vendor, e.payment_terms,
                    r.raw_text, r.file_path
                FROM hp_sf_test.finance_and_accounting.silver_invoice_exceptions e
                LEFT JOIN hp_sf_test.finance_and_accounting.bronze_raw_invoice_documents r ON e.invoice_id = r.invoice_id
                LEFT JOIN hp_sf_test.finance_and_accounting.silver_vendors v ON e.vendor_id = v.vendor_id
                WHERE {exc_col} = '{invoice_id}'
                LIMIT 1
            """)

        # 3️⃣ bronze_p2p_invoices
        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    b.invoice_id, b.invoice_number, NULL AS quarantine_reason,
                    b.vendor_id, v.vendor_name, b.po_id,
                    b.invoice_date, b.due_date, b.invoice_amount, b.total_amount AS po_amount,
                    b.status, b.gstin_vendor, b.payment_terms,
                    r.raw_text, r.file_path
                FROM hp_sf_test.finance_and_accounting.bronze_p2p_invoices b
                LEFT JOIN hp_sf_test.finance_and_accounting.bronze_raw_invoice_documents r ON b.invoice_id = r.invoice_id
                LEFT JOIN hp_sf_test.finance_and_accounting.silver_vendors v ON b.vendor_id = v.vendor_id
                WHERE {bronze_col} = '{invoice_id}'
                LIMIT 1
            """)

        erp = _build_invoice_response(rows[0] if rows else _demo_invoice_fallback(invoice_id))
        raw_text = (rows[0].get("raw_text") or "") if rows else ""

        pdf_bytes = await asyncio.to_thread(build_invoice_pdf, erp, raw_text)

        filename = f"invoice-{invoice_id}.pdf"
        disposition = f'attachment; filename="{filename}"' if download else f'inline; filename="{filename}"'
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": disposition},
        )

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# ─── Static Files (React build) ─────────────────────────────

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    # Mount assets directory for JS/CSS
    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # Serve other static files (favicon, etc.)
    @app.get("/vite.svg")
    async def vite_svg():
        f = static_dir / "vite.svg"
        if f.exists():
            return FileResponse(str(f))
        return JSONResponse(status_code=404, content={"error": "not found"})

    # SPA fallback — must be last
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # Don't catch API/stream routes
        if full_path.startswith("api/") or full_path.startswith("stream/"):
            return JSONResponse(status_code=404, content={"error": "not found"})
        index = static_dir / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse(status_code=404, content={"error": "Frontend not built. Run: cd frontend && npm run build"})
else:
    @app.get("/")
    async def root():
        return {"message": "Finance Operations API. Frontend not built yet.",
                "hint": "Run: cd frontend && npm run build && cp -r frontend/dist/* backend/static/"}
