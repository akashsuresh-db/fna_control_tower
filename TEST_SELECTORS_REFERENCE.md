# Test Selectors & Element Locator Reference

## Overview
This document describes the element selectors and locator strategies used in the automated tests. Use this to understand how the tests find elements and for manual testing reference.

---

## Test 1: App Loading

### Selectors Used
```typescript
// AP Operations Tab
page.locator('text=AP Operations').first()

// Page Body Content Check
page.content()  // Verify > 100 chars (not blank)
```

### What the Test Does
1. Navigates to the app URL
2. Takes a screenshot of the loaded page
3. Verifies page has content (not a blank/white screen)
4. Finds the "AP Operations" tab using text matching
5. Verifies tab is visible (should be in viewport)

### Manual Testing Equivalent
1. Open URL in browser
2. Look for "AP Operations" as a visible tab/button
3. Verify page is fully loaded and not blank

### Expected DOM Structure
```html
<div class="tabs" or "tab-container">
  <button>AP Operations</button>  <!-- This is what test looks for -->
  <button>O2C Operations</button>
  <button>R2R Operations</button>
</div>

<main>
  <!-- Tab content renders here -->
</main>
```

---

## Test 2: Escalate Button Visibility

### Selectors Used
```typescript
// AP Operations Tab (click if not active)
page.locator('text=AP Operations').first()

// Exceptions Panel
page.locator('text=Exceptions').first()

// Escalate Button
page.locator('button:has-text("Escalate")').first()
```

### What the Test Does
1. Ensures AP Operations tab is active
2. Finds the "Exceptions" panel by text content
3. Scrolls to the panel if needed
4. Looks for a button with text "Escalate"
5. Verifies button is visible (in viewport)

### Manual Testing Equivalent
1. Click on AP Operations tab
2. Scroll down to find the Exceptions panel
3. Look for a button labeled "Escalate" in the panel header
4. Verify it's not disabled/grayed out

### Expected DOM Structure
```html
<section class="exceptions-panel">
  <header>
    <h3>Exceptions</h3>
    <button class="escalate-btn">Escalate</button>  <!-- This button -->
  </header>
  
  <div class="exceptions-list">
    <!-- List of exceptions -->
  </div>
</section>
```

### Locator Strategies
- **Primary:** `button:has-text("Escalate")` - CSS selector matching button with Escalate text
- **Fallback:** By aria-label if button doesn't have text
- **Last resort:** By data-testid if available

---

## Test 3: Escalate Modal Flow

### Selectors Used
```typescript
// Modal Title
page.locator('text=Escalate via SQL Alert').first()

// Checkboxes (by label text)
page.locator('label:has-text("Amount Mismatch")')
page.locator('label:has-text("No PO Reference")')
page.locator('label:has-text("Critical Overdue")')
page.locator('label:has-text("Missing GSTIN")')

// Email Input (should NOT exist)
page.locator('input[type="email"]')
page.locator('label:has-text("Email")')

// Input Checkboxes
page.locator('input[type="checkbox"]')

// Send Button
page.locator('button:has-text("Send Alert")')
```

### What the Test Does
1. Clicks the Escalate button (from Test 2)
2. Waits for modal to appear (1 second timeout)
3. Finds the modal title "Escalate via SQL Alert"
4. Verifies all 4 checkboxes are present with correct labels
5. Verifies NO email input field exists
6. Checks that all 4 checkboxes are pre-checked
7. Takes a screenshot of the modal

### Manual Testing Equivalent
1. Click the Escalate button
2. Look for modal with title "Escalate via SQL Alert"
3. Count the checkboxes - should be exactly 4
4. Verify labels match:
   - Amount Mismatch
   - No PO Reference
   - Critical Overdue (>60 days)
   - Missing GSTIN
5. Verify no email field
6. Verify all checkboxes are checked

### Expected DOM Structure
```html
<div class="modal-overlay">
  <div class="modal-content">
    <div class="modal-header">
      <h2>Escalate via SQL Alert</h2>
      <button class="close-btn">×</button>
    </div>
    
    <form>
      <div class="form-group">
        <label>
          <input type="checkbox" name="amount_mismatch" checked>
          Amount Mismatch
        </label>
      </div>
      
      <div class="form-group">
        <label>
          <input type="checkbox" name="no_po" checked>
          No PO Reference
        </label>
      </div>
      
      <div class="form-group">
        <label>
          <input type="checkbox" name="critical_overdue" checked>
          Critical Overdue (>60 days)
        </label>
      </div>
      
      <div class="form-group">
        <label>
          <input type="checkbox" name="missing_gstin" checked>
          Missing GSTIN
        </label>
      </div>
      
      <!-- NO email field here -->
      
      <button type="submit">Send Alert</button>
    </form>
  </div>
</div>
```

