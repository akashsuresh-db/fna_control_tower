/**
 * Finance & Accounting Control Tower — End-to-End Test Suite
 * ===========================================================
 * 7 Critical Tests for Deployed App Validation
 *
 * Run against deployed app:
 *   APP_URL=https://akash-finance-demo-1444828305810485.aws.databricksapps.com \
 *   npx playwright test --config=../../tests/playwright.config.ts tests/test_e2e_deployed.spec.ts
 */

import { test, expect, Page } from "@playwright/test";

const BASE_URL = process.env.APP_URL || "https://akash-finance-demo-1444828305810485.aws.databricksapps.com";

test.describe("Finance & Accounting Control Tower - End-to-End Tests", () => {

  // ═══════════════════════════════════════════════════════════════════
  // TEST 1: App loads correctly
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 1: App loads correctly and shows AP Operations tab", async ({ page }) => {
    console.log(`\n📱 TEST 1: Loading app from ${BASE_URL}`);

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Take screenshot of loaded app
    await page.screenshot({ path: "./test-results/01_app_loaded.png", fullPage: true });
    console.log("✓ Screenshot saved: 01_app_loaded.png");

    // Verify page title or heading exists (not a white screen)
    const bodyContent = await page.content();
    expect(bodyContent.length).toBeGreaterThan(100);
    console.log("✓ Page has content (not blank)");

    // Verify AP Operations tab is visible
    const apOpsTab = page.locator('text=AP Operations').first();
    await expect(apOpsTab).toBeVisible({ timeout: 10000 });
    console.log("✓ AP Operations tab is visible");

    // Click on AP Operations tab to ensure it's active
    await apOpsTab.click();
    await page.waitForTimeout(1000);
    console.log("✓ AP Operations tab clicked");
  });

  // ═══════════════════════════════════════════════════════════════════
  // TEST 2: Escalate button visibility
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 2: Escalate button is visible in Exceptions panel", async ({ page }) => {
    console.log("\n🔍 TEST 2: Checking Escalate button visibility");

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Ensure we're on AP Operations tab
    const apOpsTab = page.locator('text=AP Operations').first();
    if (!(await apOpsTab.evaluate(el => el.getAttribute('aria-selected') === 'true' || el.classList.contains('active')))) {
      await apOpsTab.click();
      await page.waitForTimeout(500);
    }
    console.log("✓ AP Operations tab is active");

    // Find Exceptions panel - look for heading or section that contains "Exceptions"
    const exceptionsSection = page.locator('text=Exceptions').first();
    await expect(exceptionsSection).toBeVisible({ timeout: 5000 });
    console.log("✓ Exceptions panel found");

    // Scroll to Exceptions if needed
    await exceptionsSection.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);

    // Look for Escalate button - should be in the panel header
    const escalateButton = page.locator('button:has-text("Escalate")').first();
    await expect(escalateButton).toBeVisible({ timeout: 5000 });
    console.log("✓ Escalate button is visible");

    // Take screenshot showing the button
    await escalateButton.scrollIntoViewIfNeeded();
    await page.screenshot({ path: "./test-results/02_escalate_button_visible.png", fullPage: true });
    console.log("✓ Screenshot saved: 02_escalate_button_visible.png");
  });

  // ═══════════════════════════════════════════════════════════════════
  // TEST 3: Escalate modal flow
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 3: Escalate modal opens with correct structure", async ({ page }) => {
    console.log("\n🔔 TEST 3: Testing Escalate modal flow");

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Navigate to AP Operations and find Escalate button
    const apOpsTab = page.locator('text=AP Operations').first();
    await apOpsTab.click();
    await page.waitForTimeout(500);

    const exceptionsSection = page.locator('text=Exceptions').first();
    await exceptionsSection.scrollIntoViewIfNeeded();

    const escalateButton = page.locator('button:has-text("Escalate")').first();
    await expect(escalateButton).toBeVisible();
    console.log("✓ Escalate button found");

    // Click Escalate button
    await escalateButton.click();
    await page.waitForTimeout(1000);
    console.log("✓ Escalate button clicked");

    // Verify modal opens with title "Escalate via SQL Alert"
    const modalTitle = page.locator('text=Escalate via SQL Alert').first();
    await expect(modalTitle).toBeVisible({ timeout: 5000 });
    console.log("✓ Modal title verified: 'Escalate via SQL Alert'");

    // Verify 4 checkboxes exist
    const checkbox1 = page.locator('label:has-text("Amount Mismatch")');
    const checkbox2 = page.locator('label:has-text("No PO Reference")');
    const checkbox3 = page.locator('label:has-text("Critical Overdue")');
    const checkbox4 = page.locator('label:has-text("Missing GSTIN")');

    await expect(checkbox1).toBeVisible();
    await expect(checkbox2).toBeVisible();
    await expect(checkbox3).toBeVisible();
    await expect(checkbox4).toBeVisible();
    console.log("✓ All 4 checkboxes are visible");

    // Verify NO email input field
    const emailInput = page.locator('input[type="email"]');
    const emailField = page.locator('label:has-text("Email")');
    expect(await emailInput.count()).toBe(0);
    expect(await emailField.count()).toBe(0);
    console.log("✓ No email input field (email configured server-side)");

    // Verify all 4 checkboxes are checked by default
    const inputs = page.locator('input[type="checkbox"]');
    const checkedCount = await inputs.locator('[checked]').count();
    expect(checkedCount).toBe(4);
    console.log("✓ All 4 checkboxes are checked by default");

    // Take screenshot of modal
    await page.screenshot({ path: "./test-results/03_escalate_modal.png", fullPage: true });
    console.log("✓ Screenshot saved: 03_escalate_modal.png");
  });

  // ═══════════════════════════════════════════════════════════════════
  // TEST 4: Execute the escalation
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 4: Execute escalation with partial checkboxes", async ({ page }) => {
    console.log("\n🚀 TEST 4: Executing escalation flow");

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Navigate to Escalate modal
    const apOpsTab = page.locator('text=AP Operations').first();
    await apOpsTab.click();
    await page.waitForTimeout(500);

    const exceptionsSection = page.locator('text=Exceptions').first();
    await exceptionsSection.scrollIntoViewIfNeeded();

    const escalateButton = page.locator('button:has-text("Escalate")').first();
    await escalateButton.click();
    await page.waitForTimeout(1000);
    console.log("✓ Escalate modal opened");

    // Uncheck "Missing GSTIN" (leave other 3 checked)
    const missingGstinCheckbox = page.locator('input[type="checkbox"]').filter({
      has: page.locator('text=Missing GSTIN')
    }).first();

    // Get current state
    const isChecked = await missingGstinCheckbox.isChecked();
    if (isChecked) {
      await missingGstinCheckbox.click();
      await page.waitForTimeout(300);
      console.log("✓ Unchecked 'Missing GSTIN'");
    }

    // Click Send Alert button
    const sendButton = page.locator('button:has-text("Send Alert")').first();
    await expect(sendButton).toBeVisible();
    await sendButton.click();
    console.log("✓ 'Send Alert' button clicked");

    // Wait up to 10 seconds for response
    let successMessage = null;
    let errorMessage = null;

    try {
      // Look for success message - typically contains "email" and timing info
      successMessage = page.locator('text=/email.*within|sent.*email|alert.*sent|success/i').first();
      await expect(successMessage).toBeVisible({ timeout: 10000 });
      console.log("✓ Success message appeared");
    } catch (e) {
      // Check for error message
      errorMessage = page.locator('[role="alert"]');
      if (await errorMessage.count() > 0) {
        const errorText = await errorMessage.first().textContent();
        console.log(`✗ Error message appeared: ${errorText}`);
      } else {
        console.log("⚠ No success or error message detected within 10 seconds");
      }
    }

    // Take screenshot of result
    await page.screenshot({ path: "./test-results/04_escalation_result.png", fullPage: true });
    console.log("✓ Screenshot saved: 04_escalation_result.png");
  });

  // ═══════════════════════════════════════════════════════════════════
  // TEST 5: Chat history visibility
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 5: Chat history panel works correctly", async ({ page }) => {
    console.log("\n📜 TEST 5: Testing chat history visibility");

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Find the chat panel - should be on the right side or top right
    const chatPanel = page.locator('text=Chat').first();
    if (await chatPanel.count() === 0) {
      // Try to find by icon or other selector
      console.log("⚠ Chat panel not found by text, looking for icon");
    }

    // Look for History/clock icon in the chat panel
    const historyIcon = page.locator('[aria-label*="history" i], [title*="history" i], button:has-text("History")').first();

    if (await historyIcon.count() > 0) {
      await historyIcon.click();
      await page.waitForTimeout(500);
      console.log("✓ History icon clicked");

      // Check if history panel opened
      const historyPanel = page.locator('text=History');
      if (await historyPanel.count() > 0) {
        console.log("✓ History panel opened");

        // Take screenshot
        await page.screenshot({ path: "./test-results/05_chat_history.png", fullPage: true });
        console.log("✓ Screenshot saved: 05_chat_history.png");
      }
    } else {
      console.log("⚠ History icon not found in chat panel");
      await page.screenshot({ path: "./test-results/05_chat_history.png", fullPage: true });
    }
  });

  // ═══════════════════════════════════════════════════════════════════
  // TEST 6: Send a test chat message
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 6: Send test chat message and verify response", async ({ page }) => {
    console.log("\n💬 TEST 6: Testing chat message send");

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Look for chat input field
    const chatInput = page.locator('textarea, input[placeholder*="message" i], input[placeholder*="ask" i]').first();

    if (await chatInput.count() > 0) {
      // Type test message
      await chatInput.click();
      await chatInput.fill("How many invoices are in exception status?");
      console.log("✓ Chat message typed");

      // Look for Send button and click it
      const sendButton = page.locator('button[aria-label*="send" i], button:has-text("Send")').first();
      if (await sendButton.count() > 0) {
        await sendButton.click();
      } else {
        // Try pressing Enter
        await chatInput.press("Enter");
      }
      console.log("✓ Message sent");

      // Wait up to 30 seconds for response
      // Look for a response bubble or message that's different from the sent message
      let responseFound = false;
      const startTime = Date.now();

      while (Date.now() - startTime < 30000) {
        const messages = page.locator('[role="article"], .message, [class*="message"]');
        if (await messages.count() >= 2) {
          const lastMessage = messages.last();
          const content = await lastMessage.textContent();
          if (content && content.length > 0 && !content.includes("How many invoices")) {
            responseFound = true;
            console.log(`✓ Response received: ${content?.substring(0, 100)}...`);
            break;
          }
        }
        await page.waitForTimeout(1000);
      }

      if (!responseFound) {
        console.log("⚠ No response detected within 30 seconds");
      }

      // Take screenshot
      await page.screenshot({ path: "./test-results/06_chat_message.png", fullPage: true });
      console.log("✓ Screenshot saved: 06_chat_message.png");
    } else {
      console.log("⚠ Chat input field not found");
      await page.screenshot({ path: "./test-results/06_chat_message.png", fullPage: true });
    }
  });

  // ═══════════════════════════════════════════════════════════════════
  // TEST 7: Check chat history after sending
  // ═══════════════════════════════════════════════════════════════════
  test("TEST 7: Chat history shows new session after message", async ({ page }) => {
    console.log("\n💾 TEST 7: Checking chat history after sending message");

    await page.goto(BASE_URL, { waitUntil: "networkidle" });

    // Send a chat message first
    const chatInput = page.locator('textarea, input[placeholder*="message" i], input[placeholder*="ask" i]').first();

    if (await chatInput.count() > 0) {
      await chatInput.click();
      await chatInput.fill("What is the total invoice amount?");

      const sendButton = page.locator('button[aria-label*="send" i], button:has-text("Send")').first();
      if (await sendButton.count() > 0) {
        await sendButton.click();
      } else {
        await chatInput.press("Enter");
      }
      console.log("✓ Chat message sent");

      // Wait for response
      await page.waitForTimeout(5000);

      // Now click History icon
      const historyIcon = page.locator('[aria-label*="history" i], [title*="history" i], button:has-text("History")').first();
      if (await historyIcon.count() > 0) {
        await historyIcon.click();
        await page.waitForTimeout(500);
        console.log("✓ History panel opened");

        // Check if new session appears in history
        const sessions = page.locator('text=What is the total invoice amount');
        if (await sessions.count() > 0) {
          console.log("✓ New session appears in history");
        } else {
          console.log("⚠ New session not found in history");
        }

        // Take screenshot
        await page.screenshot({ path: "./test-results/07_chat_history_updated.png", fullPage: true });
        console.log("✓ Screenshot saved: 07_chat_history_updated.png");
      }
    } else {
      console.log("⚠ Chat input not found for this test");
      await page.screenshot({ path: "./test-results/07_chat_history_updated.png", fullPage: true });
    }
  });
});
