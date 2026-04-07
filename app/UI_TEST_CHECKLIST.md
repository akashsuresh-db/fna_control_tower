# UI/UX Testing Checklist - Finance & Accounting Demo

**App URL:** https://akash-finance-demo-1444828305810485.aws.databricksapps.com  
**Test Environment:** Production  
**Browser:** Chrome, Safari, or Edge  
**Date:** 2026-04-07  

---

## Authentication & Initial Load

- [ ] Navigate to app URL
- [ ] Browser redirects to Databricks SSO login
- [ ] Login with akash.s@databricks.com on e2-demo-field-eng workspace
- [ ] Redirected back to app
- [ ] User name appears in top-right corner

---

## P2P Tab (AP Operations) - Complete Test Flow

### Metrics & UI Load

- [ ] **Tab Navigation:** Click "AP Operations" or "P2P" tab
- [ ] **KPI Cards Display:**
  - [ ] Total Invoices card visible
  - [ ] 3-Way Matched card visible (green)
  - [ ] Exceptions card visible (red)
  - [ ] Touchless Rate card visible (blue)
  - [ ] Overdue card visible (amber) with INR amount
  - [ ] Avg Aging card visible
- [ ] **Payment Run Panel:**
  - [ ] DPO (Days Payable Outstanding) gauge visible
  - [ ] Early Payments count visible
  - [ ] On Time Payments count visible
  - [ ] Late Payments count visible

### Stream Processing

- [ ] **Click "Start Processing" Button**
  - [ ] Button changes state to disabled/loading
  - [ ] No JavaScript errors in console (F12)
  - [ ] **If no error appears after 3 seconds:**
    - [ ] Greeting message appears
    - [ ] Message shows invoice count and exception count
    - [ ] "Processing..." indicator appears with pulse animation
    - [ ] **Proceed to next checks**
  - [ ] **If error appears in red box:**
    - [ ] Copy error message
    - [ ] Check browser console (F12) for technical details
    - [ ] Note: This helps diagnose the streaming issue
    - [ ] **Skip remaining stream checks for now**

### Invoice Queue Feed

*(Only if stream started successfully)*

- [ ] **Invoice rows appear in queue:**
  - [ ] First invoice appears within 5 seconds
  - [ ] Invoice ID visible (e.g., "INV-001")
  - [ ] Vendor name visible
  - [ ] Invoice amount in INR
  - [ ] Match status badge (Matched/Pending/Mismatch)
  - [ ] Due date visible
  - [ ] Aging bucket visible if overdue

- [ ] **Invoices continue flowing:**
  - [ ] New invoices appear every 1-2 seconds
  - [ ] Queue scrolls automatically (shows latest at bottom)
  - [ ] Progress counter updates (e.g., "Processing... 23/100")

### Exception Detection & Handling

*(Only if stream started)*

- [ ] **Exceptions panel shows:**
  - [ ] "Exceptions" header with count
  - [ ] Exception items list below
  - [ ] Each exception shows severity badge (critical/high/medium)

- [ ] **Click exception row:**
  - [ ] ExceptionDrawer slides in from right
  - [ ] Shows exception type (Quarantine/Exception)
  - [ ] Shows reason and resolution
  - [ ] Shows affected invoice details

- [ ] **In ExceptionDrawer, click "View Invoice" (if present):**
  - [ ] InvoiceDrawer opens showing full details:
    - [ ] Invoice ID and Number
    - [ ] Vendor name and ID
    - [ ] PO ID
    - [ ] Invoice date, due date
    - [ ] Amount and GSTIN
    - [ ] Match status reason
  - [ ] Click "Download PDF" button:
    - [ ] PDF generates and downloads
    - [ ] Filename is "invoice-{invoice_id}.pdf"

- [ ] **Back in ExceptionDrawer:**
  - [ ] **Approve Button** (if visible):
    - [ ] Click Approve
    - [ ] Button state changes to "Actioned"
    - [ ] API call succeeds (check Network tab)
    - [ ] Row in queue marked as approved
  - [ ] **Reject Button** (if visible):
    - [ ] Click Reject
    - [ ] Same flow as Approve
    - [ ] Status changes to "Rejected"

- [ ] **Close drawer:**
  - [ ] Click X button
  - [ ] Drawer slides out
  - [ ] Back to main P2P view

