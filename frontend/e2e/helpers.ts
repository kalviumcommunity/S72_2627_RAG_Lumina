import { expect, type Page } from "@playwright/test";

/** Demo sign-in: pick a seeded user on the login screen. */
export async function signInAs(page: Page, displayName: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: new RegExp(displayName) }).click();
  await expect(page.getByRole("button", { name: "Account and navigation menu" })).toBeVisible();
}

export async function ask(page: Page, question: string): Promise<void> {
  const box = page.getByRole("textbox", { name: /Ask about an approved protocol/i });
  await box.fill(question);
  await box.press("Enter");
}
