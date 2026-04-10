# Finance & Accounting Control Tower - Deployment Test Instructions

## Executive Summary

A comprehensive end-to-end test suite has been created to validate the deployed Finance & Accounting Control Tower app. The suite includes 7 critical tests covering:

1. ✓ App Loading & Navigation
2. ✓ Escalation Modal Flow
3. ✓ Alert Sending Functionality
4. ✓ AI Chat Messaging
5. ✓ Chat History Management

**App Under Test:** https://akash-finance-demo-1444828305810485.aws.databricksapps.com

---

## Quick Start (5 Minutes)

### For Manual Testing
1. Open a browser and navigate to the app URL above
2. Follow the 7 test scenarios in: `E2E_TEST_GUIDE.md`
3. Document results using the provided checklist

### For Automated Testing
```bash
cd "/Users/akash.s/finance & accounting demo"

# Install Playwright (first time only)
cd app/frontend && npm install -D @playwright/test && npx playwright install chromium && cd ../..

# Run all 7 tests
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts

# View results
npx playwright show-report test-results/html
```

---

## Test Suite Contents

### Test File
**Location:** `/Users/akash.s/finance & accounting demo/tests/test_e2e_deployed.spec.ts`

**7 Automated Tests:**

| # | Test Name | Purpose | Validates |
|---|-----------|---------|-----------|
| 1 | App loads correctly | Page renders without errors | No white screen, AP Operations tab visible |
| 2 | Escalate button visibility | Button exists in UI | Exceptions panel, clickable Escalate button |
| 3 | Escalate modal flow | Modal opens with correct structure | Title, 4 checkboxes, no email field, all checked |
| 4 | Execute escalation | Alert sending works | Success message appears within 10s |
| 5 | Chat history visibility | History panel opens | History icon clickable, panel displays |
| 6 | Send test chat message | AI responds with data | Response within 30s, contains actual data |
| 7 | Chat history persistence | Sessions saved correctly | New session appears in history list |

---

## Documentation Files

### 1. E2E_TEST_GUIDE.md (Complete Testing Guide)
Contains:
- **Manual Testing Steps** - Detailed instructions for all 7 tests
- **Expected Results** - What should happen in each scenario
- **Automated Testing Commands** - How to run with Playwright
- **Debugging Guide** - Troubleshooting common issues
- **Result Summary Table** - Track PASS/FAIL for each test

**Use this if:** You want to test manually or understand what each test does

### 2. TEST_SETUP_SUMMARY.md (Setup & Configuration)
Contains:
- **What Has Been Created** - Overview of all new files
- **How to Run Tests** - Step-by-step commands
- **Test Results Format** - What you'll get when tests run
- **Prerequisites** - What's needed before running
- **File Locations** - Where everything is located

**Use this if:** You need to set up the test environment

### 3. This File (Quick Reference)
Contains:
- **Quick Start** - Get running in 5 minutes
- **Command Reference** - Common test commands
- **Success Criteria** - What PASS means for each test
- **Troubleshooting** - Common issues & solutions

---

## Test Execution Guide

### Running Full Test Suite
```bash
# Navigate to project root
cd "/Users/akash.s/finance & accounting demo"

# Run all 7 tests against deployed app
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts

# Expected output:
# TEST 1: App loads correctly ✓ PASSED
# TEST 2: Escalate button visibility ✓ PASSED
# TEST 3: Escalate modal flow ✓ PASSED
# TEST 4: Execute escalation ✓ PASSED
# TEST 5: Chat history visibility ✓ PASSED
# TEST 6: Send test chat message ✓ PASSED
# TEST 7: Chat history persistence ✓ PASSED
```

### Running Individual Tests
```bash
# Just Test 1
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 1"

# Just Test 4 (escalation)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 4"

# Just Test 6 (chat)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 6"
```

### Running in Headed Mode (See Browser)
```bash
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts --headed
```

