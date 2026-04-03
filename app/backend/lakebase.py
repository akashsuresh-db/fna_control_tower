"""Lakebase (Postgres) connection for operational state storage.

Falls back to in-memory storage when Lakebase is not configured,
so the app works in demo mode without a database.

Token refresh: Uses databricks-sdk generate_database_credential() to get
a fresh OAuth token on every connection, preventing the ~1-hour expiry
that causes silent fallback to in-memory (demo) mode.
"""
import os
import json
import datetime
from typing import Any

# Track whether we're in demo mode
_demo_mode = False
_in_memory_approvals: list[dict] = []
_in_memory_call_logs: list[dict] = []
_in_memory_chat_history: list[dict] = []


def _fresh_token() -> str:
    """
    Generate a short-lived database credential via the Databricks SDK.
    This token is valid for ~1 hour; we generate a new one per connection
    so long-running apps never hit an expired-credentials error.

    Falls back to the static PGPASSWORD env var if the SDK call fails
    (e.g. running locally without app credentials).
    """
    instance_name = os.environ.get("LAKEBASE_INSTANCE_NAME", "finance-ops-db")
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()  # auto-configures from app SP in Databricks Apps runtime
        cred = w.database.generate_database_credential(instance_names=[instance_name])
        if cred and cred.token:
            return cred.token
    except Exception as e:
        print(f"SDK token refresh failed, falling back to PGPASSWORD: {e}")
    return os.environ.get("PGPASSWORD") or os.environ.get("LAKEBASE_PASSWORD", "")


def _get_conn():
    """Get a psycopg2 connection to Lakebase with a freshly generated token."""
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get("PGHOST") or os.environ.get("LAKEBASE_HOST"),
        port=int(os.environ.get("PGPORT") or os.environ.get("LAKEBASE_PORT", "5432")),
        database=os.environ.get("PGDATABASE") or os.environ.get("LAKEBASE_DATABASE", "finance_ops"),
        user=os.environ.get("PGUSER") or os.environ.get("LAKEBASE_USER"),
        password=_fresh_token(),
        sslmode=os.environ.get("PGSSLMODE", "require"),
    )


