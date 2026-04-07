"""Database module using databricks-sql-connector."""
import os
from typing import Any
from databricks import sql as dbsql
from backend.config import get_workspace_host, get_token, WAREHOUSE_ID, full_table

# Track demo mode
_demo_mode = False

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
    """Execute a SQL query and return rows as dicts. Falls back to demo mode on connection error."""
    global _demo_mode
    try:
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(sql, parameters=params)
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            return [dict(zip(columns, row)) for row in rows]
        finally:
            conn.close()
    except Exception as e:
        print(f"Database query failed, using demo mode: {e}")
        _demo_mode = True
        return []


# ─── P2P Queries ─────────────────────────────────────────────

def _get_demo_invoices(limit: int = 200) -> list[dict]:
    """Return demo invoices."""
    invoices = [
        {"invoice_id": "INV001001", "invoice_number": "VINV-2025-50101", "vendor_name": "TechSupply Corp", "vendor_category": "IT Equipment", "invoice_date": "2025-03-01", "due_date": "2025-04-01", "invoice_amount": 450000, "tax_amount": 81000, "invoice_total_inr": 531000, "match_status": "THREE_WAY_MATCHED", "has_po_ref": True, "is_overdue": False, "aging_days": 7, "aging_bucket": "0-30 days", "invoice_status": "PENDING", "po_id": "PO-2025-1001", "gstin_vendor": "29AABCT1234H1Z2"},
        {"invoice_id": "INV001002", "invoice_number": "VINV-2025-50102", "vendor_name": "Office Solutions", "vendor_category": "Office Supplies", "invoice_date": "2025-03-02", "due_date": "2025-04-02", "invoice_amount": 125000, "tax_amount": 22500, "invoice_total_inr": 147500, "match_status": "AMOUNT_MISMATCH", "has_po_ref": True, "is_overdue": False, "aging_days": 6, "aging_bucket": "0-30 days", "invoice_status": "PENDING", "po_id": "PO-2025-1002", "gstin_vendor": "28AACCT5678H2Z3"},
        {"invoice_id": "INV001003", "invoice_number": "VINV-2025-50103", "vendor_name": "Global Services", "vendor_category": "Consulting", "invoice_date": "2025-02-15", "due_date": "2025-03-15", "invoice_amount": 850000, "tax_amount": 0, "invoice_total_inr": 850000, "match_status": "NO_PO_REFERENCE", "has_po_ref": False, "is_overdue": True, "aging_days": 23, "aging_bucket": "0-30 days", "invoice_status": "PENDING", "po_id": None, "gstin_vendor": None},
        {"invoice_id": "INV001004", "invoice_number": "VINV-2025-50104", "vendor_name": "Logistics Plus", "vendor_category": "Transportation", "invoice_date": "2025-01-10", "due_date": "2025-02-10", "invoice_amount": 275000, "tax_amount": 49500, "invoice_total_inr": 324500, "match_status": "THREE_WAY_MATCHED", "has_po_ref": True, "is_overdue": True, "aging_days": 56, "aging_bucket": "31-60 days", "invoice_status": "PENDING", "po_id": "PO-2025-1004", "gstin_vendor": "18AABCR1234K2Z0"},
        {"invoice_id": "INV001005", "invoice_number": "VINV-2025-50105", "vendor_name": "Raw Materials Ltd", "vendor_category": "Raw Materials", "invoice_date": "2025-02-28", "due_date": "2025-03-28", "invoice_amount": 1200000, "tax_amount": 216000, "invoice_total_inr": 1416000, "match_status": "THREE_WAY_MATCHED", "has_po_ref": True, "is_overdue": False, "aging_days": 10, "aging_bucket": "0-30 days", "invoice_status": "APPROVED", "po_id": "PO-2025-1005", "gstin_vendor": "27AABCT8901H3Z1"},
        {"invoice_id": "INV001006", "invoice_number": "VINV-2025-50106", "vendor_name": "Equipment Rental", "vendor_category": "Equipment", "invoice_date": "2025-03-05", "due_date": "2025-04-05", "invoice_amount": 350000, "tax_amount": 63000, "invoice_total_inr": 413000, "match_status": "TWO_WAY_MATCHED", "has_po_ref": True, "is_overdue": False, "aging_days": 2, "aging_bucket": "0-30 days", "invoice_status": "PENDING", "po_id": "PO-2025-1006", "gstin_vendor": "22AABCT1234H4Z2"},
    ]
    return invoices[:limit]

