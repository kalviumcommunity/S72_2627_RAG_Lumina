import { expect, test } from "@playwright/test";

import { signInAs, watchErrors } from "./helpers";

/** Which pages each role may open, and the heading each page shows (role gate otherwise). */
const PAGES: [path: string, heading: string, minimumRole: number][] = [
  ["/", "Ask the approved protocols", 0],
  ["/library", "Documents", 1],
  ["/review/amendments", "Amendments", 1],
  ["/review/conflicts", "Conflicts", 1],
  ["/review/feedback", "Feedback", 1],
  ["/admin", "Admin", 3],
  ["/admin/audit", "Audit log", 3],
];
/** Addresses from before the restructure keep working (bookmarks, old links in e-mails). */
const OLD_ADDRESSES: [from: string, to: string][] = [
  ["/admin/documents", "/library"],
  ["/admin/supersessions", "/review/amendments"],
  ["/admin/conflicts", "/review/conflicts"],
  ["/admin/feedback", "/review/feedback"],
  ["/admin/overview", "/admin"],
  ["/admin/dashboard", "/admin"],
  ["/review", "/review/amendments"],
];
const USERS: [name: string, rank: number][] = [
  ["Dr Kavya Rao", 0],
  ["Dr Meera Nair", 1],
  ["Dr Sana Qureshi", 2],
  ["Nikhil Desai", 3],
];

test("the login page is the first page and lists every demo role", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("/");
  await expect(
    page.getByRole("heading", { level: 1, name: "Answers you can trace to the clause." }),
  ).toBeVisible();
  const demoUsers = page.getByRole("region", { name: "Demo users" });
  for (const role of ["Clinician", "Document author", "Approver", "Administrator"]) {
    await expect(demoUsers.getByText(role, { exact: true })).toBeVisible();
  }
  await expect(page.getByRole("contentinfo", { name: "Intended use" })).toBeVisible();
  expect(errors).toEqual([]);
});

for (const [name, rank] of USERS) {
  test(`${name}: every page loads, or is refused for the role`, async ({ page }) => {
    const errors = watchErrors(page);
    await signInAs(page, name);
    for (const [path, heading, minimum] of PAGES) {
      await page.goto(path);
      const expected = rank >= minimum ? heading : "Not available for your role";
      await expect(page.getByRole("heading", { level: 1, name: expected, exact: true })).toBeVisible();
      await expect(page.getByRole("alert").filter({ hasText: "Something went wrong" })).toHaveCount(0);
    }
    await page.goto("/no-such-page");
    await expect(page.getByRole("heading", { name: "Page not found" })).toBeVisible();
    expect(errors).toEqual([]);
  });
}

test("old addresses redirect to where the page lives now", async ({ page }) => {
  await signInAs(page, "Nikhil Desai");
  for (const [from, to] of OLD_ADDRESSES) {
    await page.goto(from);
    await expect(page).toHaveURL(new RegExp(`${to}$`));
  }
});

test("the top navigation has one entry per section and each section has its own tabs", async ({ page }) => {
  await signInAs(page, "Nikhil Desai");
  const main = page.getByRole("navigation", { name: "Main" });
  await expect(main.getByRole("link")).toHaveText(["Ask", "Library", "Review", "Admin"]);
  await main.getByRole("link", { name: "Review" }).click();
  await expect(page).toHaveURL(/\/review\/amendments$/);
  const queues = page.getByRole("navigation", { name: "Review queues" });
  await queues.getByRole("link", { name: /Conflicts/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Conflicts" })).toBeVisible();
  await main.getByRole("link", { name: "Admin" }).click();
  await page
    .getByRole("navigation", { name: "Administration" })
    .getByRole("link", { name: "Audit log" })
    .click();
  await expect(page.getByRole("heading", { level: 1, name: "Audit log" })).toBeVisible();
});

test("the admin page shows AI usage, users and every record list", async ({ page }) => {
  await signInAs(page, "Nikhil Desai");
  await page.goto("/admin");
  await expect(page.getByText("Answered with citations")).toBeVisible();
  await page.getByRole("tab", { name: "AI usage" }).click();
  await expect(page.getByText("How the AI is set up")).toBeVisible();
  await expect(page.getByRole("table", { name: "Recent decisions" })).toBeVisible();
  const tabs: [RegExp, string][] = [
    [/^Users/, "Dr Kavya Rao"],
    [/^Documents/, "P-ICU-07"],
    [/^Amendments/, "P-ICU-07 §4.2"],
    [/^Conflicts/, ""],
    [/^Feedback/, ""],
  ];
  for (const [tab, text] of tabs) {
    await page.getByRole("tab", { name: tab }).click();
    await expect(page.getByRole("tabpanel")).toContainText(text);
  }
});

test("a document opens with its versions and indexed clauses", async ({ page }) => {
  await signInAs(page, "Dr Sana Qureshi");
  await page.goto("/library");
  await page.getByRole("link", { name: /^P-ICU-07 / }).click();
  await expect(page).toHaveURL(/\/library\/[0-9a-f-]+$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Heparin Infusion Protocol (Adult ICU)" }),
  ).toBeVisible();
  await expect(page.getByText(/Amended by C-2026-09/)).toBeVisible();
  await page
    .getByRole("button", { name: /Show indexed clauses/ })
    .first()
    .click();
  await expect(page.getByText(/tokens/).first()).toBeVisible();
});

test("the phone layout keeps the Ask page title and input visible @phone", async ({ page }) => {
  await signInAs(page, "Dr Kavya Rao");
  await expect(page.getByRole("heading", { name: "Ask the approved protocols" })).toBeInViewport();
  await expect(page.getByRole("textbox", { name: /Ask about an approved protocol/i })).toBeInViewport();
});
