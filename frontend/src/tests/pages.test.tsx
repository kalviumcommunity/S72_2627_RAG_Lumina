/**
 * Every page, rendered on its own against a mocked API: it loads, shows its title and main content,
 * calls only the endpoints it should, and its main action works.
 */
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "../app/App";
import { AppShell } from "../app/layout/AppShell";
import { ToastProvider } from "../components/ui/Toast";
import { AdminOverviewPage } from "../features/admin/AdminOverviewPage";
import { AskPage } from "../features/ask/AskPage";
import { AuditPage } from "../features/audit/AuditPage";
import { LoginPage } from "../features/auth/LoginPage";
import { ConflictsPage } from "../features/conflicts/ConflictsPage";
import { DocumentDetailPage } from "../features/documents/DocumentDetailPage";
import { DocumentsPage } from "../features/documents/DocumentsPage";
import { FeedbackPage } from "../features/feedback/FeedbackPage";
import { SupersessionsPage } from "../features/supersessions/SupersessionsPage";
import type { Session } from "../lib/auth";
import type { Role } from "../lib/types";
import {
  adminConflict,
  answered,
  auditEvent,
  documentDetail,
  documentSummary,
  feedbackItem,
  historyItem,
  overview,
  referenceData,
  stats,
  supersession,
  user,
} from "./fixtures";
import { mockApi } from "./mockApi";
import { renderWithProviders } from "./render";

let session: Session | null = null;
const devLogin = vi.fn();
const signOut = vi.fn();
vi.mock("../app/providers", () => ({
  useAuth: () => ({
    session,
    lastExit: null,
    config: {
      dev_auth: true,
      oidc_enabled: false,
      session_idle_minutes: 15,
      llm_provider: "gemini",
      llm_model: "gemini-3.6-flash",
      demo_corpus: true,
    },
    devLogin,
    signOut,
  }),
}));

function signedInAs(role: Role | null) {
  session = role ? { token: "t", expiresAt: Date.now() + 600_000, user: user(role) } : null;
}

function sse(events: [string, unknown][]): Response {
  const body = events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join("");
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

/** The whole app (it brings its own router), for routing and role-gate tests. */
function renderApp(path: string) {
  window.history.pushState({}, "", path);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <TooltipPrimitive.Provider>
          <App />
        </TooltipPrimitive.Provider>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  devLogin.mockReset();
  signOut.mockReset();
});

describe("Login page (first screen)", () => {
  it("lists demo users by role and signs in the one picked", async () => {
    signedInAs(null);
    const api = mockApi({ "GET /auth/dev-users": [user("clinician"), user("admin")] });
    renderWithProviders(<LoginPage />);
    expect(
      screen.getByRole("heading", { level: 1, name: "Answers you can trace to the clause." }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Demo users" })).toBeInTheDocument();
    expect(screen.getByRole("contentinfo", { name: "Intended use" })).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /Demo clinician/ }));
    expect(devLogin).toHaveBeenCalledWith("clinician@demo.protocite.test");
    expect(screen.getByText(/Asks questions and opens the cited sources/)).toBeInTheDocument();
    expect(api.unmatched).toEqual([]);
  });
});