### Checkbox Verification Logic
```typescript
// Get all checkboxes
const inputs = page.locator('input[type="checkbox"]');

// Count checked ones
const checkedCount = await inputs.locator('[checked]').count();

// Should be 4
expect(checkedCount).toBe(4);
```

---

## Test 4: Execute Escalation

### Selectors Used
```typescript
// Missing GSTIN checkbox (to uncheck)
page.locator('input[type="checkbox"]').filter({
  has: page.locator('text=Missing GSTIN')
}).first()

// Send Alert button
page.locator('button:has-text("Send Alert")').first()

// Success message (multiple patterns)
page.locator('text=/email.*within|sent.*email|alert.*sent|success/i').first()

// Error alert (if failure)
page.locator('[role="alert"]')
```

### What the Test Does
1. Opens the Escalate modal (from Test 3)
2. Finds the "Missing GSTIN" checkbox
3. Unchecks it (leaves other 3 checked)
4. Clicks the "Send Alert" button
5. Waits up to 10 seconds for success/error message
6. Takes screenshot of the result

### Manual Testing Equivalent
1. Open the Escalate modal
2. Uncheck the "Missing GSTIN" checkbox
3. Click "Send Alert"
4. Wait and observe for success message
5. Screenshot the result

### Expected Success Message
Should contain keywords like:
- "email" + "within" = "email sent within ~60 seconds"
- "sent" + "email" = "alert sent via email"
- "success" + "alert" = "success, alert triggered"

### Checkbox Unchecking Logic
```typescript
const missingGstinCheckbox = page.locator('input[type="checkbox"]').filter({
  has: page.locator('text=Missing GSTIN')
}).first();

const isChecked = await missingGstinCheckbox.isChecked();
if (isChecked) {
  await missingGstinCheckbox.click();
}
```

---

## Test 5: Chat History Visibility

### Selectors Used
```typescript
// History Icon (multiple patterns)
page.locator('[aria-label*="history" i]')
page.locator('[title*="history" i]')
page.locator('button:has-text("History")')

// History Panel
page.locator('text=History').first()
```

### What the Test Does
1. Looks for chat panel on the page
2. Finds History icon (clock, calendar, or labeled button)
3. Clicks the History icon
4. Waits for history panel to open
5. Verifies panel is visible
6. Takes screenshot

### Manual Testing Equivalent
1. Look for AI chat panel (usually right side or top right)
2. Find the History button/icon (often a clock or calendar icon)
3. Click it
4. Verify a panel/drawer opens showing past sessions
5. Screenshot the result

### Expected DOM Structure
```html
<div class="chat-panel">
  <header>
    <h2>AI Chat Assistant</h2>
    <button aria-label="Chat History" title="View History">
      <Clock Icon />  <!-- or History Icon -->
    </button>
  </header>
  
  <div class="chat-messages">
    <!-- messages -->
  </div>
  
  <!-- When History button clicked: -->
  <aside class="history-panel">
    <h3>History</h3>
    <ul class="sessions">
      <li>Yesterday 3:45 PM</li>
      <li>Previous Session</li>
    </ul>
  </aside>
</div>
```

### Finding the History Icon
Strategies in order of preference:
1. `[aria-label*="history" i]` - Accessible label approach
2. `[title*="history" i]` - Tooltip approach
3. `button:has-text("History")` - Text matching
4. Look near chat header for icon buttons

---

## Test 6: Send Test Chat Message

### Selectors Used
```typescript
// Chat Input Field (multiple patterns)
page.locator('textarea')
page.locator('input[placeholder*="message" i]')
page.locator('input[placeholder*="ask" i]')

// Send Button
page.locator('button[aria-label*="send" i]')
page.locator('button:has-text("Send")')

// Check for Response
page.locator('[role="article"]')
page.locator('.message')
page.locator('[class*="message"]')
```

### What the Test Does
1. Finds the chat input field (textarea or input)
2. Clicks into the field
3. Types: "How many invoices are in exception status?"
4. Sends the message (Click Send or press Enter)
5. Waits up to 30 seconds for a response
6. Looks for any message that's not the sent message
7. Takes screenshot of conversation

### Manual Testing Equivalent
1. Find the chat input box
2. Click in it
3. Type: "How many invoices are in exception status?"
4. Press Enter or click Send
5. Wait up to 30 seconds
6. Look for a response message with actual numbers
7. Screenshot the result

### Expected DOM Structure
```html
<div class="chat-container">
  <div class="messages">
    <div class="message user">
      <p>How many invoices are in exception status?</p>
      <span class="time">Just now</span>
    </div>
    
    <!-- After response: -->
    <div class="message assistant">
      <p>There are currently 45 invoices in exception status...</p>
      <span class="time">2 seconds ago</span>
    </div>
  </div>
  
  <form class="chat-input">
    <textarea placeholder="Ask about your finances..."></textarea>
    <button aria-label="Send message">Send</button>
  </form>
</div>
```