def get_invoices(limit: int = 200) -> list[dict]:
    """Get invoices for the streaming feed."""
    if _demo_mode:
        return _get_demo_invoices(limit)

    return query(f"""
        SELECT invoice_id, invoice_number, vendor_name, vendor_category,
               invoice_date, due_date, invoice_amount, tax_amount,
               invoice_total_inr, match_status, has_po_ref, is_overdue,
               aging_days, aging_bucket, invoice_status, po_id, gstin_vendor
        FROM {full_table('gold_fact_invoices')}
        ORDER BY invoice_date DESC
        LIMIT {limit}
    """) or _get_demo_invoices(limit)


def _get_p2p_demo_metrics() -> dict:
    """Return demo P2P metrics."""
    return {
        "total_invoices": 142,
        "matched": 118,
        "two_way": 15,
        "amount_mismatch": 5,
        "no_po": 4,
        "exceptions": 9,
        "overdue_count": 8,
        "total_amount": 47_500_000,
        "overdue_amount": 2_100_000,
        "avg_aging_days": 21.5,
        "touchless_rate": 83.1,
    }

def get_p2p_metrics() -> dict:
    """Get AP/P2P KPI metrics."""
    if _demo_mode:
        return _get_p2p_demo_metrics()

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
    return _get_p2p_demo_metrics()


def _get_payment_run_demo_data() -> dict:
    """Return demo payment run data."""
    return {
        "total_payments": 89,
        "total_paid": 32_750_000,
        "avg_dpo": 42.3,
        "early_payments": 12,
        "on_time_payments": 65,
        "late_payments": 12,
    }

def get_payment_run_data() -> dict:
    """Get payment run summary."""
    if _demo_mode:
        return _get_payment_run_demo_data()

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
    return _get_payment_run_demo_data()


# ─── O2C Queries ─────────────────────────────────────────────

def _get_demo_collections(limit: int = 200) -> list[dict]:
    """Return demo collections."""
    collections = [
        {"o2c_invoice_id": "O2C001001", "invoice_number": "INV-2025-001", "customer_name": "Tech Corp Ltd", "segment": "Enterprise", "industry": "IT", "invoice_date": "2025-02-15", "due_date": "2025-03-15", "invoice_total_inr": 850000, "amount_collected_inr": 0, "balance_outstanding": 850000, "invoice_status": "OVERDUE", "aging_bucket": "61-90 days", "days_outstanding": 53, "days_overdue": 23, "is_fully_collected": False, "payment_method": None, "region": "North"},
        {"o2c_invoice_id": "O2C001002", "invoice_number": "INV-2025-002", "customer_name": "Global Industries", "segment": "Mid-market", "industry": "Manufacturing", "invoice_date": "2025-01-20", "due_date": "2025-02-20", "invoice_total_inr": 1200000, "amount_collected_inr": 500000, "balance_outstanding": 700000, "invoice_status": "PARTIAL", "aging_bucket": "90+ days", "days_outstanding": 76, "days_overdue": 45, "is_fully_collected": False, "payment_method": "Bank Transfer", "region": "South"},
        {"o2c_invoice_id": "O2C001003", "invoice_number": "INV-2025-003", "customer_name": "Express Logistics", "segment": "SMB", "industry": "Transportation", "invoice_date": "2025-02-25", "due_date": "2025-03-25", "invoice_total_inr": 425000, "amount_collected_inr": 425000, "balance_outstanding": 0, "invoice_status": "COLLECTED", "aging_bucket": "0-30 days", "days_outstanding": 13, "days_overdue": 0, "is_fully_collected": True, "payment_method": "Credit Card", "region": "East"},
        {"o2c_invoice_id": "O2C001004", "invoice_number": "INV-2025-004", "customer_name": "Retail Partners", "segment": "SMB", "industry": "Retail", "invoice_date": "2025-02-28", "due_date": "2025-03-28", "invoice_total_inr": 580000, "amount_collected_inr": 580000, "balance_outstanding": 0, "invoice_status": "COLLECTED", "aging_bucket": "0-30 days", "days_outstanding": 10, "days_overdue": 0, "is_fully_collected": True, "payment_method": "ACH", "region": "West"},
        {"o2c_invoice_id": "O2C001005", "invoice_number": "INV-2025-005", "customer_name": "Healthcare Group", "segment": "Enterprise", "industry": "Healthcare", "invoice_date": "2025-03-01", "due_date": "2025-04-01", "invoice_total_inr": 950000, "amount_collected_inr": 0, "balance_outstanding": 950000, "invoice_status": "PENDING", "aging_bucket": "0-30 days", "days_outstanding": 7, "days_overdue": 0, "is_fully_collected": False, "payment_method": None, "region": "North"},
    ]
    return collections[:limit]