describe("Ask page (clinician)", () => {
  it("shows examples and recent questions, then a verified answer for a picked example", async () => {
    signedInAs("clinician");
    const api = mockApi({
      "GET /query/history": [historyItem()],
      "POST /query/stream": () =>
        sse([
          ["route", { route: "answer", reason: "lookup", redacted_question: "q", pii_redacted: false }],
          ["sources", { sources: [], timings_ms: {} }],
          ["answer", answered()],
          ["done", { query_id: "q-1" }],
        ]),
    });
    renderWithProviders(<AskPage />);
    expect(screen.getByRole("heading", { name: "Ask the approved protocols" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Recent questions" })).toHaveTextContent("Does Tazocin");

    await userEvent.click(screen.getByRole("button", { name: /heparin nomogram step for aPTT above 100/ }));
    expect(await screen.findByTestId("answer-text")).toHaveTextContent(
      "Hold the heparin infusion for 1 hour.",
    );
    expect(screen.getByText("Verified against sources")).toBeInTheDocument();
    expect(api.calls.some((c) => c.method === "POST" && c.path === "/query/stream")).toBe(true);
    expect(api.unmatched).toEqual([]);
  });

  it("typing a question and pressing Enter asks it", async () => {
    signedInAs("clinician");
    let asked = "";
    mockApi({
      "GET /query/history": [],
      "POST /query/stream": (_url: URL, init?: RequestInit) => {
        asked = (JSON.parse(init?.body as string) as { question: string }).question;
        return sse([
          ["error", { code: "internal_error", message: "The answer could not be produced safely." }],
        ]);
      },
    });
    renderWithProviders(<AskPage />);
    await userEvent.type(
      screen.getByRole("textbox", { name: /Ask about an approved protocol/ }),
      "Who do I call?{Enter}",
    );
    expect(await screen.findByText("No answer — nothing unverified was shown")).toBeInTheDocument();
    expect(asked).toBe("Who do I call?");
  });
});

describe("Admin page", () => {
  it("opens on the overview and every tab shows its records", async () => {
    signedInAs("admin");
    const api = mockApi({ "GET /admin/stats": stats(), "GET /admin/overview": overview() });
    renderWithProviders(<AdminOverviewPage />);
    expect(screen.getByRole("heading", { name: "Admin" })).toBeInTheDocument();
    expect(await screen.findByText("Answered with citations")).toBeInTheDocument();
    expect(screen.getByText("Versions awaiting approval →")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "AI usage" }));
    expect(screen.getByText("How the AI is set up")).toBeInTheDocument();
    expect(screen.getByText("gemini · gemini-3.6-flash")).toBeInTheDocument();
    expect(screen.getByText("90%")).toBeInTheDocument(); // 18 of 20 statements kept
    await userEvent.click(
      within(screen.getByRole("table", { name: "Recent decisions" })).getAllByText("Trace")[1]!,
    );
    expect(screen.getByText(/Removed by the verifier/)).toBeInTheDocument();
    expect(screen.getByText(/It is always safe/)).toBeInTheDocument();

    const tabs: [RegExp, string][] = [
      [/^Users/, "Dr Kavya Rao"],
      [/^Documents/, "Heparin Infusion Protocol (Adult ICU)"],
      [/^Amendments/, "P-ICU-07 §4.2"],
      [/^Conflicts/, "aPTT recheck: 6 h vs 4 h"],
      [/^Feedback/, "A newer circular applies"],
    ];
    for (const [tab, text] of tabs) {
      await userEvent.click(screen.getByRole("tab", { name: tab }));
      expect(screen.getByRole("tabpanel")).toHaveTextContent(text);
    }

    await userEvent.click(screen.getByRole("button", { name: "7 days" }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.path === "/admin/overview" && c.search === "?days=7")).toBe(true),
    );
    expect(api.unmatched).toEqual([]);
  });
});

