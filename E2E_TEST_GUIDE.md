# Finance & Accounting Control Tower - End-to-End Test Guide

## Overview
This guide provides comprehensive instructions for testing the deployed Finance & Accounting Control Tower app at:
**https://akash-finance-demo-1444828305810485.aws.databricksapps.com**

## Test Execution Methods

### Method 1: Automated Testing with Playwright (Recommended)

#### Prerequisites
```bash
# Navigate to the app directory
cd "/Users/akash.s/finance & accounting demo/app/frontend"

# Install dependencies (one-time)
npm install -D @playwright/test
npx playwright install chromium
```

#### Run Full Test Suite
```bash
# Run against deployed app
cd "/Users/akash.s/finance & accounting demo"
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts

# View results
npx playwright show-report
```

#### Run Individual Tests
```bash
# Run only Test 1 (App Loading)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 1"

# Run only Test 4 (Escalation)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 4"
```

#### Test Results Location
- Screenshots: `./test-results/*.png`
- HTML Report: `./test-results/html/index.html`
- Videos: `./test-results/**/*.webm` (on failure)

---

### Method 2: Manual Testing

Follow the step-by-step instructions below to manually test each feature.

---

## Test Cases

### TEST 1: App loads correctly
**Purpose:** Verify the application loads properly and is not showing error or blank screens

**Steps:**
1. Open browser and navigate to: https://akash-finance-demo-1444828305810485.aws.databricksapps.com
2. Wait for the page to fully load (watch for "Ready" signal in console)
3. Take a screenshot of the loaded page
4. Verify the page displays the app layout (not a white/blank screen)
5. Verify the "AP Operations" tab is visible in the tab bar

**Expected Results:**
- Page loads within 10 seconds
- No white screen or error messages
- "AP Operations" tab is visible in the UI
- Page has substantial content (navigation, metrics, panels)

**PASS/FAIL:** 

**Screenshot:** (To be captured by tester)

---

### TEST 2: Escalate button visibility
**Purpose:** Verify the Escalate button exists and is visible in the Exceptions panel

**Steps:**
1. Navigate to the deployed app (if not already there)
2. Ensure you're on the "AP Operations" tab (click if needed)
3. Scroll down to find the "Exceptions" panel
4. Look for an "Escalate" button in the panel header
5. Verify the button is clickable and visible
6. Take a screenshot showing the Escalate button

**Expected Results:**
- Exceptions panel is visible
- "Escalate" button is visible in the panel header
- Button is not disabled or grayed out
- Button appears as a prominent interactive element

**PASS/FAIL:** 

**Screenshot:** (To be captured by tester)

---

### TEST 3: Escalate modal flow
**Purpose:** Verify the modal opens correctly with all expected fields

**Steps:**
1. On the "AP Operations" tab, find the Exceptions panel
2. Click the "Escalate" button
3. Wait for the modal to open (should take <1 second)
4. Verify the modal has the title: "Escalate via SQL Alert"
5. Look for 4 checkboxes:
   - Amount Mismatch
   - No PO Reference
   - Critical Overdue (>60 days)
   - Missing GSTIN
6. Verify there is NO email input field (email should be configured server-side)
7. Verify all 4 checkboxes are CHECKED by default
8. Take a screenshot of the open modal

**Expected Results:**
- Modal opens with title "Escalate via SQL Alert"
- Exactly 4 checkboxes are visible with correct labels
- All 4 checkboxes are pre-checked
- NO email input field is present
- Modal has a "Send Alert" button at the bottom

**PASS/FAIL:** 

**Screenshot:** (To be captured by tester)

---

### TEST 4: Execute the escalation
**Purpose:** Verify the escalation flow works and returns appropriate success/error messages

**Steps:**
1. Open the Escalate modal (from Test 3)
2. Uncheck the "Missing GSTIN" checkbox (leave the other 3 checked)
3. Click the "Send Alert" button
4. Wait up to 10 seconds for a response
5. Observe if a success message appears
6. Note the exact text of the success/error message
7. Take a screenshot of the result

**Expected Results:**
- Modal remains open after clicking "Send Alert"
- A success message appears (typically contains "email" and timing like "within ~60 seconds")
- Message clearly indicates: which stakeholders will receive the alert
- No error messages appear
- Button is not disabled or in a loading state indefinitely

**Example Success Message:**
"Email sent to approvers@company.com. Alert will be triggered within ~60 seconds."

**PASS/FAIL:** 

**Error Message (if any):**

**Screenshot:** (To be captured by tester)

---

### TEST 5: Chat history visibility
**Purpose:** Verify the chat history panel can be opened and shows past sessions

**Steps:**
1. Look for the AI chat panel (typically top-right or right side)
2. Find the History icon (usually a clock/calendar icon) in the chat panel header
3. Click the History icon
4. Verify a history panel/drawer opens on the side or modal appears
5. Check if any past chat sessions are listed
6. If sessions are visible, note how many and what they show
7. Take a screenshot of the history panel

**Expected Results:**
- History icon is clickable
- History panel opens smoothly
- Past sessions are listed (if any exist)
- Each session shows: timestamp and first message preview
- User can click a session to restore it

**PASS/FAIL:** 

**Number of Sessions Visible:** 

**Screenshot:** (To be captured by tester)

---

### TEST 6: Send a test chat message
**Purpose:** Verify the chat functionality works and receives responses with actual data

**Steps:**
1. Open the chat panel (right side of screen, usually)
2. Click in the chat input field
3. Type the message: "How many invoices are in exception status?"
4. Send the message (press Enter or click Send button)
5. Wait up to 30 seconds for a response
6. Verify a response message appears from the AI (not an error)
7. Check that the response contains actual data (not just a generic message)
8. Take a screenshot of the conversation