### Response Detection Logic
```typescript
const startTime = Date.now();
while (Date.now() - startTime < 30000) {
  const messages = page.locator('[role="article"], .message');
  if (await messages.count() >= 2) {
    const lastMessage = messages.last();
    const content = await lastMessage.textContent();
    // If last message is different from our sent message and has content
    if (content && !content.includes("How many invoices")) {
      // We got a response!
      break;
    }
  }
  await page.waitForTimeout(1000);
}
```

---

## Test 7: Chat History Persistence

### Selectors Used
```typescript
// Same as Test 6
page.locator('textarea')
page.locator('button[aria-label*="send" i]')

// History Icon
page.locator('[aria-label*="history" i]')

// Check if new message in history
page.locator('text=What is the total invoice amount')
```

### What the Test Does
1. Sends a new chat message: "What is the total invoice amount?"
2. Waits 5 seconds for response
3. Opens the History panel
4. Looks for the new message in the session list
5. Takes screenshot

### Manual Testing Equivalent
1. Send a chat message
2. Wait for it to be received
3. Click the History icon
4. Look at the session list
5. Find your new message in the list
6. Optionally click it to restore the session
7. Screenshot the result

### Expected Behavior
- After sending a message, the chat session is saved
- History panel shows a new session with:
  - Timestamp (e.g., "Today 3:45 PM")
  - Preview of first message (e.g., "What is the total invoice amount?")
- Clicking the session restores the conversation
- All messages are still visible

---

## Common Locator Patterns

### Text Matching (Recommended)
```typescript
// Find element by exact text
page.locator('text=Send Alert')

// Find element containing text (any case)
page.locator('button:has-text("Send Alert")')

// Find by text with regex
page.locator('text=/send|submit/i')
```

### Attribute Matching
```typescript
// By input type
page.locator('input[type="checkbox"]')

// By placeholder
page.locator('input[placeholder*="message"]')

// By aria-label
page.locator('[aria-label="Send"]')

// By data-testid (if available)
page.locator('[data-testid="escalate-button"]')
```

### Hierarchical Selectors
```typescript
// Within parent
page.locator('section:has-text("Exceptions")').locator('button:has-text("Escalate")')

// With checkbox inside label
page.locator('label:has-text("Amount Mismatch")').locator('input[type="checkbox"]')
```

### First/Last Matching
```typescript
// Get first matching element
page.locator('button:has-text("Escalate")').first()

// Get last matching element
page.locator('.message').last()

// Get nth element
page.locator('button').nth(2)
```

---

## Debugging Selectors

### Test If Element Exists
```typescript
if (await page.locator('button:has-text("Escalate")').count() > 0) {
  console.log("Button found!");
}
```

### Get Text of Element
```typescript
const text = await page.locator('text=AP Operations').textContent();
console.log(`Tab text: ${text}`);
```

### Check If Visible
```typescript
const isVisible = await page.locator('button:has-text("Send Alert")').isVisible();
console.log(`Button visible: ${isVisible}`);
```

### List All Matching Elements
```typescript
const buttons = page.locator('button');
console.log(`Found ${await buttons.count()} buttons`);
for (let i = 0; i < await buttons.count(); i++) {
  const text = await buttons.nth(i).textContent();
  console.log(`Button ${i}: ${text}`);
}
```

### Wait for Element
```typescript
// Wait up to 5 seconds for element to appear
await page.locator('button:has-text("Escalate")').waitFor({ timeout: 5000 });
```

---

## Accessibility-First Approach

All selectors prioritize accessibility:

1. **Text content** (users can see it)
2. **ARIA labels** (accessible labels)
3. **Placeholders** (input hints)
4. **Data attributes** (if no other option)

This ensures tests are:
- Resilient to style/layout changes
- Similar to how real users interact
- Help identify accessibility issues
- Future-proof against refactoring

---

## Troubleshooting Selector Failures

### Selector Not Found
1. Open DevTools (F12)
2. Use Ctrl+F to search for the text
3. Verify it exists on the page
4. Check if it's hidden/outside viewport
5. Try zooming out to see full layout

### Selector Finds Wrong Element
1. Use `.first()` or `.nth()` to target specific match
2. Use hierarchical selectors to narrow scope
3. Add more specific text (e.g., "Escalate" vs "Escalate via SQL Alert")

### Selector Works in Manual Test But Not Automated
1. Check timing - element may not be loaded yet
2. Add wait: `await page.waitForSelector('...')`
3. Check for dynamic content - selector may change
4. Look at network tab - is backend call completing?

---

## Reference Implementation

For complete implementation examples, see:
```
tests/test_e2e_deployed.spec.ts
```

Specific test sections:
- **TEST 1:** Lines 30-55
- **TEST 2:** Lines 60-95
- **TEST 3:** Lines 100-165
- **TEST 4:** Lines 170-245
- **TEST 5:** Lines 250-295
- **TEST 6:** Lines 300-375
- **TEST 7:** Lines 380-435
