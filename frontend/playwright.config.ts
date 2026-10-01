import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running Lumina (API + built web app on one origin, e.g. port 8001):
 *   backend: uvicorn app.main:app --port 8001   (after `pnpm build`, the API serves frontend/dist)
 *   then:    pnpm e2e
 * Browser: Playwright's bundled Chromium by default. Override with E2E_CHANNEL (e.g. "msedge" on
 * Windows) or E2E_CHROMIUM_PATH (a Chromium binary already on the machine).
 */
const channel = process.env.E2E_CHANNEL || undefined;
const executablePath = process.env.E2E_CHROMIUM_PATH || undefined;
const browser = { channel, launchOptions: executablePath ? { executablePath } : {} };

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 45_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:8001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], ...browser } },
    { name: "phone", use: { ...devices["Pixel 7"], ...browser }, grep: /@phone/ },
  ],
});
