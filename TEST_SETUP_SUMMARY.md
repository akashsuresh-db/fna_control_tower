# Finance & Accounting Control Tower - Test Setup Summary

## What Has Been Created

### 1. Playwright Test Suite
**File:** `/Users/akash.s/finance & accounting demo/tests/test_e2e_deployed.spec.ts`

A comprehensive automated test suite with 7 end-to-end tests for the deployed app:

- **Test 1:** App loads correctly - Verifies no white screen, AP Operations tab visible
- **Test 2:** Escalate button visibility - Confirms button exists in Exceptions panel
- **Test 3:** Escalate modal flow - Validates modal structure (4 checkboxes, no email field)
- **Test 4:** Execute escalation - Tests sending alerts and receiving success messages
- **Test 5:** Chat history visibility - Verifies history panel functionality
- **Test 6:** Send test chat message - Tests AI response with real data
- **Test 7:** Chat history persistence - Confirms new sessions appear in history

### 2. Updated Playwright Configuration
**File:** `/Users/akash.s/finance & accounting demo/tests/playwright.config.ts`

Updated to:
- Support both test files (original + new deployed app tests)
- Increased timeout from 30s to 60s for chat responses
- Set retries to 0 (for deployed app testing)
- Screenshot on failure + HTML reports

### 3. Comprehensive Test Guide
**File:** `/Users/akash.s/finance & accounting demo/E2E_TEST_GUIDE.md`

Complete guide with:
- Step-by-step manual testing instructions
- Automated test execution commands
- Expected results for each test
- Debugging guide for troubleshooting
- Screenshots locations

---

## How to Run the Tests

### Quick Start (Automated)

```bash
# Navigate to project
cd "/Users/akash.s/finance & accounting demo"

# Install Playwright (one-time)
cd app/frontend
npm install -D @playwright/test
npx playwright install chromium
cd ../..

# Run all 7 tests against deployed app
APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts

# View results
npx playwright show-report test-results/html
```

### Run Individual Tests

```bash
# Test 1 only (App loading)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 1"

# Test 4 only (Escalation)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 4"

# Test 6 only (Chat messages)
npx playwright test --config=tests/playwright.config.ts tests/test_e2e_deployed.spec.ts -g "TEST 6"
```

### Manual Testing

Follow the step-by-step instructions in `E2E_TEST_GUIDE.md` to manually test each feature in your browser.

---

## Test Results Will Include

When tests run, you'll get:

1. **Console Output** - Pass/fail status for each test with detailed logging
2. **Screenshots** - Automatically captured for each major step:
   - `01_app_loaded.png` - Initial app load
   - `02_escalate_button_visible.png` - Button in panel
   - `03_escalate_modal.png` - Modal structure
   - `04_escalation_result.png` - Success/error message
   - `05_chat_history.png` - History panel
   - `06_chat_message.png` - Chat conversation
   - `07_chat_history_updated.png` - New session in history

3. **HTML Report** - Full test results in `test-results/html/index.html`

---

## Key Test Expectations

### Test 1: App Loading
- ✓ Page loads within 10 seconds
- ✓ No white screen or errors
- ✓ AP Operations tab is visible

### Test 2 & 3: Escalate Button & Modal
- ✓ Button found in Exceptions panel
- ✓ Modal title: "Escalate via SQL Alert"
- ✓ 4 checkboxes: Amount Mismatch, No PO Reference, Critical Overdue, Missing GSTIN
- ✓ NO email input field (configured server-side)
- ✓ All checkboxes checked by default

### Test 4: Escalation Execution
- ✓ Success message appears within 10 seconds
- ✓ Message confirms email will be sent
- ✓ No error toasts appear

### Test 5: Chat History
- ✓ History icon is clickable
- ✓ History panel opens
- ✓ Past sessions (if any) are listed

### Test 6: Chat Messages
- ✓ Message sends successfully
- ✓ Response appears within 30 seconds
- ✓ Response contains actual data (not generic)

### Test 7: History Persistence
- ✓ New chat session appears in history
- ✓ Can click to restore conversation

---

## Prerequisites

### For Automated Testing
- Node.js v25.6.1+ (installed)
- npm v11.9.0+ (installed)
- Playwright dependencies (will install: `npm install -D @playwright/test`)
- Browser (Chromium - installed via `npx playwright install chromium`)
- Network access to: `https://akash-finance-demo-1444828305810485.aws.databricksapps.com`
- Databricks SSO login (should already be active in browser)

### For Manual Testing
- Modern web browser (Chrome, Edge, Firefox, Safari)
- Network access to the app URL
- Databricks SSO authentication

---

## File Locations

```
/Users/akash.s/finance & accounting demo/
├── tests/
│   ├── test_e2e_deployed.spec.ts      (NEW - 7 automated tests)
│   ├── test_frontend.spec.ts          (existing - local dev tests)
│   └── playwright.config.ts           (UPDATED)
├── E2E_TEST_GUIDE.md                  (NEW - testing guide)
├── TEST_SETUP_SUMMARY.md              (THIS FILE)
├── app/
│   └── frontend/
│       └── package.json
└── test-results/                      (AUTO-GENERATED - screenshots & reports)
    ├── *.png                          (test screenshots)
    └── html/
        └── index.html                 (report)
```

---

## Next Steps

1. **Review the test guide:** Read `E2E_TEST_GUIDE.md` for detailed test procedures
2. **Install dependencies:** Run `npm install -D @playwright/test` in app/frontend
3. **Run tests:** Execute the test command above with the app URL
4. **Check results:** Review screenshots and HTML report
5. **Report issues:** Document any failures with exact error messages

---

## Troubleshooting

### Network Error Installing Playwright
If you see `ECONNREFUSED` when installing:
- This environment has no npm registry access
- Use manual testing approach instead (see E2E_TEST_GUIDE.md)
- Or run tests in an environment with network access

### Tests Timeout
- Deployed app may be slow initially
- Extend timeout: Edit `playwright.config.ts`, change `timeout: 60_000` to `timeout: 120_000`

### Escalate Button Not Found
- Ensure you're on the AP Operations tab
- Scroll down - Exceptions panel may be below the fold
- Check if layout is responsive/mobile (try zooming out)

### Chat Tests Fail
- Check browser DevTools Console (F12) for JS errors
- Chat backend may need 30 seconds to respond
- Verify network requests to `/api/*` endpoints succeed

---

## Contact

For questions about the test setup or results, refer to:
- Test file: `tests/test_e2e_deployed.spec.ts` (contains selector strategies)
- Test guide: `E2E_TEST_GUIDE.md` (detailed manual procedures)
- Playwright docs: https://playwright.dev/docs/intro
