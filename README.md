# Finance Operations Intelligence — Databricks Lakehouse Demo

> **A production-grade, end-to-end Finance & Accounting platform on Azure Databricks** — covering Procure-to-Pay (P2P), Order-to-Cash (O2C), and Record-to-Report (R2R) with AI-powered invoice processing, a real-time operations app, and conversational analytics.

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
14. [Demo Walkthrough](#14-demo-walkthrough)

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
ERP-locked analytics               →   Natural language queries (Genie / AI Chat)
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
| **Natural language analytics** | Genie AI Analyst | Finance users query in English; no SQL knowledge required |
| **Real-time operations app** | Databricks Apps + SSE | OAuth SSO, serverless hosting, streamed live data |
| **Operational state** | Lakebase (managed Postgres) | ACID writes for AP approvals, AR call logs, chat history |
| **Intelligent AI routing** | Claude via FMAPI (multi-agent) | Supervisor routes queries to domain-specific Genie spaces |

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
└──────────────┬─────────────────────────────┬───────────────────────┘
               │                             │
               ▼                             ▼
┌──────────────────────┐       ┌─────────────────────────────────────┐
│  GENIE AI ANALYST    │       │  FINANCE OPERATIONS APP             │
│  Natural language    │       │  React + FastAPI on Databricks Apps │
│  queries on all 9    │       │  AP · AR · GL tabs · SSE streaming  │
│  Gold tables         │       │  Lakebase for operational state     │
│  No SQL required     │       │  Multi-agent AI chat sidebar        │
└──────────────────────┘       └─────────────────────────────────────┘
               │                             │
               └──────────────┬──────────────┘
                              ▼
                 ┌────────────────────────┐
                 │  MULTI-AGENT AI CHAT   │
                 │  Claude Supervisor     │
                 │  (FMAPI tool_use mode) │
                 │  ↓ routes to          │
                 │  P2P · O2C · R2R       │
                 │  Genie sub-agents      │
                 └────────────────────────┘
```

### Governance Layer (Unity Catalog)

All tables live in a single 3-part namespace:
```
akash_s_demo.finance_and_accounting.<table_name>
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

Databricks built-in SQL functions — no custom model deployment, no API keys, no prompt engineering.

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

**Validation:** Extracted `total_amount` is reconciled against the ERP-sourced amount (±2% tolerance). High-confidence extractions are approved for straight-through processing.

### 6.2 Multi-Agent AI Chat

```
User question
      │
      ▼
Claude Supervisor (FMAPI, tool_use mode)
  Sees: system prompt + last 10 conversation turns (from Lakebase)
  Tool choice: FORCED (must call exactly one tool)
      │
      ├──► call_p2p_agent   →  P2P Genie space  →  gold_dim_vendor,
      │                                             gold_fact_invoices,
      │                                             gold_fact_payments
      │
      ├──► call_o2c_agent   →  O2C Genie space  →  gold_dim_customer,
      │                                             gold_fact_sales,
      │                                             gold_fact_collections
      │
      ├──► call_r2r_agent   →  R2R Genie space  →  gold_fact_gl,
      │                                             gold_fact_trial_balance
      │
      └──► call_full_agent  →  Full space        →  All 9 Gold tables
```

**Session memory:** Every Q&A turn is persisted to Lakebase `chat_history`. Prior turns are loaded on each request and injected into the supervisor's context — enabling multi-turn references like "those vendors" and "that customer from earlier".

---

## 7. Finance Operations App

**URL:** https://audit-control-app-984752964297111.11.azure.databricksapps.com

### Three Finance Tabs

| Tab | Live Data Feed | Key Actions |
|---|---|---|
| **AP Operations** | Invoice queue via SSE (`/stream/p2p`) | Approve / Reject exceptions, logged to Lakebase |
| **AR Operations** | AR aging via SSE (`/stream/o2c`) | Log collection calls (PTP/Dispute/Voicemail/Escalate) |
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

| Table | What It Stores |
|---|---|
| `ap_approvals` | Invoice approval/rejection decisions with reason and approver |
| `ar_call_logs` | Collection call outcomes (PTP date, notes, logged-by) |
| `chat_history` | All AI chat turns with session_id, routing info, SQL used |

---

## 8. Conversational AI — Multi-Agent System

### Session-Based Context Memory

```
1. Frontend generates session_id = crypto.randomUUID() on panel mount
2. Every POST /api/chat sends {question, active_tab, session_id}
3. Backend loads last 10 Q&A pairs from Lakebase for this session
4. Prior turns injected into Claude's context before the current question
5. After response: turn persisted back to Lakebase chat_history
6. History drawer: /api/my-sessions → resume any past session
```

**Multi-turn example:**
- Q1: "What is the total invoice spend?" → P2P Agent → ₹147Cr
- Q2: "Which of **those vendors** have compliance below 80%?" → resolves from Q1 ✅
- Q3: "Switch to AR — top overdue customers?" → O2C Agent (cross-domain shift) ✅
- Q4: "DSO for **that top customer**?" → resolves "that customer" from Q3 ✅

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
| Data lakehouse | Azure Databricks (`adb-984752964297111`) |
| Table format | Delta Lake |
| Ingestion pipelines | Delta Live Tables (DLT), serverless |
| Data governance | Unity Catalog |
| AI SQL functions | `ai_parse_document()`, `ai_extract()` (built-in) |
| Natural language analytics | Databricks Genie |
| SQL Warehouse | Serverless (`148ccb90800933a1`) |

### Application Layer

| Component | Technology |
|---|---|
| App hosting | Databricks Apps (serverless, OAuth SSO) |
| Frontend | React 19 + TypeScript + Tailwind CSS v4 + Framer Motion |
| Backend | FastAPI + uvicorn + sse-starlette |
| DB connector | `databricks-sql-connector` |
| Operational DB | Lakebase (managed Postgres, `ff6c333c`) |

### AI Layer

| Component | Technology |
|---|---|
| LLM | Claude (`databricks-claude-sonnet-4-5` via FMAPI) |
| Supervisor pattern | `tool_use` mode with forced tool choice (`tool_choice: any`) |
| Sub-agents | Genie API (`/api/2.0/genie/spaces/{id}/start-conversation`) |
| Session memory | Lakebase `chat_history` — last 10 turns injected as context |

---

## 12. Quick Reference

| Resource | Value |
|---|---|
| Workspace | `https://adb-984752964297111.11.azuredatabricks.net` |
| CLI Profile | `field-east` |
| Catalog · Schema | `akash_s_demo` · `finance_and_accounting` |
| App URL | `https://audit-control-app-984752964297111.11.azure.databricksapps.com` |
| App Service Principal | `6ff35bc8-c861-4aec-abfa-db8d93e4ef9e` |
| DLT Pipeline ID | `20b7318a-de2e-4d35-9a08-03fccc7a4ff9` |
| Genie Space ID | `01f122c95c741815919b6457017f0899` |
| SQL Warehouse ID | `148ccb90800933a1` |
| Lakebase Instance ID | `ff6c333c-a93f-4e81-95da-cfbcaeee90e6` |
| Tech Demo Deck (25 slides) | https://docs.google.com/presentation/d/19CQUoGIXvxKdILrdjtMtIZdcd2tEh7_cetLxGKdk4m4/edit |

---

## 13. Repo Structure

```
finance & accounting demo/
├── README.md                          ← This file
│
├── app/                               ← Finance Operations App
│   ├── app.yaml                       ← Databricks Apps config + Lakebase resource bindings
│   ├── backend/
│   │   ├── main.py                    ← FastAPI: metrics, SSE streams, chat, Lakebase endpoints
│   │   ├── chat.py                    ← Multi-agent supervisor (Claude tool_use + Genie sub-agents)
│   │   ├── lakebase.py                ← Postgres: session memory, approvals, call logs
│   │   ├── db.py                      ← Delta SQL: KPI queries, payment run, aging
│   │   ├── streams.py                 ← SSE generators for P2P / O2C / R2R
│   │   └── config.py                  ← Workspace host, token, catalog/schema
│   └── frontend/src/
│       ├── App.tsx                    ← Root: tab routing, user identity (/api/me)
│       └── components/
│           ├── APTab.tsx              ← AP Operations: invoice queue, exception drawer, approvals
│           ├── ARTab.tsx              ← AR Operations: aging, collection call modal
│           ├── GLTab.tsx              ← GL Operations: close checklist, JE feed
│           ├── AIChatPanel.tsx        ← Multi-agent chat: markdown renderer, session history drawer
│           ├── GreetingBanner.tsx     ← Personalised greeting with dismiss
│           └── KPICard.tsx            ← Metric display component
│
└── notebooks/                         ← Databricks workspace notebooks
    ├── 00_Setup_and_Data_Generation   ← Synthetic data: 577 invoices, 150 customers, 2000 JEs
    ├── 01_DLT_Pipeline                ← Bronze + Silver via DLT with expectations
    ├── 02_Gold_Layer_P2P              ← gold_dim_vendor, gold_fact_invoices, gold_fact_payments
    ├── 03_Gold_Layer_O2C              ← gold_dim_customer, gold_fact_sales, gold_fact_collections
    ├── 04_Gold_Layer_R2R              ← gold_fact_gl, gold_fact_trial_balance
    ├── 05_Invoice_AI_Processing       ← ai_parse_document + ai_extract → silver_invoice_extractions
    ├── 06_Genie_Space_Setup           ← Table descriptions and sample questions
    ├── 07_Create_Genie_Space          ← Created Genie space via SDK
    └── 08_Configure_Genie_Space       ← Added instructions and curated questions
```

---

## 14. Demo Walkthrough

### Recommended Script (20 minutes)

**Act 1 — Frame the Problem (2 min)**
Open the app. Show the header KPIs: 548 invoices, 193 exceptions, ₹489Cr overdue AR.
> *"This is the state of finance operations without a unified platform. 193 invoices need human attention. ₹489Cr is sitting uncollected. The team doesn't know which ones to prioritise."*

**Act 2 — Live Operations (8 min)**
- Click **Start** on AP tab → invoices stream in with `match_status` badges
- Point out green `THREE_WAY_MATCHED` (no touch needed) vs orange `AMOUNT_MISMATCH` vs red `NO_PO_REFERENCE`
- Open an exception → show AI-extracted fields vs ERP fields side by side → Approve with reason
- Switch to AR tab → overdue queue → log a Promise-to-Pay call
- Switch to GL tab → close checklist → JE validation feed

**Act 3 — Conversational AI (5 min)**
- Ask: *"Which invoices are at risk of late payment this week?"*
- Show: routing badge (Supervisor → P2P Agent → Genie), bold vendor names, SQL accordion
- Ask follow-up: *"Which of those vendors have compliance below 80%?"*
- Show: answer resolves "those vendors" from context — no need to repeat
- Open history drawer → show past sessions → click to resume any thread

**Act 4 — Platform Depth (5 min)**
- Open Unity Catalog → data lineage from `gold_fact_invoices` back to source invoice file
- Open DLT pipeline → show expectations and the quarantine table for bad records
- Open `silver_invoice_extractions` → show AI-extracted GSTIN, bank account, amounts next to ERP data

### Key Talking Points

1. **No custom model required** — `ai_parse_document()` and `ai_extract()` are built-in SQL functions. Finance teams don't need an ML team.

2. **SOX-ready by design** — DLT Expectations enforce explicit quality contracts. Unity Catalog tracks every transformation. The audit trail is automatic, not retrofitted.

3. **Finance users self-serve** — Genie and the AI chat let controllers and CFOs query data in plain English. No ticket to the data team, no waiting for a scheduled report.

4. **Scales without rearchitecting** — From 548 invoices to 5 million: same Delta tables, same DLT pipeline, serverless autoscaling. No infrastructure changes.

5. **One platform** — Ingestion, quality enforcement, AI, analytics, the app, and the operational database all on Databricks. No separate ETL tool, no separate AI platform, no separate app hosting.

---

*Built by Akash S, Databricks Field Engineering*
*Platform: Azure Databricks `adb-984752964297111` · Catalog: `akash_s_demo` · March 2026*