### Stop & Summary

- [ ] **Click "Stop" button:**
  - [ ] Stream closes
  - [ ] Processing stops
  - [ ] Button returns to "Start Processing" state
  
- [ ] **Summary appears after stream ends:**
  - [ ] SummaryCard shows:
    - [ ] Total processed
    - [ ] Total matched
    - [ ] Total exceptions
    - [ ] Touchless rate percentage
    - [ ] Summary message

---

## O2C Tab (AR Operations) - Complete Test Flow

### Metrics & UI Load

- [ ] **Tab Navigation:** Click "AR Operations" or "O2C" tab
- [ ] **KPI Cards Display:**
  - [ ] AR Outstanding (INR amount)
  - [ ] DSO (Days Sales Outstanding, days + target)
  - [ ] CEI (Collection Effectiveness Index, %)
  - [ ] Overdue count
  - [ ] Collected count
  - [ ] At Risk count (number of customers)

- [ ] **AR Aging Chart:**
  - [ ] Renders below KPI cards
  - [ ] Shows aging buckets (0-30, 31-60, 61-90, 90+)
  - [ ] Y-axis shows customer count or amount

- [ ] **Credit Risk Panel (Right side):**
  - [ ] Shows customers at risk
  - [ ] Each row shows:
    - [ ] Customer name
    - [ ] Credit limit (INR)
    - [ ] Outstanding amount (INR)
    - [ ] Utilization %
    - [ ] Overdue amount
    - [ ] DSO

### Stream Processing

- [ ] **Click "Start Collection Run" Button**
  - [ ] Same error handling as P2P
  - [ ] Check for error message in red box
  - [ ] If error, note message for diagnostics

- [ ] **Collection records appear:**
  - [ ] First record within 5 seconds
  - [ ] Shows customer name
  - [ ] Shows outstanding balance (INR)
  - [ ] Shows aging days
  - [ ] Shows invoice number
  - [ ] Status badge (Collected/Overdue/At Risk)

- [ ] **Collection running flow:**
  - [ ] Records continue appearing
  - [ ] "Collected today" ticker updates (if applicable)
  - [ ] Shows collected amount in INR

### Call Logging

- [ ] **Click "Log" button on a collection record:**
  - [ ] CallLogModal opens
  - [ ] Form appears with fields:
    - [ ] Customer name (pre-filled)
    - [ ] Outcome dropdown
    - [ ] Notes text area
    - [ ] "Log Call" submit button

- [ ] **Test outcome selection (4 buttons):**
  - [ ] Click "Reached-PTP":
    - [ ] Button highlights
    - [ ] PTP Date field appears
    - [ ] Click date picker, select date
  - [ ] Click "Reached-Dispute":
    - [ ] Button highlights
    - [ ] PTP Date field disappears (if was visible)
  - [ ] Click "Voicemail":
    - [ ] Button highlights
    - [ ] PTP Date field disappears
  - [ ] Click "Escalate":
    - [ ] Button highlights
    - [ ] PTP Date field disappears

- [ ] **Fill form and submit:**
  - [ ] Type notes in Notes field
  - [ ] Click "Log Call" button
  - [ ] Modal closes
  - [ ] Notification appears (if configured)
  - [ ] Check Network tab: POST /api/call-log succeeded

- [ ] **Close modal:**
  - [ ] Click X button
  - [ ] Modal closes cleanly
  - [ ] Form clears

### Collection Queue

- [ ] **Exception detection:**
  - [ ] Exceptions appear in sidebar with severity
  - [ ] Click exception to view details
  - [ ] Shows aging concern, high-value, or critical reasons

- [ ] **Stop stream:**
  - [ ] Click "Stop" button
  - [ ] Collection processing halts
  - [ ] Summary appears

---

## R2R Tab (GL Operations) - Complete Test Flow

### Metrics & UI Load

- [ ] **Tab Navigation:** Click "GL Operations" or "R2R" tab
- [ ] **KPI Cards Display:**
  - [ ] Journal Entries total count
  - [ ] Posted count (green)
  - [ ] Pending count (amber)
  - [ ] TB Debits (INR)
  - [ ] TB Credits (INR)
  - [ ] TB Status (BALANCED or IMBALANCED in green/red)

