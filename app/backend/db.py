"""Database module using databricks-sql-connector."""
import os
from typing import Any
from databricks import sql as dbsql
from backend.config import get_workspace_host, get_token, WAREHOUSE_ID, full_table


def get_connection():
    """Create a new Databricks SQL connection."""
    host = get_workspace_host().replace("https://", "")
    token = get_token()
    return dbsql.connect(
        server_hostname=host,
        http_path=f"/sql/1.0/warehouses/{WAREHOUSE_ID}",
        access_token=token,
    )


def query(sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    """Execute a SQL query and return rows as dicts."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, parameters=params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


# ─── P2P Queries ─────────────────────────────────────────────

def get_invoices(limit: int = 200) -> list[dict]:
    """Get invoices for the streaming feed."""
    return query(f"""
        SELECT invoice_id, invoice_number, vendor_name, vendor_category,
               invoice_date, due_date, invoice_amount, tax_amount,
               invoice_total_inr, match_status, has_po_ref, is_overdue,
               aging_days, aging_bucket, invoice_status, po_id, gstin_vendor
        FROM {full_table('gold_fact_invoices')}
        ORDER BY invoice_date DESC
        LIMIT {limit}
    """)


def get_p2p_metrics() -> dict:
    """Get AP/P2P KPI metrics."""
    rows = query(f"""
        SELECT
            COUNT(*) as total_invoices,
            SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) as matched,
            SUM(CASE WHEN match_status = 'AMOUNT_MISMATCH' THEN 1 ELSE 0 END) as amount_mismatch,
            SUM(CASE WHEN match_status = 'NO_PO_REFERENCE' THEN 1 ELSE 0 END) as no_po,
            SUM(CASE WHEN match_status = 'TWO_WAY_MATCHED' THEN 1 ELSE 0 END) as two_way,
            SUM(CASE WHEN is_overdue = true THEN 1 ELSE 0 END) as overdue_count,
            SUM(invoice_total_inr) as total_amount,
            SUM(CASE WHEN is_overdue = true THEN invoice_total_inr ELSE 0 END) as overdue_amount,
            AVG(CASE WHEN aging_days > 0 THEN aging_days END) as avg_aging_days,
            ROUND(SUM(CASE WHEN match_status = 'THREE_WAY_MATCHED' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) as touchless_rate
        FROM {full_table('gold_fact_invoices')}
    """)
    if rows:
        r = rows[0]
        # Count exceptions
        exceptions = (r.get("amount_mismatch") or 0) + (r.get("no_po") or 0)
        return {
            "total_invoices": r.get("total_invoices", 0),
            "matched": r.get("matched", 0),
            "two_way": r.get("two_way", 0),
            "amount_mismatch": r.get("amount_mismatch", 0),
            "no_po": r.get("no_po", 0),
            "exceptions": exceptions,
            "overdue_count": r.get("overdue_count", 0),
            "total_amount": float(r.get("total_amount", 0) or 0),
            "overdue_amount": float(r.get("overdue_amount", 0) or 0),
            "avg_aging_days": round(float(r.get("avg_aging_days", 0) or 0), 1),
            "touchless_rate": float(r.get("touchless_rate", 0) or 0),
        }
    return {}


def get_payment_run_data() -> dict:
    """Get payment run summary."""
    rows = query(f"""
        SELECT
            COUNT(*) as total_payments,
            SUM(payment_amount_inr) as total_paid,
            AVG(days_to_pay) as avg_dpo,
            SUM(CASE WHEN payment_timing = 'EARLY' THEN 1 ELSE 0 END) as early_payments,
            SUM(CASE WHEN payment_timing = 'ON_TIME' THEN 1 ELSE 0 END) as on_time_payments,
            SUM(CASE WHEN payment_timing = 'LATE' THEN 1 ELSE 0 END) as late_payments
        FROM {full_table('gold_fact_payments')}
    """)
    if rows:
        r = rows[0]
        return {
            "total_payments": r.get("total_payments", 0),
            "total_paid": float(r.get("total_paid", 0) or 0),
            "avg_dpo": round(float(r.get("avg_dpo", 0) or 0), 1),
            "early_payments": r.get("early_payments", 0),
            "on_time_payments": r.get("on_time_payments", 0),
            "late_payments": r.get("late_payments", 0),
        }
    return {}


# ─── O2C Queries ─────────────────────────────────────────────

def get_collections(limit: int = 200) -> list[dict]:
    """Get collections for streaming feed."""
    return query(f"""
        SELECT o2c_invoice_id, invoice_number, customer_name, segment,
               industry, invoice_date, due_date, invoice_total_inr,
               amount_collected_inr, balance_outstanding, invoice_status,
               aging_bucket, days_outstanding, days_overdue, is_fully_collected,
               payment_method, region
        FROM {full_table('gold_fact_collections')}
        ORDER BY days_outstanding DESC
        LIMIT {limit}
    """)


def get_o2c_metrics() -> dict:
    """Get AR/O2C KPI metrics."""
    # Aging breakdown
    aging = query(f"""
        SELECT
            aging_bucket,
            COUNT(*) as count,
            SUM(balance_outstanding) as amount
        FROM {full_table('gold_fact_collections')}
        GROUP BY aging_bucket
        ORDER BY
            CASE aging_bucket
                WHEN '0-30 days' THEN 1
                WHEN '31-60 days' THEN 2
                WHEN '61-90 days' THEN 3
                WHEN '90+ days' THEN 4
                ELSE 5
            END
    """)

    totals = query(f"""
        SELECT
            SUM(balance_outstanding) as total_outstanding,
            AVG(days_outstanding) as avg_dso,
            COUNT(*) as total_invoices,
            SUM(CASE WHEN is_fully_collected = true THEN 1 ELSE 0 END) as collected,
            SUM(amount_collected_inr) as total_collected,
            SUM(invoice_total_inr) as total_billed,
            SUM(CASE WHEN days_overdue > 0 THEN 1 ELSE 0 END) as overdue_count
        FROM {full_table('gold_fact_collections')}
    """)

    customers_at_risk = query(f"""
        SELECT customer_name, credit_limit, outstanding_ar_inr,
               credit_utilization_pct, overdue_invoices, dso
        FROM {full_table('gold_dim_customer')}
        WHERE credit_utilization_pct > 80
        ORDER BY credit_utilization_pct DESC
        LIMIT 10
    """)

    t = totals[0] if totals else {}
    total_billed = float(t.get("total_billed", 1) or 1)
    total_collected = float(t.get("total_collected", 0) or 0)
    cei = round((total_collected / total_billed) * 100, 1) if total_billed else 0

    return {
        "total_outstanding": float(t.get("total_outstanding", 0) or 0),
        "avg_dso": round(float(t.get("avg_dso", 0) or 0), 1),
        "total_invoices": t.get("total_invoices", 0),
        "collected": t.get("collected", 0),
        "total_collected": total_collected,
        "overdue_count": t.get("overdue_count", 0),
        "cei": cei,
        "aging_buckets": [
            {"bucket": r["aging_bucket"], "count": r["count"], "amount": float(r["amount"] or 0)}
            for r in aging
        ],
        "customers_at_risk": [
            {
                "name": c["customer_name"],
                "credit_limit": float(c["credit_limit"] or 0),
                "outstanding": float(c["outstanding_ar_inr"] or 0),
                "utilization": float(c["credit_utilization_pct"] or 0),
                "overdue": c["overdue_invoices"],
                "dso": float(c["dso"] or 0),
            }
            for c in customers_at_risk
        ],
    }


# ─── R2R Queries ─────────────────────────────────────────────

def get_journal_entries(limit: int = 200) -> list[dict]:
    """Get journal entries for streaming feed."""
    return query(f"""
        SELECT je_id, je_number, gl_line_number, account_code, account_name,
               account_type, cost_center_name, department, je_date, period,
               je_type, status, posted_by, debit_inr, credit_inr,
               net_amount_inr, gl_description
        FROM {full_table('gold_fact_gl')}
        ORDER BY je_date DESC, je_id, gl_line_number
        LIMIT {limit}
    """)


def get_r2r_metrics() -> dict:
    """Get GL/R2R KPI metrics."""
    je_stats = query(f"""
        SELECT
            COUNT(DISTINCT je_id) as total_jes,
            COUNT(*) as total_lines,
            SUM(debit_inr) as total_debits,
            SUM(credit_inr) as total_credits,
            COUNT(DISTINCT CASE WHEN status = 'POSTED' THEN je_id END) as posted,
            COUNT(DISTINCT CASE WHEN status = 'PENDING' THEN je_id END) as pending,
            COUNT(DISTINCT je_type) as je_types
        FROM {full_table('gold_fact_gl')}
    """)

    trial_balance = query(f"""
        SELECT account_code, account_name, account_type, account_subtype,
               closing_balance_inr, balance_type, period_debit, period_credit,
               period_net, transaction_count
        FROM {full_table('gold_fact_trial_balance')}
        WHERE period = (SELECT MAX(period) FROM {full_table('gold_fact_trial_balance')})
        ORDER BY account_code
    """)

    tb_totals = query(f"""
        SELECT
            SUM(period_debit) as total_debit,
            SUM(period_credit) as total_credit,
            ABS(SUM(period_debit) - SUM(period_credit)) as imbalance
        FROM {full_table('gold_fact_trial_balance')}
        WHERE period = (SELECT MAX(period) FROM {full_table('gold_fact_trial_balance')})
    """)

    j = je_stats[0] if je_stats else {}
    tb = tb_totals[0] if tb_totals else {}

    return {
        "total_jes": j.get("total_jes", 0),
        "total_lines": j.get("total_lines", 0),
        "total_debits": float(j.get("total_debits", 0) or 0),
        "total_credits": float(j.get("total_credits", 0) or 0),
        "posted": j.get("posted", 0),
        "pending": j.get("pending", 0),
        "tb_total_debit": float(tb.get("total_debit", 0) or 0),
        "tb_total_credit": float(tb.get("total_credit", 0) or 0),
        "tb_imbalance": float(tb.get("imbalance", 0) or 0),
        "is_balanced": float(tb.get("imbalance", 999) or 0) < 1.0,
        "trial_balance": [
            {
                "account_code": r["account_code"],
                "account_name": r["account_name"],
                "account_type": r["account_type"],
                "debit": float(r["period_debit"] or 0),
                "credit": float(r["period_credit"] or 0),
                "balance": float(r["closing_balance_inr"] or 0),
                "balance_type": r["balance_type"],
                "transactions": r["transaction_count"],
            }
            for r in trial_balance
        ],
    }
