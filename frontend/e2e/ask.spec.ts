import { expect, test } from "@playwright/test";

import { ask, signInAs } from "./helpers";

test.describe("clinician asks a question", () => {
  test("gets a verified, cited answer and opens the highlighted clause @phone", async ({ page }) => {
    await signInAs(page, "Dr Kavya Rao");
    await ask(page, "What is the heparin nomogram step for aPTT above 100?");

    const answer = page.getByTestId("answer-text");
    await expect(answer).toContainText(/1 hour/i);
    await expect(page.getByText("Verified against sources")).toBeVisible();

    // The newest circular overrides the protocol clause, and says so.
    const sources = page.getByRole("region", { name: "Sources cited" });
    await expect(sources).toContainText("C-2026-09");
    await expect(sources).toContainText("Amends P-ICU-07");

    await answer.getByRole("button", { name: /Open source S\d+: C-2026-09/ }).first().click();
    const sheet = page.getByRole("dialog");
    await expect(sheet).toContainText("Heparin Nomogram Amendment");
    const cited = sheet.locator('section[aria-current="true"]');
    await expect(cited).toContainText("Cited clause");
    await expect(cited).toContainText("Above 100");
    await expect(cited).toBeInViewport();
  });

  test("patient-specific dosing is refused, identifiers are removed, contacts are offered", async ({ page }) => {
    await signInAs(page, "Dr Kavya Rao");
    await ask(page, "What heparin bolus should I give Mr Ramesh Kumar, 72 kg?");

    await expect(page.getByText(/needs a clinical decision/i)).toBeVisible();
    await expect(page.getByTestId("answer-text")).toHaveCount(0);
    await expect(page.getByText(/Patient identifiers were removed/)).toBeVisible();
    // The question bubble switches to the redacted text once the server reports what it removed.
    await expect(page.getByText(/Ramesh Kumar/)).toHaveCount(0);
    await expect(page.getByRole("link", { name: /^Call / }).first()).toHaveAttribute("href", /^tel:/);
  });

  test("a question no approved document covers is answered with 'not found', not a guess", async ({ page }) => {
    await signInAs(page, "Dr Kavya Rao");
    await ask(page, "What are the visiting hours for the maternity ward?");

    await expect(page.getByText("No approved document covers this")).toBeVisible();
    await expect(page.getByTestId("answer-text")).toHaveCount(0);
  });
});

test.describe("roles and admin", () => {
  test("a clinician cannot open admin pages", async ({ page }) => {
    await signInAs(page, "Dr Kavya Rao");
    await page.goto("/admin/audit");
    await expect(page.getByText("Not available for your role")).toBeVisible();
  });

  test("an administrator sees the dashboard and a verified audit chain", async ({ page }) => {
    await signInAs(page, "Nikhil Desai");
    await page.goto("/admin/dashboard");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Questions per day")).toBeVisible();

    await page.goto("/admin/audit");
    await page.getByRole("button", { name: "Check chain" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Chain intact" })).toBeVisible();
  });

  test("an approver sees suggested amendments with their evidence", async ({ page }) => {
    await signInAs(page, "Dr Sana Qureshi");
    await page.goto("/admin/supersessions");
    await expect(page.getByRole("heading", { name: "Amendments" })).toBeVisible();
    await expect(page.getByText(/In force/)).toBeVisible();
    await expect(page.getByText(/Amends: /).first()).toBeVisible();
  });
});

test("the web app is installable: manifest and service worker", async ({ page }) => {
  await page.goto("/");
  const manifest = await page.request.get("/manifest.webmanifest");
  expect(manifest.ok()).toBe(true);
  const registered = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return registration.active?.scriptURL ?? null;
  });
  expect(registered).toMatch(/\/sw\.js$/);
});