### Stream Processing

- [ ] **Click "Start JE Validation" Button**
  - [ ] Same error handling as P2P/O2C
  - [ ] Check for error message

- [ ] **Greeting appears:**
  - [ ] Shows month and close day (e.g., "March 2025 - Day 2")
  - [ ] Shows status (e.g., "ON TRACK")
  - [ ] Shows total JEs to validate
  - [ ] Shows close checklist progress

### Close Checklist

- [ ] **Checklist items visible:**
  - [ ] Task names appear (e.g., "Depreciation JE", "Prepaid expense amortization")
  - [ ] Owner name visible
  - [ ] Status badges (completed=green, in_progress=blue, pending=gray)

- [ ] **Checklist updates during stream:**
  - [ ] As JEs process, checklist items transition
  - [ ] e.g., "Depreciation JE" moves from pending → in_progress → completed

### Journal Entry Feed

- [ ] **JE cards appear:**
  - [ ] JE Number (e.g., "JE-2025-001")
  - [ ] JE Date
  - [ ] Posted by (person name)
  - [ ] Line count
  - [ ] Balance status (green checkmark if balanced, red X if not)

- [ ] **JE detail lines:**
  - [ ] Account code visible
  - [ ] Account name
  - [ ] Debit and Credit amounts (INR)
  - [ ] Description

- [ ] **Exception detection:**
  - [ ] Unbalanced JEs flagged as quarantine (critical)
  - [ ] High-value JEs flagged as exception (medium)
  - [ ] Appears in exceptions panel

### Trial Balance View

- [ ] **Click "Show Trial Balance" button:**
  - [ ] Button changes to "Hide Trial Balance"
  - [ ] JE feed replaced with trial balance table
  - [ ] Table shows:
    - [ ] Account Code (GL code)
    - [ ] Account Name
    - [ ] Account Type (Asset/Liability/Equity/etc.)
    - [ ] Debit amount (INR)
    - [ ] Credit amount (INR)
    - [ ] Balance
  - [ ] TB Status shows BALANCED or IMBALANCED
  - [ ] Running totals visible at bottom

- [ ] **Click "Hide Trial Balance" button:**
  - [ ] Returns to JE feed view
  - [ ] Button text changes back to "Show Trial Balance"

### Stop & Summary

- [ ] **Click "Stop" button:**
  - [ ] JE processing stops
  - [ ] Summary appears with:
    - [ ] Total posted
    - [ ] Total quarantined
    - [ ] Running debits/credits
    - [ ] Balance status

---

## AI Chat Panel - Complete Test Flow

- [ ] **Find chat input at bottom-right:**
  - [ ] Input field visible
  - [ ] Placeholder text visible
  - [ ] "New Chat" or "+" button above
  - [ ] "History" button above

### Chat Message Flow

- [ ] **Type question:**
  - [ ] Type: "What is the current DPO?"
  - [ ] Text appears in input field

- [ ] **Send message:**
  - [ ] Press Enter or click Send button
  - [ ] Message appears in chat bubble (left side, user)
  - [ ] Input clears

- [ ] **AI response streams:**
  - [ ] Response starts appearing immediately
  - [ ] Text streams character by character
  - [ ] Response appears in chat bubble (right side, AI)
  - [ ] Response includes relevant finance metrics/insights

- [ ] **Multiple exchanges:**
  - [ ] Type another question (e.g., "How many invoices are overdue?")
  - [ ] Send and receive response
  - [ ] Chat history visible with both messages

### Chat Controls

- [ ] **Click "New Chat" button:**
  - [ ] Chat clears
  - [ ] All prior messages disappear
  - [ ] Ready for new conversation
  - [ ] Session ID resets (generates new UUID)

- [ ] **Click "History" button:**
  - [ ] Side panel opens showing past sessions
  - [ ] Each session shows:
    - [ ] Timestamp
    - [ ] First question preview
    - [ ] Click to load that session
  - [ ] Click a session:
    - [ ] Chat loads all messages from that session
    - [ ] Can continue conversation from where left off

---

## Navigation & State Persistence

- [ ] **Tab switching (P2P → O2C → R2R → P2P):**
  - [ ] Each tab maintains its own state
  - [ ] Switching to O2C doesn't affect P2P data
  - [ ] Switching back to P2P shows same data
  - [ ] No data loss between tab switches

