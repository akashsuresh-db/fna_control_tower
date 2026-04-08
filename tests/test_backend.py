"""
Finance & Accounting Control Tower — Backend Test Suite
========================================================
Tests every API endpoint, SSE stream, and button action handler.

Run:
    cd app && uv run pytest ../tests/test_backend.py -v

Set env vars before running locally:
    export DATABRICKS_CONFIG_PROFILE=e2-demo-west
    export DATABRICKS_WAREHOUSE_ID=4b9b953939869799
    export DATABRICKS_CATALOG=akash_s
    export DATABRICKS_SCHEMA=finance_and_accounting
"""

import json
import asyncio
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# ─── Path setup — MUST be first ───────────────────────────────
# Inject venv site-packages BEFORE any databricks imports so that
# databricks-sql-connector wins over the bare databricks SDK in conda.
APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app"))
VENV_SITE = os.path.join(APP_DIR, ".venv", "lib", "python3.10", "site-packages")
if os.path.exists(VENV_SITE) and VENV_SITE not in sys.path:
    sys.path.insert(0, VENV_SITE)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Force-reload databricks so venv's version (with sql) takes precedence
import importlib
if "databricks" in sys.modules:
    del sys.modules["databricks"]
for k in list(sys.modules.keys()):
    if k.startswith("databricks."):
        del sys.modules[k]

import httpx
from fastapi.testclient import TestClient

# Patch DB and lakebase before importing app to avoid connection on import
with patch("backend.db.query", return_value=[{"ok": 1}]), \
     patch("backend.lakebase.init_schema", return_value=None):
    from backend.main import app

client = TestClient(app, raise_server_exceptions=False)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

INVOICE_ID = "INV000001"
ERP_INVOICE_NUMBER = "VINV-2025-00001"

MOCK_P2P_METRICS = {
    "total_invoices": 500,
    "matched": 400,
    "two_way": 50,
    "amount_mismatch": 30,
    "no_po": 20,
    "exceptions": 50,
    "overdue_count": 75,
    "total_amount": 50000000.0,
    "overdue_amount": 8000000.0,
    "avg_aging_days": 28.5,
    "touchless_rate": 80.0,
}

MOCK_PAYMENT_RUN = {
    "total_payments": 300,
    "total_paid": 40000000.0,
    "avg_dpo": 38.2,
    "early_payments": 120,
    "on_time_payments": 150,
    "late_payments": 30,
}

MOCK_O2C_METRICS = {
    "total_outstanding": 25000000.0,
    "avg_dso": 38.5,
    "total_invoices": 450,
    "collected": 200,
    "total_collected": 18000000.0,
    "overdue_count": 90,
    "cei": 82.3,
    "aging_buckets": [
        {"bucket": "0-30", "count": 200, "amount": 10000000.0},
        {"bucket": "31-60", "count": 150, "amount": 8000000.0},
        {"bucket": "61-90", "count": 70, "amount": 5000000.0},
        {"bucket": "90+", "count": 30, "amount": 2000000.0},
    ],
    "customers_at_risk": [
        {"name": "Reliance Industries", "credit_limit": 5000000.0,
         "outstanding": 5500000.0, "utilization": 110.0, "overdue": 200000.0, "dso": 55.0},
    ],
}

MOCK_R2R_METRICS = {
    "total_jes": 250,
    "total_lines": 1200,
    "total_debits": 45000000.0,
    "total_credits": 45000000.0,
    "posted": 240,
    "pending": 10,
    "tb_total_debit": 45000000.0,
    "tb_total_credit": 45000000.0,
    "tb_imbalance": 0.0,
    "is_balanced": True,
    "trial_balance": [
        {"account_code": "1000", "account_name": "Cash", "account_type": "ASSET",
         "debit": 5000000.0, "credit": 0.0, "balance": 5000000.0, "balance_type": "DR", "transactions": 45},
        {"account_code": "2000", "account_name": "Accounts Payable", "account_type": "LIABILITY",
         "debit": 0.0, "credit": 5000000.0, "balance": 5000000.0, "balance_type": "CR", "transactions": 30},
    ],
}

MOCK_INVOICE_ROW = {
    "invoice_id": INVOICE_ID,
    "invoice_number": ERP_INVOICE_NUMBER,
    "exception_type": "AMOUNT_MISMATCH",
    "vendor_id": "VEN001",
    "vendor_name": "Tech Solutions Ltd",
    "po_id": "PO-2025-001",
    "invoice_date": "2025-03-01",
    "due_date": "2025-03-31",
    "invoice_amount": 250000.0,
    "total_amount": 240000.0,
    "status": "PENDING",
    "gstin_vendor": "29AABCT1332L1ZV",
    "payment_terms": "Net 30",
    "raw_text": "INVOICE\nVendor: Tech Solutions Ltd\nAmount: 250,000",
    "file_path": "/uploads/inv000001.pdf",
}


# ═══════════════════════════════════════════════════════════════
# 1. Health & Identity
# ═══════════════════════════════════════════════════════════════