def get_collections(limit: int = 200) -> list[dict]:
    """Get collections for streaming feed."""
    if _demo_mode:
        return _get_demo_collections(limit)

    return query(f"""
        SELECT o2c_invoice_id, invoice_number, customer_name, segment,
               industry, invoice_date, due_date, invoice_total_inr,
               amount_collected_inr, balance_outstanding, invoice_status,
               aging_bucket, days_outstanding, days_overdue, is_fully_collected,
               payment_method, region
        FROM {full_table('gold_fact_collections')}
        ORDER BY days_outstanding DESC
        LIMIT {limit}
    """) or _get_demo_collections(limit)


def _get_o2c_demo_metrics() -> dict:
    """Return demo O2C metrics."""
    return {
        "total_outstanding": 28_500_000,
        "avg_dso": 38.2,
        "total_invoices": 156,
        "collected": 132,
        "total_collected": 76_400_000,
        "overdue_count": 24,
        "cei": 89.5,
        "aging_buckets": [
            {"bucket": "0-30 days", "count": 98, "amount": 14_700_000},
            {"bucket": "31-60 days", "count": 35, "amount": 8_900_000},
            {"bucket": "61-90 days", "count": 18, "amount": 3_200_000},
            {"bucket": "90+ days", "count": 5, "amount": 1_700_000},
        ],
        "customers_at_risk": [
            {"name": "Tech Corp Ltd", "credit_limit": 5_000_000, "outstanding": 4_200_000, "utilization": 84.0, "overdue": 3, "dso": 45.2},
            {"name": "Global Industries", "credit_limit": 3_000_000, "outstanding": 2_850_000, "utilization": 95.0, "overdue": 7, "dso": 62.1},
            {"name": "Express Logistics", "credit_limit": 2_000_000, "outstanding": 1_950_000, "utilization": 97.5, "overdue": 2, "dso": 38.5},
        ],
    }

def get_o2c_metrics() -> dict:
    """Get AR/O2C KPI metrics."""
    if _demo_mode:
        return _get_o2c_demo_metrics()

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
    } if aging and totals else _get_o2c_demo_metrics()


# ─── R2R Queries ─────────────────────────────────────────────

def _get_demo_journal_entries(limit: int = 200) -> list[dict]:
    """Return demo journal entries."""
    entries = [
        {"je_id": "JE001", "je_number": "JE-2025-001", "gl_line_number": 1, "account_code": "1200", "account_name": "Accounts Receivable", "account_type": "Asset", "cost_center_name": "Sales", "department": "Revenue", "je_date": "2025-03-05", "period": "2025-03", "je_type": "Revenue", "status": "POSTED", "posted_by": "Vikram", "debit_inr": 850000, "credit_inr": 0, "net_amount_inr": 850000, "gl_description": "Sales invoice INV-2025-001 to Tech Corp Ltd"},
        {"je_id": "JE001", "je_number": "JE-2025-001", "gl_line_number": 2, "account_code": "4100", "account_name": "Revenue", "account_type": "Revenue", "cost_center_name": "Sales", "department": "Revenue", "je_date": "2025-03-05", "period": "2025-03", "je_type": "Revenue", "status": "POSTED", "posted_by": "Vikram", "debit_inr": 0, "credit_inr": 850000, "net_amount_inr": -850000, "gl_description": "Sales invoice INV-2025-001 to Tech Corp Ltd"},
        {"je_id": "JE002", "je_number": "JE-2025-002", "gl_line_number": 1, "account_code": "1100", "account_name": "Cash", "account_type": "Asset", "cost_center_name": "Treasury", "department": "Finance", "je_date": "2025-03-04", "period": "2025-03", "je_type": "Payment", "status": "POSTED", "posted_by": "Vikram", "debit_inr": 500000, "credit_inr": 0, "net_amount_inr": 500000, "gl_description": "Payment received from Global Industries"},
        {"je_id": "JE002", "je_number": "JE-2025-002", "gl_line_number": 2, "account_code": "1200", "account_name": "Accounts Receivable", "account_type": "Asset", "cost_center_name": "Treasury", "department": "Finance", "je_date": "2025-03-04", "period": "2025-03", "je_type": "Payment", "status": "POSTED", "posted_by": "Vikram", "debit_inr": 0, "credit_inr": 500000, "net_amount_inr": -500000, "gl_description": "Payment received from Global Industries"},
        {"je_id": "JE003", "je_number": "JE-2025-003", "gl_line_number": 1, "account_code": "5100", "account_name": "COGS", "account_type": "Expense", "cost_center_name": "Operations", "department": "Cost Center", "je_date": "2025-03-01", "period": "2025-03", "je_type": "Accrual", "status": "PENDING", "posted_by": "Akash", "debit_inr": 125000, "credit_inr": 0, "net_amount_inr": 125000, "gl_description": "Monthly accrual for raw materials"},
        {"je_id": "JE003", "je_number": "JE-2025-003", "gl_line_number": 2, "account_code": "2100", "account_name": "Accounts Payable", "account_type": "Liability", "cost_center_name": "Operations", "department": "Cost Center", "je_date": "2025-03-01", "period": "2025-03", "je_type": "Accrual", "status": "PENDING", "posted_by": "Akash", "debit_inr": 0, "credit_inr": 125000, "net_amount_inr": -125000, "gl_description": "Monthly accrual for raw materials"},
    ]
    return entries[:limit]