def init_schema():
    """Create tables if they don't exist. Falls back to demo mode."""
    global _demo_mode

    host = os.environ.get("PGHOST") or os.environ.get("LAKEBASE_HOST")
    user = os.environ.get("PGUSER") or os.environ.get("LAKEBASE_USER")
    if not host or not user:
        print("Lakebase not configured (PGHOST/PGUSER missing) - using in-memory demo mode")
        _demo_mode = True
        return

    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                # Try to create tables — may fail if SP lacks CREATE privilege,
                # but tables may already exist (pre-created by admin). That's fine.
                try:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS ap_approvals (
                            id SERIAL PRIMARY KEY,
                            invoice_id VARCHAR(50),
                            action VARCHAR(20),
                            reason TEXT,
                            approved_by VARCHAR(100),
                            approved_at TIMESTAMP DEFAULT NOW()
                        );
                        CREATE TABLE IF NOT EXISTS ar_call_logs (
                            id SERIAL PRIMARY KEY,
                            customer_id VARCHAR(50),
                            customer_name VARCHAR(200),
                            outcome VARCHAR(50),
                            ptp_date DATE,
                            notes TEXT,
                            logged_by VARCHAR(100),
                            logged_at TIMESTAMP DEFAULT NOW()
                        );
                        CREATE TABLE IF NOT EXISTS chat_history (
                            id SERIAL PRIMARY KEY,
                            session_id VARCHAR(100),
                            user_email VARCHAR(200),
                            active_tab VARCHAR(50),
                            question TEXT,
                            genie_space VARCHAR(50),
                            answer TEXT,
                            sql_used TEXT,
                            routing_info JSONB,
                            previous_response_id VARCHAR(200),
                            asked_at TIMESTAMP DEFAULT NOW()
                        );
                        CREATE INDEX IF NOT EXISTS idx_chat_session
                            ON chat_history(session_id, asked_at ASC);
                        CREATE INDEX IF NOT EXISTS idx_chat_user
                            ON chat_history(user_email, asked_at DESC);
                    """)
                    cur.execute("""
                        ALTER TABLE chat_history
                            ADD COLUMN IF NOT EXISTS routing_info JSONB;
                        ALTER TABLE chat_history
                            ADD COLUMN IF NOT EXISTS previous_response_id VARCHAR(200);
                    """)
                except Exception as ddl_err:
                    # DDL failed (e.g. no CREATE privilege) — verify tables exist
                    conn.rollback()
                    cur.execute("SELECT COUNT(*) FROM chat_history LIMIT 1")
                    print(f"DDL skipped (tables pre-created): {ddl_err}")
        conn.close()
        print("Lakebase schema ready")
    except Exception as e:
        print(f"Lakebase schema init failed, using demo mode: {e}")
        _demo_mode = True


# ─── Write operations ────────────────────────────────────────


def log_approval(invoice_id: str, action: str, reason: str, user: str):
    """Log an AP approval/rejection action."""
    record = {
        "invoice_id": invoice_id,
        "action": action,
        "reason": reason,
        "approved_by": user,
        "approved_at": datetime.datetime.now().isoformat(),
    }
    if _demo_mode:
        _in_memory_approvals.insert(0, record)
        return
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ap_approvals (invoice_id, action, reason, approved_by) VALUES (%s, %s, %s, %s)",
                    (invoice_id, action, reason, user),
                )
    finally:
        conn.close()


def log_call(customer_id: str, customer_name: str, outcome: str, ptp_date: str | None, notes: str, user: str):
    """Log an AR collection call."""
    record = {
        "customer_id": customer_id,
        "customer_name": customer_name,
        "outcome": outcome,
        "ptp_date": ptp_date,
        "notes": notes,
        "logged_by": user,
        "logged_at": datetime.datetime.now().isoformat(),
    }
    if _demo_mode:
        _in_memory_call_logs.insert(0, record)
        return
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ar_call_logs (customer_id, customer_name, outcome, ptp_date, notes, logged_by) VALUES (%s, %s, %s, %s, %s, %s)",
                    (customer_id, customer_name, outcome, ptp_date, notes, user),
                )
    finally:
        conn.close()


def log_chat(
    session_id: str,
    user_email: str,
    tab: str,
    question: str,
    space: str,
    answer: str,
    sql: str,
    routing_info: dict | None = None,
    previous_response_id: str | None = None,
):
    """Log a chat interaction."""
    record = {
        "session_id": session_id,
        "user_email": user_email,
        "active_tab": tab,
        "question": question,
        "genie_space": space,
        "answer": answer,
        "sql_used": sql,
        "routing_info": routing_info,
        "previous_response_id": previous_response_id,
        "asked_at": datetime.datetime.now().isoformat(),
    }
    if _demo_mode:
        _in_memory_chat_history.append(record)
        return
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO chat_history
                       (session_id, user_email, active_tab, question, genie_space,
                        answer, sql_used, routing_info, previous_response_id)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (session_id, user_email, tab, question, space, answer, sql,
                     json.dumps(routing_info) if routing_info else None,
                     previous_response_id),
                )
    finally:
        conn.close()


# ─── Read operations ─────────────────────────────────────────


def get_session_messages(session_id: str, limit: int = 10) -> list[dict]:
    """Return prior turns for a session as [{role, content}, ...] pairs.

    Each stored row (question + answer) expands to two messages:
      {role: "user", content: question}
      {role: "assistant", content: answer}
    Returns up to `limit` Q+A pairs (2*limit messages total), oldest first.
    """
    if _demo_mode:
        rows = [r for r in _in_memory_chat_history if r["session_id"] == session_id]
        rows = rows[-limit:]
    else:
        try:
            conn = _get_conn()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT question, answer FROM chat_history
                           WHERE session_id = %s
                           ORDER BY asked_at ASC
                           LIMIT %s""",
                        (session_id, limit),
                    )
                    rows = [{"question": r[0], "answer": r[1]} for r in cur.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            print(f"get_session_messages failed: {e}")
            return []

    messages = []
    for row in rows:
        if row.get("question"):
            messages.append({"role": "user", "content": row["question"]})
        if row.get("answer"):
            messages.append({"role": "assistant", "content": row["answer"]})
    return messages


def get_user_sessions(user_email: str, limit: int = 20) -> list[dict]:
    """Return session cards for a user, most recent first."""
    if _demo_mode:
        seen: dict[str, dict] = {}
        for row in _in_memory_chat_history:
            if row["user_email"] != user_email:
                continue
            sid = row["session_id"]
            if sid not in seen:
                seen[sid] = {
                    "session_id": sid,
                    "first_question": row["question"],
                    "tab": row["active_tab"],
                    "started_at": row["asked_at"],
                    "last_active": row["asked_at"],
                    "message_count": 1,
                }
            else:
                seen[sid]["last_active"] = row["asked_at"]
                seen[sid]["message_count"] += 1
        sessions = sorted(seen.values(), key=lambda x: x["last_active"], reverse=True)
        return sessions[:limit]

    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT
                         h.session_id,
                         h.question        AS first_question,
                         h.active_tab      AS tab,
                         h.asked_at        AS started_at,
                         agg.last_active,
                         agg.message_count
                       FROM chat_history h
                       JOIN (
                         SELECT session_id,
                                MAX(asked_at) AS last_active,
                                COUNT(*)      AS message_count
                         FROM chat_history
                         WHERE user_email = %s
                         GROUP BY session_id
                       ) agg ON agg.session_id = h.session_id
                       WHERE h.user_email = %s
                         AND h.asked_at = (
                               SELECT MIN(asked_at) FROM chat_history h2
                               WHERE h2.session_id = h.session_id
                             )
                       ORDER BY agg.last_active DESC
                       LIMIT %s""",
                    (user_email, user_email, limit),
                )
                cols = ["session_id", "first_question", "tab", "started_at", "last_active", "message_count"]
                rows = [dict(zip(cols, r)) for r in cur.fetchall()]
                # Serialize timestamps
                for row in rows:
                    for k in ("started_at", "last_active"):
                        if hasattr(row[k], "isoformat"):
                            row[k] = row[k].isoformat()
                return rows
        finally:
            conn.close()
    except Exception as e:
        print(f"get_user_sessions failed: {e}")
        return []


def get_session_detail(session_id: str, user_email: str) -> dict:
    """Return full message history + last previous_response_id for a session."""
    if _demo_mode:
        rows = [
            r for r in _in_memory_chat_history
            if r["session_id"] == session_id and r["user_email"] == user_email
        ]
        messages = [
            {
                "role": role,
                "content": r["question"] if role == "user" else r["answer"],
                "sql": r.get("sql_used") if role == "assistant" else None,
                "genie_space": r.get("genie_space") if role == "assistant" else None,
                "routing_info": r.get("routing_info") if role == "assistant" else None,
                "asked_at": r["asked_at"],
            }
            for r in rows
            for role in ("user", "assistant")
        ]
        last_prev_id = next(
            (r["previous_response_id"] for r in reversed(rows) if r.get("previous_response_id")), None
        )
        return {"messages": messages, "previous_response_id": last_prev_id}

    try:
        conn = _get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT question, answer, sql_used, genie_space, routing_info,
                              previous_response_id, asked_at
                       FROM chat_history
                       WHERE session_id = %s AND user_email = %s
                       ORDER BY asked_at ASC""",
                    (session_id, user_email),
                )
                results = []
                last_prev_id = None
                for question, answer, sql_used, genie_space, routing_info, prev_resp_id, asked_at in cur.fetchall():
                    ts = asked_at.isoformat() if hasattr(asked_at, "isoformat") else str(asked_at)
                    if prev_resp_id:
                        last_prev_id = prev_resp_id
                    results.append({"role": "user", "content": question,
                                    "sql": None, "genie_space": None, "routing_info": None, "asked_at": ts})
                    results.append({"role": "assistant", "content": answer,
                                    "sql": sql_used, "genie_space": genie_space,
                                    "routing_info": routing_info, "asked_at": ts})
                return {"messages": results, "previous_response_id": last_prev_id}
        finally:
            conn.close()
    except Exception as e:
        print(f"get_session_detail failed: {e}")
        return {"messages": [], "previous_response_id": None}


def get_user_approvals(user: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent approvals by a user."""
    if _demo_mode:
        return [r for r in _in_memory_approvals if r["approved_by"] == user][:limit]
    try:
        import psycopg2.extras
        conn = _get_conn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM ap_approvals WHERE approved_by = %s ORDER BY approved_at DESC LIMIT %s",
                    (user, limit),
                )
                return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
    except Exception:
        return [r for r in _in_memory_approvals if r["approved_by"] == user][:limit]