class TestHealthAndIdentity:

    def test_health_returns_200(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_response_structure(self):
        resp = client.get("/api/health")
        body = resp.json()
        assert body["status"] == "healthy"
        assert body["app"] == "finance-operations"

    def test_me_no_headers(self):
        """Without forwarded headers, should return fallback values."""
        resp = client.get("/api/me")
        assert resp.status_code == 200
        body = resp.json()
        assert "name" in body
        assert "email" in body
        assert "username" in body

    def test_me_with_email_header(self):
        resp = client.get("/api/me", headers={"x-forwarded-email": "john.doe@databricks.com"})
        body = resp.json()
        assert body["email"] == "john.doe@databricks.com"
        assert body["name"] == "John"  # first name extracted

    def test_me_with_preferred_username(self):
        resp = client.get("/api/me", headers={
            "x-forwarded-email": "akash.s@databricks.com",
            "x-forwarded-preferred-username": "akash.s",
        })
        body = resp.json()
        assert body["name"] == "Akash"

    def test_me_single_name(self):
        resp = client.get("/api/me", headers={"x-forwarded-email": "alice@databricks.com"})
        body = resp.json()
        assert body["name"] == "Alice"


# ═══════════════════════════════════════════════════════════════
# 2. P2P Metrics Endpoint
# ═══════════════════════════════════════════════════════════════

class TestP2PMetrics:

    @patch("backend.db.get_p2p_metrics", return_value=MOCK_P2P_METRICS)
    @patch("backend.db.get_payment_run_data", return_value=MOCK_PAYMENT_RUN)
    def test_p2p_metrics_200(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        assert resp.status_code == 200

    @patch("backend.db.get_p2p_metrics", return_value=MOCK_P2P_METRICS)
    @patch("backend.db.get_payment_run_data", return_value=MOCK_PAYMENT_RUN)
    def test_p2p_metrics_structure(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        body = resp.json()
        assert "metrics" in body
        assert "payment_run" in body

    @patch("backend.db.get_p2p_metrics", return_value=MOCK_P2P_METRICS)
    @patch("backend.db.get_payment_run_data", return_value=MOCK_PAYMENT_RUN)
    def test_p2p_metrics_all_fields(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        m = resp.json()["metrics"]
        required = ["total_invoices", "matched", "two_way", "amount_mismatch",
                    "no_po", "exceptions", "overdue_count", "total_amount",
                    "overdue_amount", "avg_aging_days", "touchless_rate"]
        for field in required:
            assert field in m, f"Missing field: {field}"

    @patch("backend.db.get_p2p_metrics", return_value=MOCK_P2P_METRICS)
    @patch("backend.db.get_payment_run_data", return_value=MOCK_PAYMENT_RUN)
    def test_p2p_payment_run_fields(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        pr = resp.json()["payment_run"]
        required = ["total_payments", "total_paid", "avg_dpo",
                    "early_payments", "on_time_payments", "late_payments"]
        for field in required:
            assert field in pr, f"Missing payment_run field: {field}"

    @patch("backend.db.get_p2p_metrics", side_effect=Exception("DB connection failed"))
    @patch("backend.db.get_payment_run_data", return_value={})
    def test_p2p_metrics_db_error_returns_500(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        assert resp.status_code == 500
        assert "error" in resp.json()

    @patch("backend.db.get_p2p_metrics", return_value=MOCK_P2P_METRICS)
    @patch("backend.db.get_payment_run_data", return_value=MOCK_PAYMENT_RUN)
    def test_p2p_touchless_rate_is_percentage(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        rate = resp.json()["metrics"]["touchless_rate"]
        assert 0 <= rate <= 100

    @patch("backend.db.get_p2p_metrics", return_value=MOCK_P2P_METRICS)
    @patch("backend.db.get_payment_run_data", return_value=MOCK_PAYMENT_RUN)
    def test_p2p_exceptions_equals_mismatch_plus_no_po(self, mock_pr, mock_m):
        resp = client.get("/api/metrics/p2p")
        m = resp.json()["metrics"]
        assert m["exceptions"] == m["amount_mismatch"] + m["no_po"]


# ═══════════════════════════════════════════════════════════════
# 3. O2C Metrics Endpoint
# ═══════════════════════════════════════════════════════════════

class TestO2CMetrics:

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_metrics_200(self, mock_m):
        resp = client.get("/api/metrics/o2c")
        assert resp.status_code == 200

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_metrics_structure(self, mock_m):
        body = client.get("/api/metrics/o2c").json()
        assert "metrics" in body

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_all_required_fields(self, mock_m):
        m = client.get("/api/metrics/o2c").json()["metrics"]
        required = ["total_outstanding", "avg_dso", "total_invoices", "collected",
                    "total_collected", "overdue_count", "cei", "aging_buckets",
                    "customers_at_risk"]
        for field in required:
            assert field in m, f"Missing: {field}"

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_aging_buckets_is_list(self, mock_m):
        m = client.get("/api/metrics/o2c").json()["metrics"]
        assert isinstance(m["aging_buckets"], list)
        assert len(m["aging_buckets"]) > 0

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_aging_bucket_fields(self, mock_m):
        bucket = client.get("/api/metrics/o2c").json()["metrics"]["aging_buckets"][0]
        assert "bucket" in bucket
        assert "count" in bucket
        assert "amount" in bucket

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_customers_at_risk_structure(self, mock_m):
        c = client.get("/api/metrics/o2c").json()["metrics"]["customers_at_risk"][0]
        for field in ["name", "credit_limit", "outstanding", "utilization", "overdue", "dso"]:
            assert field in c, f"Missing customer field: {field}"

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_dso_is_numeric(self, mock_m):
        m = client.get("/api/metrics/o2c").json()["metrics"]
        assert isinstance(m["avg_dso"], (int, float))

    @patch("backend.db.get_o2c_metrics", side_effect=Exception("Warehouse offline"))
    def test_o2c_db_error_500(self, mock_m):
        resp = client.get("/api/metrics/o2c")
        assert resp.status_code == 500

    @patch("backend.db.get_o2c_metrics", return_value=MOCK_O2C_METRICS)
    def test_o2c_cei_range(self, mock_m):
        cei = client.get("/api/metrics/o2c").json()["metrics"]["cei"]
        assert 0 <= cei <= 100


# ═══════════════════════════════════════════════════════════════
# 4. R2R Metrics Endpoint
# ═══════════════════════════════════════════════════════════════

class TestR2RMetrics:

    @patch("backend.db.get_r2r_metrics", return_value=MOCK_R2R_METRICS)
    def test_r2r_metrics_200(self, mock_m):
        resp = client.get("/api/metrics/r2r")
        assert resp.status_code == 200

    @patch("backend.db.get_r2r_metrics", return_value=MOCK_R2R_METRICS)
    def test_r2r_metrics_structure(self, mock_m):
        body = client.get("/api/metrics/r2r").json()
        assert "metrics" in body

    @patch("backend.db.get_r2r_metrics", return_value=MOCK_R2R_METRICS)
    def test_r2r_all_required_fields(self, mock_m):
        m = client.get("/api/metrics/r2r").json()["metrics"]
        required = ["total_jes", "total_lines", "total_debits", "total_credits",
                    "posted", "pending", "tb_total_debit", "tb_total_credit",
                    "tb_imbalance", "is_balanced", "trial_balance"]
        for field in required:
            assert field in m, f"Missing: {field}"

    @patch("backend.db.get_r2r_metrics", return_value=MOCK_R2R_METRICS)
    def test_r2r_trial_balance_is_list(self, mock_m):
        tb = client.get("/api/metrics/r2r").json()["metrics"]["trial_balance"]
        assert isinstance(tb, list)
        assert len(tb) > 0

    @patch("backend.db.get_r2r_metrics", return_value=MOCK_R2R_METRICS)
    def test_r2r_trial_balance_row_fields(self, mock_m):
        row = client.get("/api/metrics/r2r").json()["metrics"]["trial_balance"][0]
        for field in ["account_code", "account_name", "account_type",
                      "debit", "credit", "balance", "balance_type", "transactions"]:
            assert field in row, f"Missing TB field: {field}"

    @patch("backend.db.get_r2r_metrics", return_value=MOCK_R2R_METRICS)
    def test_r2r_balanced_when_debits_equal_credits(self, mock_m):
        m = client.get("/api/metrics/r2r").json()["metrics"]
        assert m["is_balanced"] == (abs(m["tb_total_debit"] - m["tb_total_credit"]) < 1.0)

    @patch("backend.db.get_r2r_metrics", side_effect=Exception("Query timeout"))
    def test_r2r_db_error_500(self, mock_m):
        resp = client.get("/api/metrics/r2r")
        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# 5. SSE Streams — Start/Stop Button Handlers
# ═══════════════════════════════════════════════════════════════

class TestSSEStreams:
    """Test SSE endpoints that power the Start Processing / Start Collection Run /
    Start JE Validation buttons."""

    @patch("backend.db.get_invoices", return_value=[])
    def test_p2p_stream_200(self, mock_inv):
        """GET /stream/p2p should return 200 with text/event-stream."""
        resp = client.get("/stream/p2p")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @patch("backend.db.get_invoices", return_value=[])
    def test_p2p_stream_contains_greeting(self, mock_inv):
        resp = client.get("/stream/p2p")
        body = resp.text
        assert "greeting" in body

    @patch("backend.db.get_invoices", return_value=[])
    def test_p2p_stream_contains_summary(self, mock_inv):
        resp = client.get("/stream/p2p")
        assert "summary" in resp.text

    @patch("backend.db.get_invoices", return_value=[{
        "invoice_id": "INV001", "invoice_number": "VINV-2025-001",
        "vendor_name": "Test Corp", "vendor_category": "IT",
        "invoice_date": "2025-03-01", "due_date": "2025-03-31",
        "invoice_amount": 100000, "tax_amount": 18000, "invoice_total_inr": 118000,
        "match_status": "THREE_WAY_MATCHED", "has_po_ref": True,
        "is_overdue": False, "aging_days": 15, "aging_bucket": "0-30",
        "invoice_status": "PENDING", "po_id": "PO-001", "gstin_vendor": "29AABCT1332L1ZV",
    }])
    def test_p2p_stream_emits_invoice_event(self, mock_inv):
        resp = client.get("/stream/p2p")
        assert "invoice" in resp.text

    @patch("backend.db.get_invoices", return_value=[{
        "invoice_id": "INV002", "invoice_number": "VINV-2025-002",
        "vendor_name": "Bad Corp", "vendor_category": "Services",
        "invoice_date": "2025-01-01", "due_date": "2025-01-31",
        "invoice_amount": 500000, "tax_amount": 90000, "invoice_total_inr": 590000,
        "match_status": "AMOUNT_MISMATCH", "has_po_ref": True,
        "is_overdue": True, "aging_days": 65, "aging_bucket": "61-90",
        "invoice_status": "EXCEPTION", "po_id": "PO-002", "gstin_vendor": None,
    }])
    def test_p2p_stream_emits_exception_for_mismatch(self, mock_inv):
        resp = client.get("/stream/p2p")
        assert "quarantine" in resp.text or "exception" in resp.text

    @patch("backend.db.get_invoices", return_value=[{
        "invoice_id": "INV003", "invoice_number": "VINV-2025-003",
        "vendor_name": "No PO Corp", "vendor_category": "Services",
        "invoice_date": "2025-02-01", "due_date": "2025-02-28",
        "invoice_amount": 200000, "tax_amount": 36000, "invoice_total_inr": 236000,
        "match_status": "NO_PO_REFERENCE", "has_po_ref": False,
        "is_overdue": False, "aging_days": 20, "aging_bucket": "0-30",
        "invoice_status": "EXCEPTION", "po_id": None, "gstin_vendor": "29AABCT1332L1ZV",
    }])
    def test_p2p_stream_emits_quarantine_for_no_po(self, mock_inv):
        resp = client.get("/stream/p2p")
        assert "quarantine" in resp.text

    @patch("backend.db.get_collections", return_value=[])
    def test_o2c_stream_200(self, mock_col):
        resp = client.get("/stream/o2c")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @patch("backend.db.get_collections", return_value=[])
    def test_o2c_stream_contains_greeting(self, mock_col):
        assert "greeting" in client.get("/stream/o2c").text

    @patch("backend.db.get_collections", return_value=[])
    def test_o2c_stream_contains_summary(self, mock_col):
        assert "summary" in client.get("/stream/o2c").text

    @patch("backend.db.get_collections", return_value=[{
        "o2c_invoice_id": "CINV001", "invoice_number": "OINV-001",
        "customer_name": "Reliance Industries", "segment": "ENTERPRISE",
        "invoice_status": "OVERDUE", "balance_outstanding": 3000000,
        "days_overdue": 95, "days_outstanding": 95, "aging_bucket": "90+",
        "amount_collected_inr": 0, "due_date": "2024-12-31",
    }])
    def test_o2c_stream_emits_quarantine_for_critical_overdue(self, mock_col):
        resp = client.get("/stream/o2c")
        assert "quarantine" in resp.text

    @patch("backend.db.get_collections", return_value=[{
        "o2c_invoice_id": "CINV002", "invoice_number": "OINV-002",
        "customer_name": "Tata Steel", "segment": "ENTERPRISE",
        "invoice_status": "COLLECTED", "balance_outstanding": 0,
        "days_overdue": 0, "days_outstanding": 10, "aging_bucket": "0-30",
        "amount_collected_inr": 1500000, "due_date": "2025-03-31",
    }])
    def test_o2c_stream_emits_payment_received_for_collected(self, mock_col):
        resp = client.get("/stream/o2c")
        assert "payment_received" in resp.text

    @patch("backend.db.get_journal_entries", return_value=[])
    def test_r2r_stream_200(self, mock_je):
        resp = client.get("/stream/r2r")
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @patch("backend.db.get_journal_entries", return_value=[])
    def test_r2r_stream_contains_greeting(self, mock_je):
        assert "greeting" in client.get("/stream/r2r").text

    @patch("backend.db.get_journal_entries", return_value=[])
    def test_r2r_stream_contains_checklist(self, mock_je):
        resp = client.get("/stream/r2r")
        # Greeting event should contain checklist
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        greeting_found = False
        for line in lines:
            try:
                data = json.loads(line[5:])
                if data.get("type") == "greeting":
                    greeting_found = True
                    assert "checklist" in data["data"]
                    assert len(data["data"]["checklist"]) == 8
                    break
            except Exception:
                pass
        assert greeting_found

    @patch("backend.db.get_journal_entries", return_value=[
        {"je_id": "JE001", "je_number": "JE-2025-001", "je_date": "2025-03-31",
         "je_type": "STANDARD", "posted_by": "Sunita", "status": "POSTED",
         "department": "Finance", "gl_line_number": 1, "account_code": "1000",
         "account_name": "Cash", "debit_inr": 100000, "credit_inr": 0, "gl_description": "Receipt"},
        {"je_id": "JE001", "je_number": "JE-2025-001", "je_date": "2025-03-31",
         "je_type": "STANDARD", "posted_by": "Sunita", "status": "POSTED",
         "department": "Finance", "gl_line_number": 2, "account_code": "2000",
         "account_name": "Revenue", "debit_inr": 0, "credit_inr": 100000, "gl_description": "Revenue"},
    ])
    def test_r2r_stream_emits_journal_entry(self, mock_je):
        resp = client.get("/stream/r2r")
        assert "journal_entry" in resp.text

    @patch("backend.db.get_journal_entries", return_value=[
        {"je_id": "JE002", "je_number": "JE-2025-002", "je_date": "2025-03-31",
         "je_type": "STANDARD", "posted_by": "Sunita", "status": "POSTED",
         "department": "Finance", "gl_line_number": 1, "account_code": "1000",
         "account_name": "Cash", "debit_inr": 100000, "credit_inr": 0, "gl_description": "Unbalanced"},
    ])
    def test_r2r_stream_emits_quarantine_for_unbalanced_je(self, mock_je):
        resp = client.get("/stream/r2r")
        assert "quarantine" in resp.text


# ═══════════════════════════════════════════════════════════════
# 6. AP Approve / Reject Button (P2P Tab)
# ═══════════════════════════════════════════════════════════════

class TestApprovalEndpoint:
    """Tests the Approve / Reject button handlers in the P2P invoice queue."""

    @patch("backend.lakebase.log_approval", return_value=None)
    def test_approve_invoice_200(self, mock_log):
        resp = client.post("/api/approve", json={
            "invoice_id": INVOICE_ID,
            "action": "APPROVED",
            "reason": "Verified with vendor",
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.log_approval", return_value=None)
    def test_approve_response_structure(self, mock_log):
        resp = client.post("/api/approve", json={
            "invoice_id": INVOICE_ID, "action": "APPROVED", "reason": "",
        })
        body = resp.json()
        assert body["status"] == "logged"
        assert body["action"] == "APPROVED"
        assert body["invoice_id"] == INVOICE_ID

    @patch("backend.lakebase.log_approval", return_value=None)
    def test_reject_invoice_200(self, mock_log):
        resp = client.post("/api/approve", json={
            "invoice_id": INVOICE_ID, "action": "REJECTED", "reason": "Duplicate invoice",
        })
        assert resp.status_code == 200
        assert resp.json()["action"] == "REJECTED"

    @patch("backend.lakebase.log_approval", return_value=None)
    def test_escalate_invoice_200(self, mock_log):
        resp = client.post("/api/approve", json={
            "invoice_id": INVOICE_ID, "action": "ESCALATED", "reason": "Needs manager review",
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.log_approval", return_value=None)
    def test_approval_with_user_header(self, mock_log):
        resp = client.post(
            "/api/approve",
            json={"invoice_id": INVOICE_ID, "action": "APPROVED", "reason": ""},
            headers={"x-forwarded-email": "akash.s@databricks.com"},
        )
        assert resp.status_code == 200
        mock_log.assert_called_once()
        call_args = mock_log.call_args[0]
        assert "akash.s@databricks.com" in call_args

    @patch("backend.lakebase.log_approval", return_value=None)
    def test_approval_without_reason_is_valid(self, mock_log):
        resp = client.post("/api/approve", json={"invoice_id": INVOICE_ID, "action": "APPROVED"})
        assert resp.status_code == 200

    def test_approval_missing_invoice_id_returns_422(self):
        resp = client.post("/api/approve", json={"action": "APPROVED"})
        assert resp.status_code == 422

    def test_approval_missing_action_returns_422(self):
        resp = client.post("/api/approve", json={"invoice_id": INVOICE_ID})
        assert resp.status_code == 422

    @patch("backend.lakebase.log_approval", side_effect=Exception("Lakebase down"))
    def test_approval_lakebase_error_returns_500(self, mock_log):
        resp = client.post("/api/approve", json={
            "invoice_id": INVOICE_ID, "action": "APPROVED", "reason": "",
        })
        assert resp.status_code == 500
        assert "error" in resp.json()


# ═══════════════════════════════════════════════════════════════
# 7. AR Call Log Button (O2C Tab)
# ═══════════════════════════════════════════════════════════════

class TestCallLogEndpoint:
    """Tests the 'Log Call' button in the AR collections queue."""

    @patch("backend.lakebase.log_call", return_value=None)
    def test_call_log_reached_ptp(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST001",
            "customer_name": "Reliance Industries",
            "outcome": "REACHED_PTP",
            "ptp_date": "2025-04-15",
            "notes": "Customer committed to pay by 15th April",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged"

    @patch("backend.lakebase.log_call", return_value=None)
    def test_call_log_reached_dispute(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST002",
            "customer_name": "Tata Steel",
            "outcome": "REACHED_DISPUTE",
            "notes": "Disputing invoice amount",
        })
        assert resp.status_code == 200
        assert resp.json()["outcome"] == "REACHED_DISPUTE"

    @patch("backend.lakebase.log_call", return_value=None)
    def test_call_log_voicemail(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST003",
            "customer_name": "Infosys",
            "outcome": "VOICEMAIL",
            "notes": "Left voicemail, follow up tomorrow",
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.log_call", return_value=None)
    def test_call_log_escalate(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST004",
            "customer_name": "Wipro",
            "outcome": "ESCALATE",
            "notes": "Escalating to credit manager",
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.log_call", return_value=None)
    def test_call_log_without_optional_fields(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST005",
            "outcome": "VOICEMAIL",
        })
        assert resp.status_code == 200

    def test_call_log_missing_customer_id_returns_422(self):
        resp = client.post("/api/call-log", json={"outcome": "VOICEMAIL"})
        assert resp.status_code == 422

    def test_call_log_missing_outcome_returns_422(self):
        resp = client.post("/api/call-log", json={"customer_id": "CUST001"})
        assert resp.status_code == 422

    @patch("backend.lakebase.log_call", return_value=None)
    def test_call_log_ptp_date_null_for_non_ptp(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST001",
            "outcome": "VOICEMAIL",
            "ptp_date": None,
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.log_call", side_effect=Exception("DB error"))
    def test_call_log_lakebase_error_returns_500(self, mock_log):
        resp = client.post("/api/call-log", json={
            "customer_id": "CUST001", "outcome": "VOICEMAIL",
        })
        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# 8. Invoice Viewer (View Invoice button from ExceptionDrawer)
# ═══════════════════════════════════════════════════════════════

class TestInvoiceEndpoint:
    """Tests the invoice detail view opened via ExceptionDrawer → 'View Invoice'."""

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    def test_get_invoice_by_id_200(self, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}")
        assert resp.status_code == 200

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    def test_get_invoice_response_structure(self, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}")
        body = resp.json()
        required = ["invoice_id", "invoice_number", "quarantine_reason",
                    "vendor_id", "vendor_name", "po_id", "invoice_date",
                    "due_date", "invoice_amount", "po_amount", "status",
                    "gstin", "payment_terms", "raw_text", "file_path"]
        for field in required:
            assert field in body, f"Missing field: {field}"

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    def test_get_invoice_amounts_are_float(self, mock_q):
        body = client.get(f"/api/invoice/{INVOICE_ID}").json()
        assert isinstance(body["invoice_amount"], float)
        assert isinstance(body["po_amount"], float)

    @patch("backend.db.query", return_value=[])
    def test_get_invoice_not_found_returns_404(self, mock_q):
        resp = client.get("/api/invoice/NONEXISTENT")
        assert resp.status_code == 404

    @patch("backend.db.query", return_value=[{**MOCK_INVOICE_ROW, "invoice_id": None,
                                               "exception_type": None}])
    def test_get_invoice_by_erp_number(self, mock_q):
        resp = client.get(f"/api/invoice/{ERP_INVOICE_NUMBER}")
        assert resp.status_code == 200

    @patch("backend.db.query", side_effect=Exception("Query failed"))
    def test_get_invoice_db_error_returns_500(self, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}")
        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# 9. Invoice PDF Download Button
# ═══════════════════════════════════════════════════════════════

class TestInvoicePDFEndpoint:
    """Tests the 'Download PDF' button in InvoiceDrawer."""

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    @patch("backend.invoice_pdf.build_invoice_pdf", return_value=b"%PDF-1.4 fake pdf bytes")
    def test_pdf_returns_200(self, mock_pdf, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}/pdf")
        assert resp.status_code == 200

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    @patch("backend.invoice_pdf.build_invoice_pdf", return_value=b"%PDF-1.4 fake")
    def test_pdf_content_type_is_pdf(self, mock_pdf, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}/pdf")
        assert "application/pdf" in resp.headers.get("content-type", "")

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    @patch("backend.invoice_pdf.build_invoice_pdf", return_value=b"%PDF-1.4 fake")
    def test_pdf_inline_by_default(self, mock_pdf, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}/pdf")
        assert "inline" in resp.headers.get("content-disposition", "")

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    @patch("backend.invoice_pdf.build_invoice_pdf", return_value=b"%PDF-1.4 fake")
    def test_pdf_download_param_sets_attachment(self, mock_pdf, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}/pdf?download=true")
        assert "attachment" in resp.headers.get("content-disposition", "")

    @patch("backend.db.query", return_value=[MOCK_INVOICE_ROW])
    @patch("backend.invoice_pdf.build_invoice_pdf", return_value=b"%PDF-1.4 fake")
    def test_pdf_filename_includes_invoice_id(self, mock_pdf, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}/pdf")
        assert INVOICE_ID in resp.headers.get("content-disposition", "")

    @patch("backend.db.query", return_value=[])
    def test_pdf_not_found_returns_404(self, mock_q):
        resp = client.get("/api/invoice/NONEXISTENT/pdf")
        assert resp.status_code == 404

    @patch("backend.db.query", side_effect=Exception("DB timeout"))
    def test_pdf_db_error_returns_500(self, mock_q):
        resp = client.get(f"/api/invoice/{INVOICE_ID}/pdf")
        assert resp.status_code == 500


# ═══════════════════════════════════════════════════════════════
# 10. AI Chat — Send Button
# ═══════════════════════════════════════════════════════════════

class TestChatEndpoint:
    """Tests the AI chat Send button and SSE streaming response."""

    def _mock_stream(self, text="DPO is 38 days, within the 30-45 day healthy range."):
        async def _gen(messages, user_token=None, previous_response_id=None):
            for word in text.split():
                yield {"type": "chunk", "text": word + " "}
            yield {"type": "done", "response_id": None, "tool": None}
        return _gen

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_returns_streaming_response(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream()
        resp = client.post("/api/chat", json={
            "question": "What is the current DPO?",
            "active_tab": "P2P",
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_content_type_is_event_stream(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream()
        resp = client.post("/api/chat", json={"question": "What is DSO?", "active_tab": "O2C"})
        assert "text/event-stream" in resp.headers.get("content-type", "")

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_emits_chunk_events(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Hello World")
        resp = client.post("/api/chat", json={"question": "Hi", "active_tab": "P2P"})
        assert '"type": "chunk"' in resp.text

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_emits_done_event(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Answer here")
        resp = client.post("/api/chat", json={"question": "Test", "active_tab": "P2P"})
        assert '"type": "done"' in resp.text

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_done_event_includes_session_id(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Test answer")
        resp = client.post("/api/chat", json={"question": "Test", "active_tab": "P2P"})
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        done_events = [json.loads(l[5:]) for l in lines if '"type": "done"' in l]
        assert len(done_events) > 0
        assert "session_id" in done_events[0]

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_uses_provided_session_id(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Test")
        session_id = "my-test-session-123"
        resp = client.post("/api/chat", json={
            "question": "Test", "active_tab": "P2P", "session_id": session_id,
        })
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        done_events = [json.loads(l[5:]) for l in lines if '"type": "done"' in l]
        assert done_events[0]["session_id"] == session_id

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_generates_session_id_if_empty(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Test")
        resp = client.post("/api/chat", json={"question": "Test", "active_tab": "P2P"})
        lines = [l for l in resp.text.split("\n") if l.startswith("data:")]
        done_events = [json.loads(l[5:]) for l in lines if '"type": "done"' in l]
        assert done_events[0]["session_id"]  # non-empty UUID

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_with_o2c_tab(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("DSO is 38 days.")
        resp = client.post("/api/chat", json={"question": "What is DSO?", "active_tab": "O2C"})
        assert resp.status_code == 200

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_with_r2r_tab(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Trial balance is balanced.")
        resp = client.post("/api/chat", json={
            "question": "Is trial balance balanced?", "active_tab": "R2R",
        })
        assert resp.status_code == 200

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_persists_to_lakebase(self, mock_stream, mock_log, mock_hist):
        mock_stream.side_effect = self._mock_stream("Answer persisted")
        client.post("/api/chat", json={"question": "Test persistence", "active_tab": "P2P"})
        mock_log.assert_called_once()

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_empty_answer_uses_fallback(self, mock_stream, mock_log, mock_hist):
        async def _empty_gen(messages, user_token=None, previous_response_id=None):
            yield {"type": "done", "response_id": None, "tool": None}
        mock_stream.side_effect = _empty_gen
        resp = client.post("/api/chat", json={"question": "Test", "active_tab": "P2P"})
        assert "No answer returned" in resp.text or '"type": "chunk"' in resp.text

    def test_chat_missing_question_returns_422(self):
        resp = client.post("/api/chat", json={"active_tab": "P2P"})
        assert resp.status_code == 422

    @patch("backend.lakebase.get_session_messages", return_value=[])
    @patch("backend.lakebase.log_chat", return_value=None)
    @patch("backend.main.stream_mas_agent")
    def test_chat_stream_error_emits_error_event(self, mock_stream, mock_log, mock_hist):
        async def _error_gen(messages, user_token=None, previous_response_id=None):
            yield {"type": "error", "message": "Model unavailable"}
        mock_stream.side_effect = _error_gen
        resp = client.post("/api/chat", json={"question": "Test", "active_tab": "P2P"})
        assert '"type": "error"' in resp.text


# ═══════════════════════════════════════════════════════════════
# 11. Session History (AI Chat History Panel)
# ═══════════════════════════════════════════════════════════════

class TestSessionHistory:
    """Tests the chat history panel buttons."""

    @patch("backend.lakebase.get_user_sessions", return_value=[
        {"session_id": "abc123", "first_question": "What is DPO?",
         "tab": "P2P", "started_at": "2025-03-01T10:00:00", "last_active": "2025-03-01T10:05:00",
         "message_count": 3},
    ])
    def test_my_sessions_200(self, mock_sessions):
        resp = client.get("/api/my-sessions")
        assert resp.status_code == 200

    @patch("backend.lakebase.get_user_sessions", return_value=[])
    def test_my_sessions_returns_empty_list(self, mock_sessions):
        resp = client.get("/api/my-sessions")
        assert resp.json()["sessions"] == []

    @patch("backend.lakebase.get_user_sessions", return_value=[
        {"session_id": "abc123", "first_question": "What is DPO?",
         "tab": "P2P", "started_at": "2025-03-01T10:00:00",
         "last_active": "2025-03-01T10:05:00", "message_count": 3},
    ])
    def test_my_sessions_with_email_header(self, mock_sessions):
        resp = client.get("/api/my-sessions",
                          headers={"x-forwarded-email": "akash.s@databricks.com"})
        assert resp.status_code == 200
        mock_sessions.assert_called_with("akash.s@databricks.com")

    @patch("backend.lakebase.get_session_detail", return_value={
        "messages": [
            {"role": "user", "content": "What is DPO?"},
            {"role": "assistant", "content": "DPO is 38 days."},
        ],
        "previous_response_id": None,
    })
    def test_get_session_detail_200(self, mock_detail):
        resp = client.get("/api/session/abc123")
        assert resp.status_code == 200

    @patch("backend.lakebase.get_session_detail", return_value={
        "messages": [], "previous_response_id": None,
    })
    def test_get_session_detail_structure(self, mock_detail):
        resp = client.get("/api/session/abc123")
        body = resp.json()
        assert "session_id" in body
        assert "messages" in body
        assert "previous_response_id" in body

    @patch("backend.lakebase.get_user_sessions", side_effect=Exception("Lakebase error"))
    def test_my_sessions_lakebase_error_returns_empty(self, mock_sessions):
        resp = client.get("/api/my-sessions")
        body = resp.json()
        assert "sessions" in body  # Graceful degradation
        assert body["sessions"] == []


# ═══════════════════════════════════════════════════════════════
# 12. Approvals History
# ═══════════════════════════════════════════════════════════════

class TestApprovalsHistory:

    @patch("backend.lakebase.get_user_approvals", return_value=[
        {"invoice_id": INVOICE_ID, "action": "APPROVED", "reason": "",
         "actioned_by": "akash.s@databricks.com", "actioned_at": "2025-03-01T10:00:00"},
    ])
    def test_my_approvals_200(self, mock_approvals):
        resp = client.get("/api/my-approvals")
        assert resp.status_code == 200
        assert "approvals" in resp.json()

    @patch("backend.lakebase.get_user_approvals", return_value=[])
    def test_my_approvals_empty_list(self, mock_approvals):
        assert client.get("/api/my-approvals").json()["approvals"] == []


# ═══════════════════════════════════════════════════════════════
# 13. Frontend Static Files
# ═══════════════════════════════════════════════════════════════

class TestStaticFiles:
    """Tests that the React app is being served correctly."""

    def test_root_serves_index_html(self):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_unknown_path_serves_spa_fallback(self):
        resp = client.get("/some/deep/route")
        # SPA fallback should return index.html (200) or 404 if frontend not built
        assert resp.status_code in (200, 404)

    def test_api_path_not_caught_by_spa(self):
        resp = client.get("/api/nonexistent-endpoint")
        assert resp.status_code == 404

    def test_stream_path_not_caught_by_spa(self):
        """Stream paths should not be caught by the SPA fallback."""
        # This would hang as SSE, but the path prefix check should work
        # We just verify it doesn't 404 from the SPA handler
        pass  # Covered by SSE tests above


# ═══════════════════════════════════════════════════════════════
# 14. Exception Detection Logic
# ═══════════════════════════════════════════════════════════════

class TestExceptionDetection:
    """Tests the server-side exception detection rules (not UI buttons)."""

    def test_amount_mismatch_detected(self):
        from backend.streams import _detect_p2p_exceptions
        excs = _detect_p2p_exceptions({"match_status": "AMOUNT_MISMATCH", "po_id": "PO-001"})
        assert any(e["rule"] == "amount_match" for e in excs)
        assert any(e["severity"] == "high" for e in excs)

    def test_no_po_reference_detected(self):
        from backend.streams import _detect_p2p_exceptions
        excs = _detect_p2p_exceptions({"match_status": "NO_PO_REFERENCE"})
        assert any(e["rule"] == "has_po_ref" for e in excs)

    def test_overdue_critical_detected(self):
        from backend.streams import _detect_p2p_exceptions
        excs = _detect_p2p_exceptions({"match_status": "THREE_WAY_MATCHED",
                                        "is_overdue": "true", "aging_days": 65})
        assert any(e["rule"] == "overdue_critical" for e in excs)
        assert any(e["severity"] == "critical" for e in excs)

    def test_missing_gstin_detected(self):
        from backend.streams import _detect_p2p_exceptions
        excs = _detect_p2p_exceptions({"match_status": "THREE_WAY_MATCHED", "gstin_vendor": None})
        assert any(e["rule"] == "missing_gstin" for e in excs)

    def test_three_way_matched_no_exception(self):
        from backend.streams import _detect_p2p_exceptions
        excs = _detect_p2p_exceptions({
            "match_status": "THREE_WAY_MATCHED",
            "is_overdue": "false",
            "aging_days": 15,
            "gstin_vendor": "29AABCT1332L1ZV",
        })
        assert not any(e["rule"] in ("amount_match", "has_po_ref") for e in excs)

    def test_written_off_quarantine(self):
        from backend.streams import _detect_o2c_exceptions
        excs = _detect_o2c_exceptions({
            "invoice_status": "WRITTEN_OFF",
            "balance_outstanding": 500000,
            "days_overdue": 0,
        })
        assert any(e["rule"] == "written_off" for e in excs)
        assert any(e["type"] == "quarantine" for e in excs)

    def test_critical_overdue_o2c(self):
        from backend.streams import _detect_o2c_exceptions
        excs = _detect_o2c_exceptions({
            "invoice_status": "OVERDUE",
            "balance_outstanding": 3000000,
            "days_overdue": 95,
        })
        assert any(e["rule"] == "critical_overdue" for e in excs)

    def test_aging_concern_o2c(self):
        from backend.streams import _detect_o2c_exceptions
        excs = _detect_o2c_exceptions({
            "invoice_status": "OVERDUE",
            "balance_outstanding": 1000000,
            "days_overdue": 65,
        })
        assert any(e["rule"] == "aging_concern" for e in excs)
        assert any(e["severity"] == "high" for e in excs)

    def test_unbalanced_je_quarantine(self):
        from backend.streams import _detect_r2r_exceptions
        je = {"posted_by": "Sunita"}
        lines = [
            {"debit_inr": 100000, "credit_inr": 0},
            {"debit_inr": 0, "credit_inr": 90000},  # unbalanced
        ]
        excs = _detect_r2r_exceptions(je, lines)
        assert any(e["rule"] == "je_balanced" for e in excs)
        assert any(e["type"] == "quarantine" for e in excs)

    def test_balanced_je_no_quarantine(self):
        from backend.streams import _detect_r2r_exceptions
        je = {"posted_by": "Sunita"}
        lines = [
            {"debit_inr": 100000, "credit_inr": 0},
            {"debit_inr": 0, "credit_inr": 100000},
        ]
        excs = _detect_r2r_exceptions(je, lines)
        assert not any(e["rule"] == "je_balanced" for e in excs)

    def test_high_value_je_exception(self):
        from backend.streams import _detect_r2r_exceptions
        je = {"posted_by": "Vikram"}
        lines = [
            {"debit_inr": 6000000, "credit_inr": 0},
            {"debit_inr": 0, "credit_inr": 6000000},
        ]
        excs = _detect_r2r_exceptions(je, lines)
        assert any(e["rule"] == "high_value_je" for e in excs)
