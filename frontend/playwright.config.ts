import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running ProtoCite (API + built web app on one origin):
 *   ..\protocite.ps1 start   then   pnpm e2e
 * Uses the installed Microsoft Edge (channel "msedge"), so no browser download is needed.
 * Answers come from the live pipeline, so each run makes a few LLM calls.
 */
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
    channel: process.env.E2E_CHANNEL ?? "msedge",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Edge"], channel: process.env.E2E_CHANNEL ?? "msedge" } },
    {
      name: "phone",
      use: { ...devices["Pixel 7"], channel: process.env.E2E_CHANNEL ?? "msedge" },
      grep: /@phone/,
    },
  ],
});