describe("Document pages (author / approver)", () => {
  it("lists documents and filters to those awaiting approval", async () => {
    signedInAs("author");
    mockApi({
      "GET /documents": [
        documentSummary(),
        documentSummary({
          id: "doc-2",
          doc_code: "C-2026-14",
          title: "Pip-taz restriction",
          versions: [],
          current_version_id: null,
        }),
      ],
    });
    renderWithProviders(<DocumentsPage />, "/library");
    expect(screen.getByRole("heading", { name: "Documents" })).toBeInTheDocument();
    expect(await screen.findByText("Heparin Infusion Protocol (Adult ICU)")).toBeInTheDocument();
    expect(screen.getByText("Pip-taz restriction")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox", { name: "Search documents" }), "pip");
    expect(screen.queryByText("Heparin Infusion Protocol (Adult ICU)")).not.toBeInTheDocument();
  });

  it("opens the upload dialog with the reference data", async () => {
    signedInAs("author");
    const api = mockApi({ "GET /documents": [], "GET /admin/reference-data": referenceData() });
    renderWithProviders(<DocumentsPage />, "/library");
    await userEvent.click(screen.getByRole("button", { name: /Upload document/ }));
    expect(await screen.findByRole("dialog", { name: "Upload a document" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("option", { name: "Intensive Care" })).toBeInTheDocument());
    await userEvent.click(screen.getByRole("button", { name: /Upload as draft/ }));
    expect(screen.getByText("Choose a file to upload")).toBeInTheDocument();
    expect(api.unmatched).toEqual([]);
  });

  it("shows versions, the amendment and lets an approver approve a draft", async () => {
    signedInAs("approver");
    const api = mockApi({
      "GET /documents/doc-icu": documentDetail(),
      "POST /documents/doc-icu/versions/ver-4/approve": {
        ok: true,
        message: "Version approved",
        details: {},
      },
    });
    renderWithProviders(
      <Routes>
        <Route path="/library/:documentId" element={<DocumentDetailPage />} />
      </Routes>,
      "/library/doc-icu",
    );
    expect(
      await screen.findByRole("heading", { name: "Heparin Infusion Protocol (Adult ICU)" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Amended by C-2026-09 v1/)).toBeInTheDocument();
    expect(screen.getByText("Version 3")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve version 4?" });
    await userEvent.click(within(dialog).getByRole("button", { name: /Approve/ }));
    await waitFor(() =>
      expect(api.calls.some((c) => c.method === "POST" && c.path.endsWith("/approve"))).toBe(true),
    );
  });

  it("hides the approve button from authors", async () => {
    signedInAs("author");
    mockApi({ "GET /documents/doc-icu": documentDetail() });
    renderWithProviders(
      <Routes>
        <Route path="/library/:documentId" element={<DocumentDetailPage />} />
      </Routes>,
      "/library/doc-icu",
    );
    expect(await screen.findByText("Version 4")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });
});

describe("Review queues", () => {
  it("Amendments: splits links into needs-review and in-force", async () => {
    signedInAs("approver");
    mockApi({
      "GET /supersessions": [
        supersession(),
        supersession({ id: "link-2", confirmed: false, target_section_path: "3.1" }),
      ],
    });
    renderWithProviders(<SupersessionsPage />);
    expect(screen.getByRole("heading", { name: "Amendments" })).toBeInTheDocument();
    expect(await screen.findByText("Needs review (1)")).toBeInTheDocument();
    expect(screen.getByText("In force (1)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Confirm/ })).toBeInTheDocument();
  });

  it("Conflicts: shows both sides and resolves with a note", async () => {
    signedInAs("author");
    const api = mockApi({
      "GET /conflicts": [adminConflict()],
      "PATCH /conflicts/conflict-1": adminConflict({ status: "resolved" }),
    });
    renderWithProviders(<ConflictsPage />);
    expect(await screen.findByText("aPTT recheck: 6 h vs 4 h")).toBeInTheDocument();
    expect(screen.getByText("Check the aPTT 4 hours after any rate change.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Resolve/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "Note" }), "DG-02 will be amended");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "PATCH")).toBe(true));
  });

  it("Feedback: shows the report with its question and answer", async () => {
    signedInAs("author");
    mockApi({ "GET /feedback/inbox": [feedbackItem()] });
    renderWithProviders(<FeedbackPage />);
    expect(screen.getByRole("heading", { name: "Feedback" })).toBeInTheDocument();
    expect(await screen.findByText("Reported outdated")).toBeInTheDocument();
    expect(screen.getByText("A newer circular applies")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Acknowledge/ })).toBeInTheDocument();
  });

  it("Audit log: lists events and checks the hash chain", async () => {
    signedInAs("admin");
    mockApi({
      "GET /admin/audit": [auditEvent()],
      "GET /admin/audit/verify": { ok: true, events_checked: 42, first_bad_seq: null, reason: null },
    });
    renderWithProviders(<AuditPage />);
    expect(await screen.findByText("query.answered")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Check chain/ }));
    expect(await screen.findByText("Chain intact")).toBeInTheDocument();
  });
});

describe("App shell and routing", () => {
  it("clinicians get no navigation, only sign-out", () => {
    signedInAs("clinician");
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<p>content</p>} />
        </Route>
      </Routes>,
    );
    expect(screen.queryByRole("navigation", { name: "Main" })).not.toBeInTheDocument();
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("admins see one entry per section: Ask, Library, Review, Admin", async () => {
    signedInAs("admin");
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<p>content</p>} />
        </Route>
      </Routes>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Ask", "Library", "Review", "Admin"]);
    await userEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("authors see Library and Review but not Admin", () => {
    signedInAs("author");
    renderWithProviders(
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<p>content</p>} />
        </Route>
      </Routes>,
    );
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(
      within(nav)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Ask", "Library", "Review"]);
  });

  it("the Review section lists its queues with what is waiting in each", async () => {
    signedInAs("author");
    mockApi({
      "GET /supersessions": [supersession({ id: "link-2", confirmed: false })],
      "GET /conflicts": [adminConflict()],
      "GET /feedback/inbox": [feedbackItem(), feedbackItem({ id: "fb-2" })],
    });
    renderApp("/review");
    expect(await screen.findByRole("heading", { name: "Amendments" })).toBeInTheDocument();
    expect(window.location.pathname).toBe("/review/amendments");
    const queues = screen.getByRole("navigation", { name: "Review queues" });
    expect(await within(queues).findByLabelText("2 waiting")).toBeInTheDocument();
    expect(
      within(queues)
        .getAllByRole("link")
        .map((a) => a.textContent),
    ).toEqual(["Amendments1", "Conflicts1", "Feedback2"]);
  });

  it("the Admin section links Insights, Audit log and the API reference", async () => {
    signedInAs("admin");
    mockApi({ "GET /admin/stats": stats(), "GET /admin/overview": overview() });
    renderApp("/admin");
    const admin = await screen.findByRole("navigation", { name: "Administration" });
    expect(within(admin).getByRole("link", { name: "Insights" })).toHaveAttribute("aria-current", "page");
    expect(within(admin).getByRole("link", { name: "Audit log" })).toHaveAttribute("href", "/admin/audit");
    expect(within(admin).getByRole("link", { name: /API reference/ })).toHaveAttribute("target", "_blank");
  });

  it("a document opens at /library/:id and old /admin/documents/:id links still work", async () => {
    signedInAs("author");
    mockApi({ "GET /documents/doc-icu": documentDetail() });
    renderApp("/admin/documents/doc-icu");
    expect(
      await screen.findByRole("heading", { level: 1, name: "Heparin Infusion Protocol (Adult ICU)" }),
    ).toBeInTheDocument();
    expect(window.location.pathname).toBe("/library/doc-icu");
    expect(screen.getByRole("link", { name: "Library", current: false })).toBeInTheDocument();
  });

  it.each<[string, Role, string]>([
    ["/nope", "admin", "Page not found"],
    ["/admin", "author", "Not available for your role"],
    ["/admin/audit", "author", "Not available for your role"],
    ["/library", "clinician", "Not available for your role"],
    ["/review/conflicts", "clinician", "Not available for your role"],
  ])("%s as %s shows '%s'", async (path, role, heading) => {
    signedInAs(role);
    mockApi({ "GET /query/history": [] });
    renderApp(path);
    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });

  it.each<[string, string]>([
    ["/admin/dashboard", "/admin"],
    ["/admin/overview", "/admin"],
  ])("the old address %s opens the Admin page at %s", async (from, to) => {
    signedInAs("admin");
    mockApi({ "GET /admin/stats": stats(), "GET /admin/overview": overview() });
    renderApp(from);
    expect(await screen.findByRole("heading", { name: "Admin" })).toBeInTheDocument();
    expect(window.location.pathname).toBe(to);
  });

  it.each<[string, string, string]>([
    ["/admin/documents", "/library", "Documents"],
    ["/admin/supersessions", "/review/amendments", "Amendments"],
    ["/admin/conflicts", "/review/conflicts", "Conflicts"],
    ["/admin/feedback", "/review/feedback", "Feedback"],
  ])("the old address %s redirects to %s", async (from, to, heading) => {
    signedInAs("author");
    mockApi({
      "GET /documents": [documentSummary()],
      "GET /supersessions": [],
      "GET /conflicts": [],
      "GET /feedback/inbox": [],
    });
    renderApp(from);
    expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    expect(window.location.pathname).toBe(to);
  });
});