- [ ] **Streaming state per tab:**
  - [ ] If P2P is streaming, switch to O2C:
    - [ ] O2C stream not auto-started
    - [ ] Can click "Start Collection Run" independently
  - [ ] P2P stream still running in background
  - [ ] Switch back to P2P: stream continues

---

## Browser Console & Network Checks

- [ ] **Open Developer Tools (F12):**
  - [ ] Go to **Console** tab
  - [ ] Check for any red error messages
  - [ ] Note any errors for diagnostics

- [ ] **Network Tab Analysis:**
  - [ ] Go to **Network** tab
  - [ ] Click "Start Processing"
  - [ ] Look for request to `/stream/p2p`:
    - [ ] **Status 200:** ✅ Good (but need to check if events arriving)
    - [ ] **Status 401/403:** Auth error (see debugging guide)
    - [ ] **Status 404:** Route not found (see debugging guide)
    - [ ] **Request not appearing:** Check console.log debugging

- [ ] **API Calls:**
  - [ ] Check for `/api/metrics/p2p`, `/api/metrics/o2c`, `/api/metrics/r2r` calls
  - [ ] All should be **Status 200**
  - [ ] Check response has metric data

---

## Responsive Design Tests (Optional)

- [ ] **Desktop (1920x1080):**
  - [ ] All components visible
  - [ ] Grid layout: 2 columns for data, 1 for exceptions/chat
  - [ ] No horizontal scroll

- [ ] **Tablet (768x1024):**
  - [ ] Layout adapts to 1 column
  - [ ] KPI cards stack vertically
  - [ ] All controls accessible

- [ ] **Mobile (375x667):**
  - [ ] Readable on phone screen
  - [ ] Tabs still accessible
  - [ ] Chat panel usable (may need scroll)

---

## Error Scenarios (After Code Changes)

- [ ] **Simulate no internet:**
  - [ ] Open DevTools offline
  - [ ] Click "Start Processing"
  - [ ] Error message appears in red box
  - [ ] Error message is clear and actionable

- [ ] **Kill backend (if testing locally):**
  - [ ] Backend service stops
  - [ ] Click "Start Processing"
  - [ ] Error appears within 5 seconds
  - [ ] Message indicates connection failure

---

## Performance Checks

- [ ] **KPI cards load time:**
  - [ ] Metric cards appear within 2 seconds
  - [ ] No layout shift

- [ ] **Stream responsiveness:**
  - [ ] First invoice/record within 5 seconds
  - [ ] Continued flow at ~1-2 second intervals
  - [ ] No stuttering or lag

- [ ] **Chat response time:**
  - [ ] AI response starts within 3 seconds
  - [ ] Streaming text appears smoothly

---

## Summary Scoring

| Area | Status | Notes |
|------|--------|-------|
| Authentication | ✅/⚠️/❌ | |
| P2P Tab Load | ✅/⚠️/❌ | |
| P2P Streaming | ✅/⚠️/❌ | If ❌, note error message |
| Invoice Actions | ✅/⚠️/❌ | |
| O2C Tab Load | ✅/⚠️/❌ | |
| O2C Streaming | ✅/⚠️/❌ | If ❌, note error message |
| Call Logging | ✅/⚠️/❌ | |
| R2R Tab Load | ✅/⚠️/❌ | |
| R2R Streaming | ✅/⚠️/❌ | If ❌, note error message |
| Trial Balance | ✅/⚠️/❌ | |
| AI Chat | ✅/⚠️/❌ | |
| Navigation | ✅/⚠️/❌ | |
| **Overall** | **✅/⚠️/❌** | |

---

## Critical Issues Found

Record any critical issues here:

1. **Issue:** [describe]
   **Severity:** Critical/High/Medium  
   **Steps to Reproduce:** [steps]  
   **Expected:** [expected behavior]  
   **Actual:** [actual behavior]  
   **Error Message:** [if any]  

---

## Test Notes

[Space for additional notes, observations, or screenshots]

---

## Sign-off

- **Tester Name:** ___________________
- **Date:** ___________________
- **Environment:** ___________________
- **Overall Result:** PASS / FAIL / PARTIAL

