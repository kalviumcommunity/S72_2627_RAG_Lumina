import { expect, type Page } from "@playwright/test";

/** Demo sign-in: pick a seeded user on the login screen. */
export async function signInAs(page: Page, displayName: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(displayName) }).click();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
}

export async function ask(page: Page, question: string): Promise<void> {
  const box = page.getByRole("textbox", { name: /Ask about an approved protocol/i });
  await box.fill(question);
  await box.press("Enter");
}

/** Collects uncaught page errors and console errors so a test can assert the page loaded cleanly. */
export function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return errors;
}