**Expected Results:**
- Message is sent successfully
- Response appears within 30 seconds
- Response contains actual invoice/data information
- Response is contextual (answers the question about exceptions)
- No error messages appear
- Response shows the AI is connected to the backend data

**Example Good Response:**
"There are currently 45 invoices in exception status. Of these, 30 have amount mismatches, 15 are missing PO references..."

**PASS/FAIL:** 

**Response Preview (first 100 chars):**

**Screenshot:** (To be captured by tester)

---

### TEST 7: Chat history shows new session after message
**Purpose:** Verify that chat sessions are saved and appear in history after messages are sent

**Steps:**
1. Send a chat message (if not already done - see Test 6)
2. Wait for the response to complete
3. Click the History icon in the chat panel
4. Verify the history panel opens
5. Look for the message you just sent in the session list
6. Verify it shows: timestamp and first few words of your message
7. Optionally: click the session to restore it and verify messages load
8. Take a screenshot of the updated history

**Expected Results:**
- History panel opens
- New session appears in the history list
- Session shows the timestamp of when it was created
- Session preview shows the message you sent
- Clicking the session restores the chat conversation
- Old messages are still visible when session is restored

**PASS/FAIL:** 

**New Session Visible:** YES / NO

**Screenshot:** (To be captured by tester)

---

## Test Result Summary

| Test # | Name | Expected | Actual | PASS/FAIL | Notes |
|--------|------|----------|--------|-----------|-------|
| 1 | App loads correctly | App loads, AP Operations tab visible | | | |
| 2 | Escalate button visibility | Escalate button visible in Exceptions panel | | | |
| 3 | Escalate modal flow | Modal opens with 4 checkboxes, no email field | | | |
| 4 | Execute escalation | Success message appears | | | |
| 5 | Chat history visibility | History panel opens, sessions visible | | | |
| 6 | Send test chat message | Response with actual data within 30s | | | |
| 7 | Chat history after message | New session appears in history | | | |

---

## Debugging Guide

### If Test 1 Fails (App Won't Load)
- **Check:** Is the app URL correct? Can you reach it in a normal browser?
- **Check:** Are you logged into Databricks? (May need to re-authenticate)
- **Action:** Try opening the URL in an incognito/private window
- **Action:** Check browser console for JavaScript errors (F12 → Console tab)

### If Test 2 or 3 Fails (Escalate Button Not Found)
- **Check:** Are you on the "AP Operations" tab? Click it explicitly
- **Check:** Scroll the page - the Exceptions panel might be below the fold
- **Check:** Open browser DevTools and search for "Escalate" (Ctrl+F)
- **Action:** Try zooming out the page (Ctrl+-) to see if layout is hidden

### If Test 4 Fails (No Success Message)
- **Check:** Did you click "Send Alert"? Watch for button state changes
- **Check:** Check browser console for errors (F12 → Console)
- **Check:** Look for error toast/alert messages elsewhere on page
- **Check:** The response may appear in a different location (bottom left, top right, etc.)
- **Action:** Wait the full 10 seconds - response may be slow

### If Test 6 Fails (No Chat Response)
- **Check:** Did the message actually send? Look for checkmark or delivery indicator
- **Check:** Is there an error message in the chat panel?
- **Check:** Check browser DevTools Network tab - look for failed requests to `/api/*`
- **Check:** The chat may be waiting for backend processing - wait the full 30 seconds
- **Action:** Try a simpler message: "Hello" or "What's the total invoice amount?"

---

## Running Tests Programmatically

### Install Playwright in Your Environment
```bash
cd "/Users/akash.s/finance & accounting demo/app/frontend"
npm install -D @playwright/test
npx playwright install chromium
```

### Run Tests with Detailed Output
```bash
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test \
  --config=../../tests/playwright.config.ts \
  tests/test_e2e_deployed.spec.ts \
  --reporter=list \
  --workers=1
```

### Run Tests in Headed Mode (See Browser)
```bash
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test \
  --config=../../tests/playwright.config.ts \
  tests/test_e2e_deployed.spec.ts \
  --headed
```

### Generate Test Report
```bash
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test \
  --config=../../tests/playwright.config.ts \
  tests/test_e2e_deployed.spec.ts

# View the report
npx playwright show-report test-results/html
```

---

## Expected Behavior Details

### Escalate Modal Success
The modal should show a message like:
```
✓ Email sent to incident-escalation@company.com
Alert will be triggered within ~60 seconds
```

Or more specifically:
```
Escalation request sent successfully.
Stakeholders will be notified via email within approximately 60 seconds.
```

### Chat Response Format
The AI should respond with specific numbers and context:
```
Based on the current data, there are 45 invoices in exception status:
- 30 with amount mismatches
- 15 missing PO references
- 5 critical overdue items (>60 days)
```

Not just:
```
I found some invoices in exception status.
```

---

## Contact & Support

- **App URL:** https://akash-finance-demo-1444828305810485.aws.databricksapps.com
- **Issue Reporting:** Include the test number, expected vs actual, and screenshot
- **Network Issues:** If you're behind a proxy, configure npm accordingly
- **Databricks Access:** Ensure your SSO session is active in the browser

---

## Test File Location

The automated test file is located at:
```
/Users/akash.s/finance & accounting demo/tests/test_e2e_deployed.spec.ts
```

This file contains the 7 test cases in Playwright format and can be executed with:
```bash
npm install -D @playwright/test
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test --config=tests/playwright.config.ts
```
