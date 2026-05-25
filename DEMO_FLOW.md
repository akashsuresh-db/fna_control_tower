# F&A Control Tower — Demo Flow

**Buildathon 2K26 · Team 03**
**App:** https://finance-accounting-demo-7474657218573364.aws.databricksapps.com/
**Pipeline:** [Finance Accounting DLT](https://fevm-fna-control-tower.cloud.databricks.com/pipelines/4ed02504-99c3-401c-b1a5-6663310a2384)
**Genie space:** `01f14f375ead12d5b6f67bf24be02a07` (Finance Test)

> A 15-minute demo script mapped 1:1 to the buildathon deck. Each Act maps to specific slides and tells the audience what to look at, how to click through, and **why each moment matters**. Numbers cited below are the live state — refresh by re-running the pipeline if you need them current.

---

## Act 0 · Open the deck and the app (1 minute)

**Slide 1 — Title** *(F&A Control Tower · Team 03)*
Open the app URL in one Chrome tab, the deck in another, and (kept for later) the [DLT pipeline](https://fevm-fna-control-tower.cloud.databricks.com/pipelines/4ed02504-99c3-401c-b1a5-6663310a2384) in a third tab. Don't switch yet.

**Slide 2 — What are we trying to solve?**
Don't read the slide. State the four frictions in one sentence each, then say:

> *"In the next 12 minutes I'll show you the same four frictions resolved live — manual invoice processing, stale AR, slow month-end close, and the fragmented data underneath that gates AI. Everything you see is real data running through a real Databricks Spark Declarative Pipeline. No mocks."*

---

## Act 1 · The AP nightmare, solved (4 minutes)

> **Slide 3 — Three workflows**, P2P pillar
> **Slide 5 — 75-85% cost reduction, 98% faster 3-way match**

### 1A · Open the AP Operations tab

Point at the **summary card at the top** ("Today's AP priorities"). Read one bullet aloud — e.g. *"169 MISSING_GRN and 107 AMOUNT_MISMATCH exceptions blocking touchless processing."*

> *"This is Claude reading the actual live gold table and synthesising what an AP lead needs to look at first. It refreshes on tab switch. No analyst built it."*

Point at the KPI strip:
- **TOTAL INVOICES** 548 · **3-WAY MATCHED** 187 · **EXCEPTIONS** 192 · **TOUCHLESS RATE** 34.1%

> *"187 of 548 went through with zero human touch. That number on Slide 3 — '70 to 85% touchless' — is where this scales to."*

### 1B · Click "Start Processing"

Invoices stream in. As they do:

| What to point at | What to say |
|---|---|
| Green `3-Way Matched` badges | *"These are auto-released to payment. Touchless. Today's incumbent process takes 2-3 days; ours took 4 seconds per invoice."* |
| The 📎 paperclip icon next to some rows | *"This paperclip means the source PDF lives in UC Volume — same byte image the AI extraction read. Click any paperclipped row."* |
| Orange `Amount Mismatch` / red `No PO Reference` badges | *"Every non-3-way invoice surfaces here automatically. The pipeline classifies these by rule, not by an analyst's CASE WHEN in a SQL script."* |

### 1C · Click a paperclipped exception (recommended: search the queue for one with `AMOUNT_MISMATCH`)

The exception drawer opens. Walk through it top to bottom:

1. **Exception type + SLA Clock** — 24h or 4h target shows up automatically
2. Click **"Verify before approve"** button (blue, with shield icon)

The `AIvsERPCard` slides in with 8 named credibility checks. Read out 2-3 of the checks aloud — especially **Invoice ↔ PO total**, **ERP vendor ↔ PDF vendor**, and **Duplicate payment check**. Highlight the **REJECT / HOLD / APPROVE** recommendation at the bottom.

> *"Eight pre-approval checks in one click. Every line is auditable. If the AP clerk had to do this by hand they'd open the ERP, the PDF, the PO, the vendor master, and the GRN — minimum five windows. Here it's one button, one panel, one decision."*

### 1D · Click "Show PDF" on the same invoice

The PDF opens in a new tab. Show the footer line:

> *"Source: UC Volume · raw_invoices/INV000xxx.pdf · Finance Operations Platform"*

> *"This is the exact byte image stored in Unity Catalog. We're not regenerating it on the fly — the app fetched it via the Files API. Watch this:"*

(Optional, if you have a SQL editor open) run:
```sql
SELECT md5(content) FROM read_files('/Volumes/.../raw_invoices', format=>'binaryFile')
WHERE path LIKE '%INV000011.pdf';
-- compare to the MD5 the browser shows in DevTools
```
Same hash. **That's UC end-to-end traceability** — the exact PDF the AI extracted from is the one a CFO can pull during audit.

---

## Act 2 · AR collections + GL close (3 minutes)

> **Slide 3** — O2C and R2R pillars
> **Slide 5** — *50-70% faster month-end close*

### 2A · Switch to AR Operations tab

Point at the summary card — bullets now talk about overdue customers in days, top recovery candidates.

Point at KPIs:
- **AR Outstanding** ₹64.87 Cr · **DSO** 270 days · **CEI** 57.4% · **Overdue** 120 customers

> *"This is the AR sub-ledger — gold_fact_collections. 64 crores outstanding, average DSO 270 days. Collections team would normally see this weekly from an ERP export."*

Click an aging-90+ customer. Show the call modal: PTP / Dispute / Voicemail / Escalate. Pick PTP, set a date, submit.

> *"That promise-to-pay just went into Lakebase Postgres — operational state, not analytical. The call list reorders tomorrow based on it."*

### 2B · Switch to GL Operations tab

This is the punchline of the close-cycle story.

**First — point at the Sub-ledger ↔ GL reconciliation card:**

```
1100  Accounts Receivable [DR]   ₹64.87 Cr ↔ ₹64.87 Cr  Δ ₹0.00  ✓
2000  Accounts Payable    [CR]  ₹431.86 Cr ↔ ₹431.86 Cr  Δ ₹0.00  ✓
"All accounts tie out — loop closed ✓"
```

> *"This is the proof. AR and AP in the trial balance equal the sub-ledger totals to the rupee. Most finance shops have a delta here every period; we engineered the delta to zero by deriving these GL balances directly from sub-ledger sums in the pipeline. Click in and you see the source tables called out: `gold_fact_collections` and `gold_fact_invoices`."*

**Then — click "Show Trial Balance":**

Nine accounts: 1100 AR (₹64.87 Cr DR), 1200 Inventory, 1500 PPE, 2000 AP (₹431.86 Cr CR), 2500 LT Debt, 3100 Retained, 4100 Service Rev, 5100 Salaries, 5500 IT Expense.

> *"Sign convention is correct on all 9 — Assets/Expenses DR, Liabilities/Equity/Revenue CR. The TB total is intentionally not zero — it shows the working-capital imbalance from real sub-ledger pressure on AP. In an actual close, that delta is what FP&A explains; we surface it instead of hiding it."*

Click **"Start JE Validation"**. Journal entries stream into the feed.

> *"Continuous validation, not month-end-only. The Close Checklist on the right shrinks day-by-day."*

---

## Act 3 · Conversational AI (Genie + Multi-Agent Supervisor) (2 minutes)

> **Slide 4** — Conversational AI · Genie
> **Slide 6** — *CFO & Controller wants a single view of working capital without waiting for an analyst-built report*

### 3A · Open the Finance AI panel (right side)

Ask the prepared question:

> **"Give me a working capital snapshot for the CFO right now."**

The supervisor routes to Genie. Genie pulls the 6 working-capital accounts from `gold_fact_trial_balance` (curated list in the Genie instructions). Returns clean DR/CR with current values.

> *"This isn't an LLM hallucinating numbers — it's our multi-agent supervisor routing the question to Genie, which queries the exact same gold table the GL tab reads. Same row, same balance, same sign. The CFO and the AP clerk see the same truth."*

### 3B · Follow-up multi-turn

> **"Which vendors have compliance below 80%?"**

Routes to the P2P sub-agent → `gold_dim_vendor`. Names get bolded; SQL accordion shows the underlying query.

> *"Conversational SQL on governed data. No CSV export, no analyst hand-off."*

### 3C · Click an old chat in the session-history drawer

Show that the session resumes with full context (chat history is persisted in Lakebase).

> *"Operational state in Lakebase, analytical state in Delta. Same Databricks platform, both serverless."*

---

## Act 4 · The architecture proof (3 minutes)

> **Slide 4 — Architecture**
> **Slide 10 — The Art of Possible**

### 4A · Open the DLT pipeline graph

Switch to the tab with the pipeline open.

Point at the layered graph:
- **Bronze (10 tables)** — Auto Loader streams from `/raw_csv/` CSVs and `/raw_invoices/` PDFs. *"Real ingestion. Bronze doesn't read from another Delta table — it reads from files."*
- **Silver (6 tables)** — `silver_p2p_invoices` is the heart: 3-way match + 6 `@dlt.expect` predicates.
- **Gold (8 tables)** — AR/AP sub-ledgers, dimensions, and the trial balance derived from sub-ledgers.

### 4B · Click the "Data Quality" tab in the pipeline

Show the six business-rule expectations with live failed_records counts:

| Expectation | passed | failed |
|---|---|---|
| `has_po_reference` | 463 | 85 |
| `amount_matches_po` | 441 | 107 |
| `has_grn` | 238 | 310 |
| `has_vendor_gstin` | 548 | 0 |
| `not_critically_overdue` | 99 | 449 |
| `extraction_matches_erp` | 196 | 4 |

> *"These six predicates are the business rules. They drive both the pipeline's data-quality tab AND the exception_type column the AP queue reads. One source of truth — no drift between the pipeline operator and the app user."*

### 4C · Drill into `silver_invoice_exceptions` from the graph

Open the table and run a quick `SELECT exception_type, COUNT(*)`. Numbers tie within rounding to the failed_records above.

> *"Every invoice an accountant would touch is in this table. Every exception type maps back to a predicate the pipeline tested. SOX audit trail — done."*

### 4D · Open Unity Catalog → Lineage on `gold_fact_invoices`

Show the lineage tree all the way back to `/raw_csv/p2p_invoices/` and `/raw_invoices/*.pdf` in the volume.

> *"Cell-level provenance. Any number you see in the app traces to a source row that traces to a source file in Unity Catalog. That's the 'AI-ready data foundation' from Slide 6."*

### 4E · Open `silver_pdf_corruption_log`

Quick query: `SELECT * FROM silver_pdf_corruption_log`. Three rows with `corruption_ratio` and `corruption_pct`.

> *"For the demo we deterministically corrupted ~3% of PDFs by 5–15%. That's why `EXTRACTION_MISMATCH` actually fires — those are real signals, not coincidences. Deterministic per invoice_id, so the same demo runs the same way next time."*

---

## Act 5 · Business impact + Art of Possible (2 minutes)

> **Slide 5 — Business impact**
> **Slide 6 — Personas**
> **Slide 10 — Art of Possible**

Switch back to the app. With the AP tab visible, narrate the impact numbers from Slide 5:

| Slide claim | What proves it in the app |
|---|---|
| 75–85% cost reduction per invoice | The 187/548 touchless rate visible in the KPI strip |
| 98% faster 3-way matching | `silver_p2p_invoices` runs every pipeline cycle, classifies 548 invoices in seconds |
| 50–70% faster close | Live trial balance + sub-ledger ↔ GL recon card → no manual reconciliation step |

Then walk through personas on Slide 6:

> *"AP Manager — saw the exceptions queue, the Verify-before-approve panel. AR Lead — saw the prioritised collections list with PTP logging. CFO/Controller — saw the working capital snapshot from the chat panel. **Three personas, three tabs, one platform — designed to the workflow not retrofitted to it."*

Switch to Slide 10 (Art of Possible).

> *"What we built today is the bottom row of this slide — DLT data-quality contracts, P2P 3-way match, AI invoice extraction, real-time AR aging, the multi-agent chat, Lakebase approvals, sub-ledger reconciliation. The middle and top rows — touchless invoice routing, predictive payment timing, dispute root-cause analytics, conversational FP&A — they're a natural extension on the same data foundation. We didn't build them yet, but we're one sprint away from each."*

---

## Closing (30 seconds)

> *"Three workflows, one tab each. One platform underneath — Spark Declarative Pipelines, Unity Catalog, Lakebase, Foundation Model APIs. We didn't write a single line of glue between them — they composed natively. That's the controllership of tomorrow, and a finance team can run it without an MLE."*

App URL on screen. Q&A.

---

## Demo prep checklist (run before the demo)

| What | Where | Expected |
|---|---|---|
| Warehouse hot | SQL warehouse `b9f847c1ad87640f` | RUNNING; queries return <1s |
| App responsive | `/api/health` | `{"status":"healthy"}` |
| AR endpoint returns real data | `/api/metrics/o2c` | `total_outstanding ≈ ₹64.87 Cr` |
| GL recon endpoint | `/api/recon` | Both rows `tied: true`, `delta: 0` |
| Summary endpoint | `/api/summary/P2P` | 3-4 bullets in `bullets[]` |
| Verify endpoint | `/api/verify-invoice/INV000282` | recommendation `REJECT` |
| Chrome session | Logged in via Okta | Avatar visible top-right |
| Pipeline latest run | DLT update | `state: COMPLETED` |
| Genie space instructions | `01f14f375ead12d5b6f67bf24be02a07` | Replaced with `genie_instructions.md` content |

## Recovery plan during the demo

If the warehouse goes cold mid-demo (queries take >10s):
1. The summary cards show "Generating with Claude…" skeleton — keep talking through the architecture slide
2. The KPI strip will be blank — pivot to the DLT pipeline tab instead
3. If the queue won't stream, demo the AI panel only (it has its own conn pool)

If the app 502s: restart with `databricks apps start finance-accounting-demo` (~90 seconds), keep talking through architecture/personas.

If the entire pipeline is in INTERNAL_ERROR: previous tables are still queryable. The recon card will keep showing because it reads materialised tables. Don't trigger a refresh during the demo.

## Killer demo SQL snippets (paste into a SQL editor tab as backup proof)

```sql
-- 1. Sub-ledger ↔ GL tie-out (the recon card's source)
SELECT * FROM fna_control_tower_catalog.finance_and_accounting.gold_recon_subledger_vs_gl;

-- 2. Every business expectation's failed_records count from the pipeline event log
SELECT event_type, details:flow_progress.data_quality.expectations
FROM event_log("4ed02504-99c3-401c-b1a5-6663310a2384")
WHERE event_type = 'flow_progress' ORDER BY timestamp DESC LIMIT 1;

-- 3. AR sub-ledger total ties to the AR Operations tab headline
SELECT ROUND(SUM(balance_outstanding)/1e7, 2) AS ar_outstanding_cr
FROM fna_control_tower_catalog.finance_and_accounting.gold_fact_collections;
-- → 64.87

-- 4. PDF in UC Volume = PDF served by /api/invoice/{id}/pdf
SELECT md5(content) FROM read_files(
  '/Volumes/fna_control_tower_catalog/finance_and_accounting/raw_invoices',
  format => 'binaryFile')
WHERE path LIKE '%INV000011.pdf';

-- 5. Deterministically corrupted PDFs (3% by design)
SELECT invoice_id, vendor_name, corruption_pct
FROM fna_control_tower_catalog.finance_and_accounting.silver_pdf_corruption_log
ORDER BY ABS(corruption_pct) DESC;
```

## Components mentioned in the deck → where they live

| Slide claim | Built thing |
|---|---|
| "Spark Declarative Pipelines: Bronze → Silver → Gold" | `notebooks/01_DLT_Pipeline.py` + 6 `@dlt.expect` predicate constants |
| "AI invoice extraction" | `notebooks/05_Invoice_AI_Processing.py` using `ai_parse_document` + `ai_extract` |
| "3-way match" | `silver_p2p_invoices` `match_status` column, derived from PO + GRN |
| "Real-time AP screen" | `app/frontend/src/components/APTab.tsx` + SSE `/stream/p2p` |
| "Real-time AR aging" | `app/frontend/src/components/ARTab.tsx` + SSE `/stream/o2c` + `gold_fact_collections` |
| "Live trial balance" | `app/frontend/src/components/GLTab.tsx` + `gold_fact_trial_balance` |
| "Genie · Conversational AI" | MAS endpoint `mas-fna-supervisor` → Genie space `01f14f375ead12d5b6f67bf24be02a07` |
| "Lakebase approvals/logs/session memory" | `app/backend/lakebase.py` tables: `ap_approvals`, `ar_call_logs`, `chat_history` |
| "DLT data-quality contracts" | 6 `@dlt.expect` predicates surfaced on the Data Quality tab |
| "AI-ready data foundation" | Unity Catalog lineage from `/raw_csv/` and `/raw_invoices/` PDFs through every Gold table |

— end —
