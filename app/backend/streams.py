"""SSE stream generators for real-time finance event feeds."""
import asyncio
import json
import random
from typing import AsyncGenerator
from backend import db


def _fmt(val) -> str | int | float | None:
    """Format DB values for JSON serialization."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    return str(val)


def _serialize_row(row: dict) -> dict:
    """Convert all values in a row to JSON-safe types."""
    return {k: _fmt(v) for k, v in row.items()}


# ─── Exception detection logic ────────────────────────────────

def _detect_p2p_exceptions(inv: dict) -> list[dict]:
    """Detect AP exceptions for an invoice."""
    exceptions = []
    ms = str(inv.get("match_status", ""))
    if ms == "AMOUNT_MISMATCH":
        exceptions.append({
            "type": "quarantine",
            "rule": "amount_match",
            "severity": "high",
            "reason": f"Invoice amount does not match PO amount (variance exceeds 2% threshold)",
            "resolution": "Compare invoice line items against PO {po}. Contact vendor if discrepancy confirmed.".format(
                po=inv.get("po_id", "N/A")
            ),
        })
    if ms == "NO_PO_REFERENCE":
        exceptions.append({
            "type": "quarantine",
            "rule": "has_po_ref",
            "severity": "high",
            "reason": "Invoice has no Purchase Order reference — cannot perform 3-way match",
            "resolution": "Route to AP supervisor for manual PO assignment or rejection.",
        })
    if str(inv.get("is_overdue", "")).lower() == "true":
        age = inv.get("aging_days", 0)
        if age and int(age) > 60:
            exceptions.append({
                "type": "exception",
                "rule": "overdue_critical",
                "severity": "critical",
                "reason": f"Invoice is {age} days overdue — approaching write-off threshold",
                "resolution": "Escalate to AP Supervisor for immediate payment authorization.",
            })
    if not inv.get("gstin_vendor"):
        exceptions.append({
            "type": "exception",
            "rule": "missing_gstin",
            "severity": "medium",
            "reason": "Vendor GSTIN is missing — GST input credit cannot be claimed",
            "resolution": "Request updated GST registration from vendor before processing.",
        })
    return exceptions


def _detect_o2c_exceptions(col: dict) -> list[dict]:
    """Detect AR exceptions for a collection record."""
    exceptions = []
    status = str(col.get("invoice_status", ""))
    outstanding = float(col.get("balance_outstanding", 0) or 0)
    days_overdue = int(col.get("days_overdue", 0) or 0)

    if status == "WRITTEN_OFF":
        exceptions.append({
            "type": "quarantine",
            "rule": "written_off",
            "severity": "critical",
            "reason": f"Invoice written off — INR {outstanding:,.0f} unrecoverable",
            "resolution": "Review with Credit Manager for bad debt provisioning.",
        })
    elif days_overdue > 90:
        exceptions.append({
            "type": "quarantine",
            "rule": "critical_overdue",
            "severity": "critical",
            "reason": f"Invoice is {days_overdue} days overdue — INR {outstanding:,.0f} at risk",
            "resolution": "Escalate to Credit Manager. Consider legal collection action.",
        })
    elif days_overdue > 60:
        exceptions.append({
            "type": "exception",
            "rule": "aging_concern",
            "severity": "high",
            "reason": f"Invoice {days_overdue} days overdue — moving into concern bucket",
            "resolution": "Priority collection call required. Update PTP commitment.",
        })
    if outstanding > 5_000_000:
        exceptions.append({
            "type": "exception",
            "rule": "high_value_outstanding",
            "severity": "high",
            "reason": f"High-value outstanding: INR {outstanding:,.0f}",
            "resolution": "Assign dedicated collection follow-up.",
        })
    return exceptions


def _detect_r2r_exceptions(je: dict, je_lines: list[dict]) -> list[dict]:
    """Detect GL exceptions for a journal entry."""
    exceptions = []
    total_debit = sum(float(l.get("debit_inr", 0) or 0) for l in je_lines)
    total_credit = sum(float(l.get("credit_inr", 0) or 0) for l in je_lines)
    diff = abs(total_debit - total_credit)

    if diff > 0.01:
        exceptions.append({
            "type": "quarantine",
            "rule": "je_balanced",
            "severity": "critical",
            "reason": f"Journal entry is UNBALANCED — Debit: INR {total_debit:,.2f}, Credit: INR {total_credit:,.2f}, Difference: INR {diff:,.2f}",
            "resolution": f"Review entry posted by {je.get('posted_by', 'Unknown')}. Correct the imbalance before period close.",
        })
    if total_debit > 5_000_000:
        exceptions.append({
            "type": "exception",
            "rule": "high_value_je",
            "severity": "medium",
            "reason": f"High-value journal entry: INR {total_debit:,.0f} — requires controller approval",
            "resolution": "Route to Vikram (Financial Controller) for sign-off.",
        })
    return exceptions


# ─── SSE Generators ────────────────────────────────────────────

async def stream_p2p() -> AsyncGenerator[str, None]:
    """Stream P2P invoice events."""
    invoices = await asyncio.to_thread(db.get_invoices, 100)
    random.shuffle(invoices)

    # Morning greeting
    total = len(invoices)
    exceptions_count = sum(1 for i in invoices if i.get("match_status") in ("AMOUNT_MISMATCH", "NO_PO_REFERENCE"))
    overdue_count = sum(1 for i in invoices if str(i.get("is_overdue", "")).lower() == "true")
    total_amount = sum(float(i.get("invoice_total_inr", 0) or 0) for i in invoices)

    yield json.dumps({
        "type": "greeting",
        "data": {
            "persona": "",
            "role": "AP Operations Lead",
            "message": f"{total} invoices queued today.\n  {exceptions_count} require your attention: exceptions & mismatches\n  {overdue_count} overdue invoices flagged\nTotal value in queue: INR {total_amount:,.0f}",
        }
    })
    await asyncio.sleep(0.3)

    processed = 0
    matched_count = 0
    exception_count = 0

    for inv in invoices:
        row = _serialize_row(inv)

        # Simulate match status animation
        ms = inv.get("match_status", "")
        if ms == "THREE_WAY_MATCHED":
            # Show running then matched
            row["_anim_status"] = "running"
            yield json.dumps({"type": "invoice_processing", "data": row})
            await asyncio.sleep(random.uniform(0.3, 0.8))
            row["_anim_status"] = "matched"
            matched_count += 1

        yield json.dumps({"type": "invoice", "data": row})
        processed += 1

        # Check for exceptions
        excs = _detect_p2p_exceptions(inv)
        for exc in excs:
            exception_count += 1
            exc_data = {**exc, "invoice_id": inv.get("invoice_id"), "vendor_name": inv.get("vendor_name"),
                        "amount": float(inv.get("invoice_total_inr", 0) or 0), "invoice_number": inv.get("invoice_number")}
            yield json.dumps({"type": exc["type"], "data": exc_data})
            await asyncio.sleep(0.2)

        # Progress update every 10 invoices
        if processed % 10 == 0:
            yield json.dumps({
                "type": "progress",
                "data": {"processed": processed, "total": total, "matched": matched_count, "exceptions": exception_count}
            })

        await asyncio.sleep(random.uniform(0.4, 1.2))

    # End of day summary
    yield json.dumps({
        "type": "summary",
        "data": {
            "processed": processed,
            "matched": matched_count,
            "exceptions": exception_count,
            "touchless_rate": round(matched_count / max(processed, 1) * 100, 1),
            "message": f"Today, Databricks handled {matched_count} invoices automatically through 3-way matching — what used to take 6.5 hours. Your team focused on: {exception_count} exception reviews, vendor escalations, and judgment calls."
        }
    })


async def stream_o2c() -> AsyncGenerator[str, None]:
    """Stream O2C collection events."""
    collections = await asyncio.to_thread(db.get_collections, 100)
    random.shuffle(collections)

    total_outstanding = sum(float(c.get("balance_outstanding", 0) or 0) for c in collections)
    overdue = [c for c in collections if int(c.get("days_overdue", 0) or 0) > 0]

    # Bucket breakdown
    buckets = {}
    for c in collections:
        b = c.get("aging_bucket", "Unknown")
        buckets[b] = buckets.get(b, 0) + float(c.get("balance_outstanding", 0) or 0)

    yield json.dumps({
        "type": "greeting",
        "data": {
            "persona": "",
            "role": "Collections Specialist",
            "message": f"AR portfolio: INR {total_outstanding:,.0f} outstanding\n  {len(overdue)} overdue accounts requiring action\n  Priority calls today: {min(len(overdue), 12)} accounts",
            "buckets": {k: round(v, 0) for k, v in buckets.items()},
        }
    })
    await asyncio.sleep(0.3)

    processed = 0
    collected_today = 0
    exceptions_found = 0

    for col in collections:
        row = _serialize_row(col)

        # Simulate payment events
        status = col.get("invoice_status", "")
        collected = float(col.get("amount_collected_inr", 0) or 0)
        if status in ("COLLECTED", "PARTIALLY_COLLECTED") and collected > 0:
            yield json.dumps({"type": "payment_received", "data": {
                **row, "event": "cash_applied",
                "auto_matched": random.random() > 0.3,
            }})
            collected_today += collected
        else:
            yield json.dumps({"type": "collection", "data": row})

        processed += 1

        # Check exceptions
        excs = _detect_o2c_exceptions(col)
        for exc in excs:
            exceptions_found += 1
            exc_data = {**exc, "invoice_id": col.get("o2c_invoice_id"),
                        "customer_name": col.get("customer_name"),
                        "amount": float(col.get("balance_outstanding", 0) or 0),
                        "invoice_number": col.get("invoice_number")}
            yield json.dumps({"type": exc["type"], "data": exc_data})
            await asyncio.sleep(0.2)

        if processed % 10 == 0:
            yield json.dumps({
                "type": "progress",
                "data": {"processed": processed, "total": len(collections),
                         "collected_today": collected_today, "exceptions": exceptions_found}
            })

        await asyncio.sleep(random.uniform(0.4, 1.2))

    yield json.dumps({
        "type": "summary",
        "data": {
            "processed": processed,
            "collected_today": collected_today,
            "exceptions": exceptions_found,
            "message": f"Today's collection run: {processed} accounts reviewed. INR {collected_today:,.0f} cash applied. {exceptions_found} exceptions flagged for follow-up."
        }
    })


async def stream_r2r() -> AsyncGenerator[str, None]:
    """Stream R2R journal entry events."""
    entries = await asyncio.to_thread(db.get_journal_entries, 200)

    # Group by je_id to process complete journal entries
    je_groups: dict[str, list[dict]] = {}
    for e in entries:
        jid = e["je_id"]
        if jid not in je_groups:
            je_groups[jid] = []
        je_groups[jid].append(e)

    je_list = list(je_groups.items())
    random.shuffle(je_list)

    total_jes = len(je_list)
    # Close checklist items
    checklist = [
        {"task": "Standard recurring JEs posted", "owner": "Sunita", "status": "completed"},
        {"task": "Payroll accrual booked", "owner": "Sunita", "status": "completed"},
        {"task": "Depreciation JE", "owner": "Sunita", "status": "in_progress"},
        {"task": "Prepaid expense amortization", "owner": "Sunita", "status": "pending"},
        {"task": "Revenue recognition adjustments", "owner": "Sunita", "status": "pending"},
        {"task": "Bank reconciliation — Final", "owner": "Sunita", "status": "pending"},
        {"task": "Intercompany eliminations", "owner": "Vikram", "status": "pending"},
        {"task": "Controller review & sign-off", "owner": "Vikram", "status": "pending"},
    ]

    yield json.dumps({
        "type": "greeting",
        "data": {
            "persona": "",
            "role": "GL Accountant",
            "message": f"Month-End Close: March 2025\nDay 2 of 5  |  Status: ON TRACK\n\n{total_jes} journal entries to validate\nClose checklist: 2 of {len(checklist)} tasks complete",
            "checklist": checklist,
        }
    })
    await asyncio.sleep(0.3)

    posted = 0
    quarantined = 0
    running_debit = 0.0
    running_credit = 0.0

    for je_id, lines in je_list[:60]:  # Limit to 60 JEs for reasonable stream
        first = lines[0]
        total_debit = sum(float(l.get("debit_inr", 0) or 0) for l in lines)
        total_credit = sum(float(l.get("credit_inr", 0) or 0) for l in lines)
        is_balanced = abs(total_debit - total_credit) < 0.01

        running_debit += total_debit
        running_credit += total_credit

        je_data = {
            "je_id": je_id,
            "je_number": first.get("je_number"),
            "je_date": str(first.get("je_date", "")),
            "je_type": first.get("je_type"),
            "posted_by": first.get("posted_by"),
            "status": first.get("status"),
            "department": first.get("department"),
            "total_debit": total_debit,
            "total_credit": total_credit,
            "is_balanced": is_balanced,
            "line_count": len(lines),
            "lines": [
                {
                    "line": l.get("gl_line_number"),
                    "account_code": l.get("account_code"),
                    "account_name": l.get("account_name"),
                    "debit": float(l.get("debit_inr", 0) or 0),
                    "credit": float(l.get("credit_inr", 0) or 0),
                    "description": l.get("gl_description"),
                }
                for l in lines
            ],
        }

        yield json.dumps({"type": "journal_entry", "data": je_data})
        posted += 1

        # Check for exceptions
        excs = _detect_r2r_exceptions(first, lines)
        for exc in excs:
            if exc["type"] == "quarantine":
                quarantined += 1
            exc_data = {**exc, **je_data}
            yield json.dumps({"type": exc["type"], "data": exc_data})
            await asyncio.sleep(0.2)

        # Trial balance update
        if posted % 5 == 0:
            yield json.dumps({
                "type": "tb_update",
                "data": {
                    "posted": posted,
                    "quarantined": quarantined,
                    "running_debit": running_debit,
                    "running_credit": running_credit,
                    "is_balanced": abs(running_debit - running_credit) < 1.0,
                }
            })

            # Advance checklist
            if posted >= 15 and checklist[2]["status"] == "in_progress":
                checklist[2]["status"] = "completed"
                checklist[3]["status"] = "in_progress"
                yield json.dumps({"type": "checklist_update", "data": {"checklist": checklist}})
            elif posted >= 30 and checklist[3]["status"] == "in_progress":
                checklist[3]["status"] = "completed"
                checklist[4]["status"] = "in_progress"
                yield json.dumps({"type": "checklist_update", "data": {"checklist": checklist}})

        await asyncio.sleep(random.uniform(0.5, 1.5))

    yield json.dumps({
        "type": "summary",
        "data": {
            "posted": posted,
            "quarantined": quarantined,
            "running_debit": running_debit,
            "running_credit": running_credit,
            "is_balanced": abs(running_debit - running_credit) < 1.0,
            "message": f"Journal entry validation complete. {posted} entries posted, {quarantined} quarantined. Trial balance {'BALANCED' if abs(running_debit - running_credit) < 1.0 else 'IMBALANCED — review required'}."
        }
    })
