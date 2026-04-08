import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.APP_URL || "http://localhost:5173";

export default defineConfig({
  testDir: "./",
  testMatch: "test_frontend.spec.ts",
  timeout: 30_000,
  retries: 1,
  reporter: [["list"], ["html", { outputFolder: "../test-results/html", open: "never" }]],
  use: {
    baseURL: BASE_URL,
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
});