def get_journal_entries(limit: int = 200) -> list[dict]:
    """Get journal entries for streaming feed."""
    if _demo_mode:
        return _get_demo_journal_entries(limit)

    return query(f"""
        SELECT je_id, je_number, gl_line_number, account_code, account_name,
               account_type, cost_center_name, department, je_date, period,
               je_type, status, posted_by, debit_inr, credit_inr,
               net_amount_inr, gl_description
        FROM {full_table('gold_fact_gl')}
        ORDER BY je_date DESC, je_id, gl_line_number
        LIMIT {limit}
    """) or _get_demo_journal_entries(limit)


def _get_r2r_demo_metrics() -> dict:
    """Return demo R2R metrics."""
    return {
        "total_jes": 247,
        "total_lines": 1248,
        "total_debits": 125_400_000,
        "total_credits": 125_400_000,
        "posted": 201,
        "pending": 46,
        "tb_total_debit": 385_250_000,
        "tb_total_credit": 385_250_000,
        "tb_imbalance": 0.0,
        "is_balanced": True,
        "trial_balance": [
            {"account_code": "1100", "account_name": "Cash", "account_type": "Asset", "debit": 8_500_000, "credit": 0, "balance": 8_500_000, "balance_type": "Debit", "transactions": 342},
            {"account_code": "1200", "account_name": "Accounts Receivable", "account_type": "Asset", "debit": 28_500_000, "credit": 0, "balance": 28_500_000, "balance_type": "Debit", "transactions": 156},
            {"account_code": "1500", "account_name": "Fixed Assets", "account_type": "Asset", "debit": 120_000_000, "credit": 0, "balance": 120_000_000, "balance_type": "Debit", "transactions": 8},
            {"account_code": "2100", "account_name": "Accounts Payable", "account_type": "Liability", "debit": 0, "credit": 14_700_000, "balance": 14_700_000, "balance_type": "Credit", "transactions": 142},
            {"account_code": "2500", "account_name": "Loan Payable", "account_type": "Liability", "debit": 0, "credit": 50_000_000, "balance": 50_000_000, "balance_type": "Credit", "transactions": 12},
            {"account_code": "3100", "account_name": "Capital Stock", "account_type": "Equity", "debit": 0, "credit": 200_000_000, "balance": 200_000_000, "balance_type": "Credit", "transactions": 2},
            {"account_code": "4100", "account_name": "Revenue", "account_type": "Revenue", "debit": 0, "credit": 125_400_000, "balance": 125_400_000, "balance_type": "Credit", "transactions": 156},
            {"account_code": "5100", "account_name": "COGS", "account_type": "Expense", "debit": 75_000_000, "credit": 0, "balance": 75_000_000, "balance_type": "Debit", "transactions": 142},
            {"account_code": "5500", "account_name": "Operating Expenses", "account_type": "Expense", "debit": 24_550_000, "credit": 0, "balance": 24_550_000, "balance_type": "Debit", "transactions": 247},
        ],
    }

def get_r2r_metrics() -> dict:
    """Get GL/R2R KPI metrics."""
    if _demo_mode:
        return _get_r2r_demo_metrics()

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
    } if je_stats and trial_balance else _get_r2r_demo_metrics()