### Viewing Test Results
```bash
# After running tests, view the HTML report
npx playwright show-report test-results/html

# Screenshots are saved to:
# test-results/01_app_loaded.png
# test-results/02_escalate_button_visible.png
# test-results/03_escalate_modal.png
# etc.
```

---

## Success Criteria

### TEST 1: App loads correctly ✓
**PASS if:**
- Page loads within 10 seconds
- No white/blank screen
- No JavaScript errors in console
- "AP Operations" tab is visible
- Page has normal layout with content

**FAIL if:**
- HTTP error (404, 500, etc.)
- White/blank screen
- Continuous loading spinner
- JavaScript errors in console

---

### TEST 2: Escalate button visibility ✓
**PASS if:**
- "Exceptions" panel is visible on AP Operations tab
- "Escalate" button is visible in panel header
- Button is not disabled/grayed out
- Button is clickable

**FAIL if:**
- Exceptions panel not found
- Escalate button not visible
- Button is disabled
- Multiple conflicting buttons found

---

### TEST 3: Escalate modal flow ✓
**PASS if:**
- Modal opens with title "Escalate via SQL Alert"
- 4 checkboxes visible:
  - Amount Mismatch
  - No PO Reference
  - Critical Overdue (>60 days)
  - Missing GSTIN
- All 4 checkboxes are PRE-CHECKED
- NO email input field present
- "Send Alert" button visible

**FAIL if:**
- Wrong title or modal doesn't open
- Missing any checkbox
- Wrong number of checkboxes
- Email input field is present
- Checkboxes are unchecked by default

---

### TEST 4: Execute escalation ✓
**PASS if:**
- Modal stays open after clicking "Send Alert"
- Success message appears within 10 seconds
- Message indicates email will be sent
- Message shows timing (e.g., "within ~60 seconds")
- No error messages

**FAIL if:**
- Error message appears
- No response within 10 seconds
- Button becomes stuck/disabled
- User gets unclear feedback

**Example Success Message:**
```
✓ Alert escalation triggered
Email sent to incident-escalation@company.com
Stakeholders will be notified within ~60 seconds
```

---

### TEST 5: Chat history visibility ✓
**PASS if:**
- History icon is visible in chat panel
- Clicking icon opens history panel/drawer
- Panel shows any past sessions (if exist)
- Panel has clear title "History" or similar
- Can close the panel

**FAIL if:**
- History icon not found
- Icon is disabled
- History panel doesn't open
- No clear indication of sessions

---

### TEST 6: Send test chat message ✓
**PASS if:**
- Message sends successfully (checkmark or confirmation)
- Response appears within 30 seconds
- Response contains actual data/numbers
- Response is contextual (answers the question)
- No error messages

**Example Good Response:**
```
There are currently 45 invoices in exception status.
Of these:
- 30 have amount mismatches
- 15 are missing PO references
- 5 are critical overdue (>60 days)
```

**FAIL if:**
- Message doesn't send
- No response after 30 seconds
- Response is generic ("I found some invoices")
- Error message appears
- Chat shows "failed to send"

---

### TEST 7: Chat history persistence ✓
**PASS if:**
- After sending message, history panel shows new session
- Session shows timestamp of when created
- Session shows preview of first message
- Can click session to restore conversation
- Old messages are still visible

**FAIL if:**
- New session not in history
- History doesn't update
- No timestamps shown
- Session preview is empty
- Messages disappear when restoring

---

## Troubleshooting Common Issues

### Issue: "Cannot find Escalate button"
**Solutions:**
1. Check you're on "AP Operations" tab (click it explicitly)
2. Scroll down - panel might be below the fold
3. Zoom out (Ctrl/-) to see full layout
4. Open DevTools (F12) and search for "Escalate" text

### Issue: "Chat doesn't respond"
**Solutions:**
1. Check network tab (F12) - are requests to `/api/*` succeeding?
2. Wait the full 30 seconds (backend may be slow)
3. Try a simpler message: "Hello" or "Hi"
4. Check console (F12) for JavaScript errors

