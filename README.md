# Finance Operations Intelligence — Databricks Lakehouse Demo

> **A production-grade, end-to-end Finance & Accounting platform on Azure Databricks** — covering Procure-to-Pay (P2P), Order-to-Cash (O2C), and Record-to-Report (R2R) with AI-powered invoice processing, a real-time operations app, and a conversational multi-agent AI system backed by Genie.

---

## Table of Contents

1. [Business Problem](#1-business-problem)
2. [Value Proposition](#2-value-proposition)
3. [How Databricks Solves It](#3-how-databricks-solves-it)
4. [Platform Architecture](#4-platform-architecture)
5. [Process Flows](#5-process-flows)
6. [AI Layer](#6-ai-layer)
7. [Finance Operations App](#7-finance-operations-app)
8. [Conversational AI — Multi-Agent System](#8-conversational-ai--multi-agent-system)
9. [Data Quality & Governance](#9-data-quality--governance)
10. [Key Metrics](#10-key-metrics)
11. [Tech Stack](#11-tech-stack)
12. [Quick Reference](#12-quick-reference)
13. [Repo Structure](#13-repo-structure)
14. [Setup & Deployment](#14-setup--deployment)
15. [Demo Walkthrough](#15-demo-walkthrough)

---

## 1. Business Problem

Finance teams at mid-to-large enterprises operate across three critical workflows — Procure-to-Pay, Order-to-Cash, and Record-to-Report. Each is burdened by the same structural problem: **data is everywhere except where it needs to be**.

### The Pain Points

| Workflow | Pain Point | Business Impact |
|---|---|---|
| **P2P** | Invoices arrive via email, PDF, supplier portal — unstructured, unmatched | AP clerks spend 60–70% of time on manual matching and exception handling |
| **P2P** | 3-way matching (PO ↔ Invoice ↔ GRN) done in spreadsheets | Duplicate payments, overpayments, fraud exposure |
| **O2C** | AR aging data lives in ERP exports, updated weekly | Collections team works stale data; DSO increases |
| **O2C** | No single view of customer credit + outstanding + dispute history | Credit decisions made without full context |
| **R2R** | Journal entries validated manually at month-end | Close cycle takes 5–10 business days; late detection of errors |
| **R2R** | Trial balance assembled from multiple ERP extracts | Material reconciliation errors surface post-close |
| **Cross** | No unified data model across P2P, O2C, R2R | CFO/Controller cannot see working capital in one place |
| **Cross** | AI/ML insights blocked by poor data quality | Finance teams cannot leverage predictive analytics |

### The Root Cause

Finance data is **fragmented by design** — ERPs are transactional systems optimised for recording, not analysing. The result: a permanent gap between the data that exists and the insights finance teams need to operate.

---

## 2. Value Proposition

### What This Platform Delivers

```
FROM                                    TO
─────────────────────────────────────────────────────────────────
Manual 3-way matching (2–3 days)   →   Automated in minutes (DLT Silver layer)
Invoice processing (5–7 days)      →   AI extraction in seconds (ai_parse_document)
Month-end close (5–10 days)        →   Continuous close with live trial balance
ERP-locked analytics               →   Natural language queries (Genie + AI Chat)
Siloed P2P / O2C / R2R views       →   Unified working capital dashboard
Spreadsheet-driven reporting       →   Production-grade Delta Gold tables
Reactive exception handling        →   Proactive DQ enforcement (DLT Expectations)
```

### Quantified Impact

| Metric | Before | After | Improvement |
|---|---|---|---|
| Invoice processing cost | $8–12 per invoice (manual) | $1–2 per invoice (automated) | **75–85% reduction** |
| 3-way match cycle time | 2–3 days | Real-time | **99% faster** |
| Touchless invoice rate | 0% | 33.9% (demo data) | **Straight-through processing** |
| Month-end close | 5–10 business days | 2–3 days | **50–70% faster** |
| DSO visibility | Weekly batch | Real-time | **Continuous** |
| Data quality errors reaching reporting | Unknown | 0 (quarantined) | **100% prevention** |

---

## 3. How Databricks Solves It

Each capability maps directly to a Databricks product:

| Business Need | Databricks Solution | Why It Matters |
|---|---|---|
| **Ingest ERP data at scale** | Auto Loader + Delta Live Tables | Incremental, idempotent ingestion; handles schema evolution |
| **Enforce data quality** | DLT Expectations + Quarantine pattern | SOX-ready quality contracts; bad records never reach reporting |
| **3-way matching** | DLT Silver transformations | Automated PO ↔ Invoice ↔ GRN match at pipeline time |
| **AI invoice extraction** | `ai_parse_document()` + `ai_extract()` | Built-in SQL functions; no custom model, no API keys |
| **Unified governance** | Unity Catalog | Single namespace, column-level lineage, RBAC, audit trail |
| **Business-ready models** | Delta Gold tables | Pre-aggregated P2P, O2C, R2R metrics; sub-second query |
| **Natural language analytics** | Databricks Genie | Finance users query in English; no SQL knowledge required |
| **Real-time operations app** | Databricks Apps + SSE | OAuth SSO, serverless hosting, streamed live data |
| **Operational state** | Lakebase (managed Postgres) | ACID writes for AP approvals, AR call logs, chat history |
| **Intelligent AI routing** | LangGraph + Claude via MAS | ReAct agent supervisor routes to Genie sub-agents per domain |

---

## 4. Platform Architecture

### Medallion Lakehouse Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  DATA SOURCES                                                        │
│  ERP Exports (SAP/Oracle/NetSuite) · Invoice PDFs · Email           │
└────────────────────────┬────────────────────────────────────────────┘
                         │ Auto Loader / Staged files
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  BRONZE LAYER  (Raw Ingestion — Delta Live Tables)                  │
│  bronze_vendors · bronze_customers · bronze_po_header               │
│  bronze_p2p_invoices · bronze_journal_entries                       │
│  bronze_raw_invoice_documents (UC Volume)                           │
│  DLT Expectations: drop nulls, validate formats                     │
└────────────────────────┬────────────────────────────────────────────┘
                         │ DLT transformations + AI functions
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  SILVER LAYER  (Cleansed & Enriched — Delta Live Tables)            │
│  silver_p2p_invoices  ← dedup + 3-way match (match_status)          │
│  silver_invoice_extractions  ← ai_parse_document + ai_extract       │
│  DLT Expectations: quarantine unbalanced JEs, future-dated invoices │
└────────────────────────┬────────────────────────────────────────────┘
                         │ Spark SQL Gold transformations
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GOLD LAYER  (Business Models — Delta Tables)                       │
│  P2P: gold_dim_vendor · gold_fact_invoices · gold_fact_payments     │
│  O2C: gold_dim_customer · gold_fact_sales · gold_fact_collections   │
│  R2R: gold_fact_gl · gold_fact_trial_balance                        │
│  KPI: finance_kpis (unified view across all three domains)          │
└──────────────┬─────────────────────────────┬───────────────────────┘
               │                             │
               ▼                             ▼
┌──────────────────────┐       ┌─────────────────────────────────────┐
│  GENIE AI ANALYST    │       │  FINANCE OPERATIONS APP             │
│  Attached to all 9   │       │  React + FastAPI on Databricks Apps │
│  Gold tables via     │       │  AP · AR · GL tabs · SSE streaming  │
│  ETL job (notebook   │       │  Lakebase for operational state     │
│  08_Configure_Genie) │       │  Multi-agent AI chat sidebar        │
└──────────────────────┘       └─────────────────────────────────────┘
               │                             │
               └──────────────┬──────────────┘
                              ▼
               ┌──────────────────────────────────────┐
               │  MAS SUPERVISOR ENDPOINT             │
               │  LangGraph ReAct agent               │
               │  (Claude via FMAPI)                  │
               │  GenieTool → Genie Space             │
               │  Deployed as UC-registered model     │
               │  + serving endpoint via MLflow        │
               └──────────────────────────────────────┘
```

### Governance Layer (Unity Catalog)

All tables live in a single 3-part namespace:
```
fna_control_tower.finance_and_accounting.<table_name>
```
- Full column-level lineage from source file to Gold
- AI-generated table and column descriptions
- RBAC: row-level security available for vendor/customer data isolation
- Audit trail for SOX compliance

---

## 5. Process Flows

### 5.1 Procure-to-Pay (P2P)

```
Vendor Invoice arrives (email / portal / EDI)
        │
        ▼
[Bronze] Invoice captured as-is
  DLT Expectations: amount > 0, vendor_id NOT NULL
        │
        ▼
[Silver] 3-Way Match Engine
  Looks up PO from bronze_po_header
  Checks GRN from bronze_grn
  Computes match_status:
    ✅ THREE_WAY_MATCHED   — PO + GRN + Invoice within 2% tolerance
    ✓  TWO_WAY_MATCHED     — PO matches, no GRN yet
    ⚠  AMOUNT_MISMATCH     — PO exists, amount differs > 2%
    ✗  NO_PO_REFERENCE     — No linked purchase order found
        │
        ▼
[AI Layer] ai_parse_document() → ai_extract()
  Extracts: invoice_number, vendor, GSTIN, line items,
            CGST, SGST, total, bank details, IFSC
        │
        ▼
[Gold] gold_fact_invoices
  Aging buckets: 0-30 / 31-60 / 61-90 / 90+ days
  DPO calculation, match_compliance_pct per vendor
        │
        ▼
[App] Finance Operations App — AP Tab
  Invoice queue streams in via SSE
  Exceptions surfaced for manual review
  Approve / Reject with reason → logged to Lakebase
```

**Key metric:** 33.9% of invoices are `THREE_WAY_MATCHED` → eligible for straight-through payment processing (no human touch required).

---

### 5.2 Order-to-Cash (O2C)

```
Sales Order created
        │
        ▼
[Bronze] Customer invoices + payment receipts
        │
        ▼
[Silver] Collections enrichment
  Days overdue calculated per invoice
  Short payments flagged
        │
        ▼
[Gold] gold_fact_collections + gold_dim_customer
  DSO (Days Sales Outstanding) by segment
  Aging buckets per customer
  CEI (Collections Effectiveness Index)
        │
        ▼
[App] Finance Operations App — AR Tab
  Overdue customer queue with call priority
  Promise-to-Pay logging → Lakebase ar_call_logs
  Cash application feed via SSE
```

---

### 5.3 Record-to-Report (R2R)

```
Journal entries posted in ERP
        │
        ▼
[Bronze] bronze_journal_entries
  DLT Expectation: abs(debit - credit) < 0.01
  Unbalanced entries → bronze_je_exceptions (quarantine)
        │
        ▼
[Gold] gold_fact_gl + gold_fact_trial_balance
  50 GL accounts · 2,000 journal entries
  Trial balance with debit/credit totals
  Period-over-period variance flags
        │
        ▼
[App] Finance Operations App — GL Tab
  Month-end close checklist
  JE validation feed via SSE
  Live trial balance build with variance alerts
```

---

## 6. AI Layer

### 6.1 Invoice AI Processing (`ai_parse_document` + `ai_extract`)

Databricks built-in SQL functions — no custom model deployment, no API keys, no prompt engineering. Because DLT pipelines cannot call `ai_parse_document()` (no cluster-side inference support), AI extraction runs in a **dedicated pre-processing notebook** (`05_Invoice_AI_Processing.py`) after the DLT Silver layer completes, then writes to `silver_invoice_extractions`.

```sql
-- Step 1: Parse raw invoice document (OCR + text extraction)
SELECT ai_parse_document(binary_content) AS parsed
FROM bronze_raw_invoice_documents;

-- Step 2: Extract structured fields from parsed text
SELECT ai_extract(
  parsed:content::STRING,
  ARRAY[
    'invoice_number', 'vendor_name', 'vendor_gstin',
    'invoice_date', 'due_date', 'po_reference',
    'subtotal', 'cgst', 'sgst', 'total_amount',
    'bank_account_number', 'ifsc_code'
  ]
) AS extracted_fields
FROM silver_parsed_invoices;
```

**Validation:** Extracted `total_amount` is reconciled against the ERP-sourced amount (±2% tolerance). Discrepancies are flagged as `EXTRACTION_MISMATCH` and quarantined for human review.

### 6.2 Genie AI Analyst

A single Genie Space is attached to all 9 Gold tables (`gold_dim_vendor`, `gold_fact_invoices`, `gold_fact_payments`, `gold_dim_customer`, `gold_fact_sales`, `gold_fact_collections`, `gold_fact_gl`, `gold_fact_trial_balance`, `finance_kpis`) plus natural language finance instructions. Finance users query in plain English — no SQL required.

The Genie Space is **created and configured automatically** by the ETL job (notebooks 07 and 08) — it is not a manual setup step.

### 6.3 Multi-Agent AI Chat (LangGraph + Claude)

The conversational AI sidebar in the app connects to a **deployed MAS (Model-Agnostic Supervisor) endpoint** built with LangGraph:

```python
from langchain_databricks.genie import GenieTool
from langgraph.prebuilt import create_react_agent

genie_tool = GenieTool(space_id=genie_space_id)

agent = create_react_agent(
    model=ChatDatabricks(endpoint="databricks-claude-sonnet-4-5"),
    tools=[genie_tool],
    state_modifier=finance_system_prompt,
)
```

The agent is registered in Unity Catalog (`fna_control_tower.finance_and_accounting.mas_agent`) and deployed as a serving endpoint via MLflow (`mas-2dcd8d5a-endpoint`). When a user asks a finance question in the app, the request goes to this endpoint; the LangGraph ReAct loop calls GenieTool, which queries the Genie Space and returns a grounded, data-backed answer.

---

## 7. Finance Operations App

**URL:** https://fna-control-tower-7405605456174026.6.azure.databricksapps.com

The app is hosted on Databricks Apps (serverless, zero-infrastructure). Authentication is handled by the Apps proxy, which injects `x-forwarded-access-token` and `x-forwarded-email` headers into every request — the backend reads user identity from these without any additional OAuth plumbing.

### Three Finance Tabs

| Tab | Live Data Feed | Key Actions |
|---|---|---|
| **AP Operations** | Invoice queue via SSE (`/stream/p2p`) | Approve / Reject exceptions, logged to Lakebase |
| **AR Operations** | AR aging via SSE (`/stream/o2c`) | Log collection calls (PTP / Dispute / Voicemail / Escalate) |
| **GL Operations** | JE validation via SSE (`/stream/r2r`) | Close checklist, variance review |

### SSE Streaming Architecture

```
React frontend                    FastAPI backend              Delta Gold tables
─────────────────────────────────────────────────────────────────────────────────
EventSource(/stream/p2p)   →→→   databricks-sql-connector  →→→  gold_fact_invoices
                                 SELECT * ORDER BY date DESC
                                 emit per record (0.5–1.5s delay)
                                 JSON: {type, match_status, vendor, amount}
```

### Lakebase Operational State

The app uses Lakebase (managed Postgres instance `finance-ops-db`) for all transactional writes — approval decisions, call logs, chat history. This keeps ACID write semantics completely separate from the analytical Delta tables.

| Table | What It Stores |
|---|---|
| `ap_approvals` | Invoice approval/rejection decisions with reason and approver |
| `ar_call_logs` | Collection call outcomes (PTP date, notes, logged-by) |
| `chat_history` | All AI chat turns with session_id, routing info, timestamp |

### Invoice Drawer

Clicking an invoice ID in the AP tab or chat opens a slide-in drawer showing:
- ERP metadata: vendor, invoice number, amounts, status, payment terms
- Quarantine reason badge (AMOUNT_MISMATCH, NO_PO_REFERENCE, EXTRACTION_MISMATCH, etc.)
- Data source badge: `ERP + PDF` or `ERP System`
- PDF viewer: dynamically generated from ERP data via `reportlab`
- Download button for offline review

---

## 8. Conversational AI — Multi-Agent System

### Architecture

```
User question (POST /api/chat)
      │
      ▼
chat.py — load last 10 turns from Lakebase for this session
      │
      ▼
POST /serving-endpoints/mas-2dcd8d5a-endpoint/invocations
      {"messages": [system_prompt, ...history, current_question]}
      │
      ▼
LangGraph ReAct Agent (Claude Sonnet 4.5 via FMAPI)
      │  thinks about the question, decides to call GenieTool
      ▼
GenieTool → POST /api/2.0/genie/spaces/{id}/start-conversation
      │  Genie runs SQL on Gold tables, returns answer with evidence
      ▼
Agent synthesises final answer
      │
      ▼
Response streamed back → Frontend renders as markdown
Save turn to Lakebase chat_history
```

### Session-Based Context Memory

```
1. Frontend generates session_id = crypto.randomUUID() on panel mount
2. Every POST /api/chat sends {question, active_tab, session_id}
3. Backend loads last 10 Q&A pairs from Lakebase for this session
4. Prior turns injected into the MAS endpoint as conversation history
5. After response: turn persisted back to Lakebase chat_history
6. History drawer: /api/my-sessions → resume any past session
```

**Multi-turn example:**
- Q1: "What is the total invoice spend?" → Genie queries gold_fact_invoices → ₹147Cr
- Q2: "Which of **those vendors** have compliance below 80%?" → resolves from Q1 ✅
- Q3: "Switch to AR — top overdue customers?" → Genie queries gold_fact_collections ✅
- Q4: "DSO for **that top customer**?" → resolves "that customer" from Q3 ✅

### Response Handling

The `_extract_mas_answer()` function in `chat.py` handles the full range of Agents API response formats:
- `{"output": {"messages": [{"type": "ai", "content": "..."}]}}`
- `{"output": "..."}` (string output)
- `{"choices": [{"message": {"content": "..."}}]}` (OpenAI-compatible)
- Tool call intermediates filtered out (`<function_calls>` stripped)

If the MAS endpoint returns a complete answer, it is streamed to the frontend in 40-character chunks with 20ms delay. If not (e.g. endpoint not deployed), the backend falls back to direct SQL + Claude.

---

## 9. Data Quality & Governance

### DLT Expectations

| Table | Expectation | Action on Fail |
|---|---|---|
| `bronze_p2p_invoices` | `valid_amount`: amount > 0 | DROP |
| `bronze_p2p_invoices` | `has_vendor`: vendor_id IS NOT NULL | DROP |
| `bronze_journal_entries` | `balanced_entry`: abs(debit-credit) < 0.01 | QUARANTINE → `bronze_je_exceptions` |
| `silver_p2p_invoices` | `no_future_invoices`: invoice_date <= today | WARN |
| `silver_p2p_invoices` | `valid_match_status`: status IN (...) | DROP |

### 3-Way Match Quarantine

Invoices that fail 3-way match are not dropped — they are preserved in `silver_p2p_invoices` with a `quarantine_reason` flag. The Finance Operations App surfaces these as the **exception queue** for human review. Approvals/rejections are written back to Lakebase, creating a complete audit trail.

### Unity Catalog Lineage

Every Gold table cell is traceable back to the source file:
```
Source file (UC Volume)
  → bronze_raw_invoice_documents  (Auto Loader)
    → silver_invoice_extractions  (DLT + ai_parse_document)
      → gold_fact_invoices        (Gold transformation)
        → Genie AI query result
```

---

## 10. Key Metrics

### Data Volume (Demo Dataset)

| Table | Rows | Description |
|---|---|---|
| `bronze_vendors` | 100 | Vendor master with GSTIN |
| `bronze_customers` | 150 | Customer master, 5 segments |
| `bronze_po_header` | 500 | Purchase orders, 8 categories |
| `bronze_p2p_invoices` | 577 | Includes ~5% intentional duplicates |
| `bronze_journal_entries` | 2,000 | 50 GL accounts |
| `bronze_raw_invoice_documents` | 200 | Text invoice files in UC Volume |
| `silver_p2p_invoices` | 548 | Post-dedup, with match_status |
| `silver_invoice_extractions` | 200 | AI-extracted structured fields |
| `gold_fact_invoices` | 548 | With aging, DPO, match metadata |
| `gold_fact_payments` | 138 | Confirmed payments |
| `gold_fact_sales` | 600 | Customer invoices |
| `gold_fact_collections` | 253 | Collection records with DSO |
| `gold_fact_gl` | 3,430 | General ledger entries |
| `gold_fact_trial_balance` | 350 | Trial balance by period |

### Live Business KPIs

| KPI | Value |
|---|---|
| Total invoices | 548 |
| Three-way matched (touchless) | 186 — **33.9%** |
| Exceptions requiring review | 193 |
| Average DPO | 37.5 days |
| Payment run staged | ₹147 Cr |
| Overdue AR | ₹489 Cr |

---

## 11. Tech Stack

### Data Platform

| Component | Technology |
|---|---|
| Data lakehouse | Azure Databricks (`adb-7405605456174026`) |
| Table format | Delta Lake |
| Ingestion pipelines | Delta Live Tables (DLT), serverless |
| Data governance | Unity Catalog |
| AI SQL functions | `ai_parse_document()`, `ai_extract()` (built-in) |
| Natural language analytics | Databricks Genie |
| SQL Warehouse | Serverless (`ff4426268a522c62`) |

### Application Layer

| Component | Technology |
|---|---|
| App hosting | Databricks Apps (serverless, OAuth SSO) |
| Frontend | React 19 + TypeScript + Tailwind CSS v4 + Framer Motion |
| Backend | FastAPI + uvicorn + sse-starlette |
| DB connector | `databricks-sql-connector` |
| Operational DB | Lakebase (managed Postgres, `finance-ops-db`) |

### AI Layer

| Component | Technology |
|---|---|
| LLM | Claude Sonnet 4.5 (`databricks-claude-sonnet-4-5` via FMAPI) |
| Agent framework | LangGraph `create_react_agent` |
| Genie integration | `GenieTool` from `langchain-databricks` |
| Model registry | Unity Catalog (`fna_control_tower.finance_and_accounting.mas_agent`) |
| Serving endpoint | MLflow / Databricks Model Serving (`mas-2dcd8d5a-endpoint`) |
| Session memory | Lakebase `chat_history` — last 10 turns injected per request |

---

## 12. Quick Reference

| Resource | Value |
|---|---|
| Workspace | `https://adb-7405605456174026.6.azuredatabricks.net` |
| CLI Profile | `fevm-fna` |
| Catalog · Schema | `fna_control_tower` · `finance_and_accounting` |
| UC Volume (Invoice PDFs) | `/Volumes/fna_control_tower/finance_and_accounting/invoice_pdfs/` |
| App URL | `https://fna-control-tower-7405605456174026.6.azure.databricksapps.com` |
| App Service Principal | `c07e4742-890d-4c54-bcd1-b8cc257b6253` |
| SQL Warehouse ID | `ff4426268a522c62` |
| ETL Job ID | `981786627277818` |
| MAS Supervisor Endpoint | `mas-2dcd8d5a-endpoint` |
| Lakebase Instance | `finance-ops-db` |

---

## 13. Repo Structure

```
fna_control_tower/
├── README.md                          ← This file
├── databricks.yml                     ← Bundle definition (targets: fevm)
│
├── resources/                         ← Bundle resource YAMLs
│   ├── fna_app.yml                    ← Databricks App (env vars + resource bindings)
│   ├── fna_warehouse.yml              ← SQL Warehouse (serverless, auto_stop_mins: 0)
│   ├── fna_etl_job.yml                ← ETL workflow (9 tasks: data → Genie → MAS)
│   └── fna_dlt_pipeline.yml           ← Delta Live Tables pipeline
│
├── app/                               ← Finance Operations App
│   ├── app.yaml                       ← App runtime config: env vars + resource bindings
│   ├── backend/
│   │   ├── main.py                    ← FastAPI: metrics, SSE streams, invoice PDF, alerts
│   │   ├── chat.py                    ← MAS endpoint call + fallback SQL+Claude
│   │   ├── lakebase.py                ← Postgres: session memory, approvals, call logs
│   │   ├── db.py                      ← Delta SQL: KPI queries, payment run, aging
│   │   ├── streams.py                 ← SSE generators for P2P / O2C / R2R
│   │   ├── escalate.py                ← SQL Alerts V2: create + arm alert for CFO
│   │   └── config.py                  ← Workspace host, token, catalog/schema
│   └── frontend/src/
│       ├── App.tsx                    ← Root: tab routing, user identity (/api/me)
│       └── components/
│           ├── APTab.tsx              ← AP Operations: invoice queue, exception drawer
│           ├── ARTab.tsx              ← AR Operations: aging, collection call modal
│           ├── GLTab.tsx              ← GL Operations: close checklist, JE feed
│           ├── AIChatPanel.tsx        ← Multi-agent chat: markdown, session history
│           ├── InvoiceDrawer.tsx      ← Invoice PDF viewer: ERP metadata + PDF iframe
│           ├── GreetingBanner.tsx     ← Personalised greeting with dismiss
│           └── KPICard.tsx            ← Metric display component
│
└── notebooks/                         ← Databricks workspace notebooks
    ├── 00_Setup_and_Data_Generation   ← Synthetic data: 577 invoices, 150 customers, 2000 JEs
    ├── 01_DLT_Pipeline                ← Bronze + Silver via DLT with expectations
    ├── 02_Gold_Layer_P2P              ← gold_dim_vendor, gold_fact_invoices, gold_fact_payments
    ├── 03_Gold_Layer_O2C              ← gold_dim_customer, gold_fact_sales, gold_fact_collections
    ├── 04_Gold_Layer_R2R              ← gold_fact_gl, gold_fact_trial_balance
    ├── 05_Invoice_AI_Processing       ← ai_parse_document + ai_extract (runs outside DLT)
    ├── 06_Create_KPI_View             ← Unified finance_kpis view across P2P / O2C / R2R
    ├── 07_Create_Genie_Space          ← Creates Genie Space via REST API (idempotent)
    ├── 08_Configure_Genie_Space       ← Attaches Gold tables + finance instructions to Genie
    └── 09_Deploy_MAS_Supervisor       ← Registers LangGraph agent + deploys serving endpoint
```

---

## 14. Setup & Deployment

The entire platform is deployed via a **Databricks Asset Bundle** (`databricks bundle deploy`). The ETL job is a 9-task orchestrated workflow that handles everything from synthetic data generation through to deploying the MAS supervisor endpoint.

### Prerequisites

- `databricks` CLI authenticated to the target workspace
  ```bash
  databricks auth login --host adb-7405605456174026.6.azuredatabricks.net --profile fevm-fna
  ```
- Python 3.10+ for any local helper scripts

### Deployment Steps

**Step 1 — Bundle deploy** (creates App, Warehouse, ETL job, DLT pipeline):
```bash
databricks bundle deploy --target fevm --profile fevm-fna
```

**Step 2 — Run the ETL job** (one command — handles all 9 tasks automatically):
```bash
databricks jobs run-now --job-id 981786627277818 --profile fevm-fna
```

The 9-task ETL workflow runs in order:

| Task | What It Does |
|---|---|
| `data_generation` | Generate synthetic Bronze tables + UC Volume invoice files |
| `dlt_bronze_to_silver` | Run DLT pipeline: dedup, 3-way match, AI extraction |
| `gold_p2p` *(parallel)* | Build P2P Gold tables |
| `gold_o2c` *(parallel)* | Build O2C Gold tables |
| `gold_r2r` *(parallel)* | Build R2R Gold tables |
| `create_kpi_view` | Build unified `finance_kpis` view |
| `create_genie_space` | Create Genie Space via API; publish `genie_space_id` as task value |
| `configure_genie_space` | Attach all 9 Gold tables + finance instructions to Genie |
| `deploy_mas_supervisor` | Register LangGraph+GenieTool agent in UC; deploy serving endpoint |

**Step 3 — Deploy the app** (picks up the new MAS endpoint automatically):
```bash
databricks bundle deploy --target fevm --profile fevm-fna
# or update the app in-place:
databricks apps deploy fna-control-tower --source-code-path app/ --profile fevm-fna
```

### Key Design Decisions

| Decision | Reason |
|---|---|
| `auto_stop_mins: 0` on warehouse | Prevents cold-start latency during demo; warehouse stays warm |
| UC grants in `setup.py` | App service principal is not auto-granted access; must be explicit |
| `ai_parse_document` outside DLT | Built-in AI functions require cluster-side inference context unavailable in DLT |
| Genie Space created via API (notebook 07) | Genie Spaces are not a DAB-supported resource type; REST API is the only option |
| Genie Space ID via `taskValues` | `dbutils.jobs.taskValues.set/get` passes the space ID from notebook 07 to 08 and 09 without hardcoding |
| LangGraph ReAct + GenieTool | Single GenieTool covers all Gold tables; no need for separate P2P/O2C/R2R sub-agents |
| `mas_setup` environment for notebook 09 | `langchain-databricks`, `langgraph`, `mlflow` not on default serverless env; pinned in environment spec |
| `default` environment for notebooks 07/08 | These notebooks use inline `%pip install databricks-sdk` — no environment package needed |
| MAS endpoint timeout 120s | Genie sub-agent queries can take 30–60s to run; 60s was too short |

---

## 15. Demo Walkthrough

### Recommended Script (20 minutes)

**Act 1 — Frame the Problem (2 min)**
Open the app. Show the header KPIs: 548 invoices, 193 exceptions, ₹489Cr overdue AR.
> *"This is the state of finance operations without a unified platform. 193 invoices need human attention. ₹489Cr is sitting uncollected. The team doesn't know which ones to prioritise."*

**Act 2 — Live Operations (8 min)**
- Click **Start** on AP tab → invoices stream in with `match_status` badges
- Point out green `THREE_WAY_MATCHED` (no touch needed) vs orange `AMOUNT_MISMATCH` vs red `NO_PO_REFERENCE`
- Open an exception → invoice drawer shows ERP metadata, quarantine reason, generated PDF
- Approve with reason → logged to Lakebase with timestamp and approver identity
- Switch to AR tab → overdue customer queue → log a Promise-to-Pay call
- Switch to GL tab → close checklist → JE validation feed showing balanced vs. exception entries

**Act 3 — Conversational AI (5 min)**
- Ask: *"Which invoices are at risk of late payment this week?"*
- Show: Genie executes SQL on gold tables, agent returns grounded answer with vendor names and amounts
- Ask follow-up: *"Which of those vendors have compliance below 80%?"*
- Show: answer resolves "those vendors" from prior turn context — no need to repeat the question
- Open history drawer → show past sessions → click to resume any thread

**Act 4 — Platform Depth (5 min)**
- Open Unity Catalog → data lineage from `gold_fact_invoices` back to source invoice file
- Open DLT pipeline → show expectations and the quarantine table for bad records
- Open `silver_invoice_extractions` → show AI-extracted GSTIN, bank account, amounts next to ERP data
- Show Genie Space directly → ask the same finance question — same Gold tables, same answer

### Key Talking Points

1. **No custom model required** — `ai_parse_document()` and `ai_extract()` are built-in SQL functions. Finance teams don't need an ML team.

2. **SOX-ready by design** — DLT Expectations enforce explicit quality contracts. Unity Catalog tracks every transformation. The audit trail is automatic, not retrofitted.

3. **Finance users self-serve** — Genie and the AI chat let controllers and CFOs query data in plain English. No ticket to the data team, no waiting for a scheduled report.

4. **Scales without rearchitecting** — From 548 invoices to 5 million: same Delta tables, same DLT pipeline, serverless autoscaling. No infrastructure changes.

5. **One platform** — Ingestion, quality enforcement, AI, analytics, the app, operational database, and the AI agent all run on Databricks. No separate ETL tool, no separate AI platform, no separate app hosting.

---

*Built by Akash S, Databricks Field Engineering*
*Platform: Azure Databricks `adb-7405605456174026` · Catalog: `fna_control_tower` · April 2026*
