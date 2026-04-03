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
from sse_starlette.sse import EventSourceResponse

from backend import db
from backend.streams import stream_p2p, stream_o2c, stream_r2r
from backend.chat import stream_mas_agent, AGENT_ENDPOINT
from backend import lakebase
from backend.invoice_pdf import build_invoice_pdf


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

@app.get("/stream/p2p")
async def sse_p2p(request: Request):
    async def event_generator():
        async for event in stream_p2p():
            if await request.is_disconnected():
                break
            yield {"data": event}
    return EventSourceResponse(event_generator())


@app.get("/stream/o2c")
async def sse_o2c(request: Request):
    async def event_generator():
        async for event in stream_o2c():
            if await request.is_disconnected():
                break
            yield {"data": event}
    return EventSourceResponse(event_generator())


@app.get("/stream/r2r")
async def sse_r2r(request: Request):
    async def event_generator():
        async for event in stream_r2r():
            if await request.is_disconnected():
                break
            yield {"data": event}
    return EventSourceResponse(event_generator())


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

@app.get("/api/invoice/{invoice_id}")
async def get_invoice(invoice_id: str):
    """
    Return full invoice details + raw source file text for any invoice ID.
    Accepts both internal invoice_id (INV000001) and ERP invoice_number (VINV-2025-XXXXX).
    Pulls quarantine/exception metadata from silver_invoice_exceptions and
    bronze_p2p_invoices_quarantine, and raw text from bronze_raw_invoice_documents.
    """
    import re as _re
    # Determine which column to match against
    is_erp_number = bool(_re.match(r'^VINV-\d{4}-\d+$', invoice_id))
    exc_col = "e.invoice_number" if is_erp_number else "e.invoice_id"
    bronze_col = "b.invoice_number" if is_erp_number else "b.invoice_id"

    try:
        rows = await asyncio.to_thread(db.query, f"""
            SELECT
                e.invoice_id,
                e.invoice_number,
                e.exception_type          AS quarantine_reason,
                e.vendor_id,
                v.vendor_name,
                e.po_id,
                e.invoice_date,
                e.due_date,
                e.invoice_amount,
                e.total_amount            AS po_amount,
                e.status,
                e.gstin_vendor,
                e.payment_terms,
                r.raw_text,
                r.file_path
            FROM akash_s_demo.finance_and_accounting.silver_invoice_exceptions e
            LEFT JOIN akash_s_demo.finance_and_accounting.bronze_raw_invoice_documents r
                ON e.invoice_id = r.invoice_id
            LEFT JOIN akash_s_demo.finance_and_accounting.silver_vendors v
                ON e.vendor_id = v.vendor_id
            WHERE {exc_col} = '{invoice_id}'
            LIMIT 1
        """)

        if not rows:
            # Not quarantined — try to find it in the main invoice table
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
                FROM akash_s_demo.finance_and_accounting.bronze_p2p_invoices b
                LEFT JOIN akash_s_demo.finance_and_accounting.bronze_raw_invoice_documents r
                    ON b.invoice_id = r.invoice_id
                LEFT JOIN akash_s_demo.finance_and_accounting.silver_vendors v
                    ON b.vendor_id = v.vendor_id
                WHERE {bronze_col} = '{invoice_id}'
                LIMIT 1
            """)

        if not rows:
            return JSONResponse(status_code=404, content={"error": f"Invoice {invoice_id} not found"})

        row = rows[0]
        # Coerce Decimal / date types to JSON-serialisable forms
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
            "po_amount":         float(row.get("po_amount") or 0),
            "status":            row.get("status"),
            "gstin":             row.get("gstin_vendor"),
            "payment_terms":     row.get("payment_terms"),
            "raw_text":          row.get("raw_text") or "",
            "file_path":         row.get("file_path") or "",
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/invoice/{invoice_id}/pdf")
async def get_invoice_pdf(invoice_id: str, download: bool = Query(False)):
    """
    Generate and stream a PDF for the given invoice.
    ?download=true sets Content-Disposition: attachment so the browser downloads it.
    """
    import re as _re
    is_erp_number = bool(_re.match(r'^VINV-\d{4}-\d+$', invoice_id))
    exc_col    = "e.invoice_number" if is_erp_number else "e.invoice_id"
    bronze_col = "b.invoice_number" if is_erp_number else "b.invoice_id"

    try:
        rows = await asyncio.to_thread(db.query, f"""
            SELECT
                e.invoice_id, e.invoice_number, e.exception_type AS quarantine_reason,
                e.vendor_id, v.vendor_name, e.po_id,
                e.invoice_date, e.due_date, e.invoice_amount, e.total_amount AS po_amount,
                e.status, e.gstin_vendor, e.payment_terms,
                r.raw_text, r.file_path
            FROM akash_s_demo.finance_and_accounting.silver_invoice_exceptions e
            LEFT JOIN akash_s_demo.finance_and_accounting.bronze_raw_invoice_documents r
                ON e.invoice_id = r.invoice_id
            LEFT JOIN akash_s_demo.finance_and_accounting.silver_vendors v
                ON e.vendor_id = v.vendor_id
            WHERE {exc_col} = '{invoice_id}'
            LIMIT 1
        """)

        if not rows:
            rows = await asyncio.to_thread(db.query, f"""
                SELECT
                    b.invoice_id, b.invoice_number, NULL AS quarantine_reason,
                    b.vendor_id, v.vendor_name, b.po_id,
                    b.invoice_date, b.due_date, b.invoice_amount, b.total_amount AS po_amount,
                    b.status, b.gstin_vendor, b.payment_terms,
                    r.raw_text, r.file_path
                FROM akash_s_demo.finance_and_accounting.bronze_p2p_invoices b
                LEFT JOIN akash_s_demo.finance_and_accounting.bronze_raw_invoice_documents r
                    ON b.invoice_id = r.invoice_id
                LEFT JOIN akash_s_demo.finance_and_accounting.silver_vendors v
                    ON b.vendor_id = v.vendor_id
                WHERE {bronze_col} = '{invoice_id}'
                LIMIT 1
            """)

        if not rows:
            return JSONResponse(status_code=404, content={"error": f"Invoice {invoice_id} not found"})

        row = rows[0]
        erp = {
            "invoice_id":        row.get("invoice_id"),
            "invoice_number":    row.get("invoice_number"),
            "quarantine_reason": row.get("quarantine_reason"),
            "vendor_id":         row.get("vendor_id"),
            "vendor_name":       row.get("vendor_name"),
            "po_id":             row.get("po_id"),
            "invoice_date":      str(row.get("invoice_date") or ""),
            "due_date":          str(row.get("due_date") or ""),
            "invoice_amount":    float(row.get("invoice_amount") or 0),
            "po_amount":         float(row.get("po_amount") or 0),
            "status":            row.get("status"),
            "gstin":             row.get("gstin_vendor"),
            "payment_terms":     row.get("payment_terms"),
            "file_path":         row.get("file_path") or "",
        }
        raw_text = row.get("raw_text") or ""

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