### Issue: "Playwright won't install"
**Solutions:**
1. Check Node.js is installed: `node --version` (should be v25.6.1+)
2. If network error, try: `npm install --no-save -D @playwright/test`
3. Or use manual testing instead (see E2E_TEST_GUIDE.md)

### Issue: "Tests timeout"
**Solutions:**
1. Deployed app may be slow on first load
2. Increase timeout in `playwright.config.ts`: change `60_000` to `120_000`
3. Run in headed mode to see what's happening: `--headed`

### Issue: "Success message not appearing"
**Solutions:**
1. Check if message appears elsewhere on page (top, bottom, center)
2. Look for toast notifications
3. Check browser console for errors
4. Verify you clicked "Send Alert" button

---

## Integration with Existing Tests

The project already has comprehensive tests in:
```
tests/test_frontend.spec.ts - Local development tests with mocked APIs
```

The new tests are specifically for the deployed app:
```
tests/test_e2e_deployed.spec.ts - Production deployment tests with real backend
```

Both can be run together:
```bash
npx playwright test --config=tests/playwright.config.ts
```

Or separately:
```bash
# Only deployed app tests
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts

# Only local dev tests
npx playwright test --config=tests/playwright.config.ts tests/test_frontend.spec.ts
```

---

## Screenshots & Artifacts

When tests run, screenshots are automatically saved:

```
test-results/
├── 01_app_loaded.png              # Initial page load
├── 02_escalate_button_visible.png # Escalate button in context
├── 03_escalate_modal.png          # Modal with 4 checkboxes
├── 04_escalation_result.png       # Success/error message
├── 05_chat_history.png            # History panel open
├── 06_chat_message.png            # Chat conversation
├── 07_chat_history_updated.png    # New session in history
└── html/
    └── index.html                 # Full test report (open in browser)
```

This helps with:
- Debugging failures visually
- Documenting test evidence
- Sharing results with team
- Understanding UI state at each step

---

## Next Steps

1. **Review Documentation:**
   - Read `E2E_TEST_GUIDE.md` for detailed test descriptions
   - Read `TEST_SETUP_SUMMARY.md` for setup details

2. **Choose Testing Approach:**
   - **Manual:** Follow guide in E2E_TEST_GUIDE.md with your browser
   - **Automated:** Run Playwright commands from this guide

3. **Execute Tests:**
   - Run commands from "Test Execution Guide" section above
   - Check results in console and screenshots

4. **Document Results:**
   - Use the result checklist in E2E_TEST_GUIDE.md
   - Save screenshots for evidence
   - Note any failures with exact error messages

5. **Report Issues:**
   - If tests fail, include: test #, expected vs actual, screenshot
   - Check troubleshooting section above first
   - Review console logs (F12) for technical details

---

## Questions?

- **Test Setup:** See `TEST_SETUP_SUMMARY.md`
- **Test Details:** See `E2E_TEST_GUIDE.md`
- **Test Code:** See `tests/test_e2e_deployed.spec.ts`
- **Debugging:** See Troubleshooting section above

---

## Files Created

```
✓ tests/test_e2e_deployed.spec.ts    - 7 automated tests (400+ lines)
✓ E2E_TEST_GUIDE.md                  - Complete testing guide (350+ lines)
✓ TEST_SETUP_SUMMARY.md              - Setup instructions (200+ lines)
✓ DEPLOYMENT_TEST_INSTRUCTIONS.md    - This file (reference guide)
✓ tests/playwright.config.ts         - Updated configuration
```

**Total:** 950+ lines of test code and documentation

**Commit:** `0d63955` - "Add comprehensive end-to-end test suite for deployed Finance & Accounting Control Tower app"

---

## App Status

- **Environment:** Databricks AWS (akash-finance-demo workspace)
- **URL:** https://akash-finance-demo-1444828305810485.aws.databricksapps.com
- **Authentication:** Databricks SSO (user already logged in)
- **Status:** Ready for end-to-end testing
- **Test Coverage:** 7 critical user flows

---

**Created:** 2026-04-10
**Last Updated:** 2026-04-10
**Version:** 1.0
