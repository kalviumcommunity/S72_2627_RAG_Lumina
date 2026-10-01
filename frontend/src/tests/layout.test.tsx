/** The app frame and the pieces added with the design system, each rendered on its own. */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ErrorBoundary } from "../app/ErrorBoundary";
import { AnnouncementBar } from "../app/layout/AnnouncementBar";
import { Page, PageHeader, SectionTitle } from "../app/layout/Page";
import { NotFoundPage } from "../app/NotFoundPage";
import { legacyRedirects, paths } from "../app/paths";
import { MAIN_NAV, SECTION_NAV, visibleItems } from "../app/navigation";
import { MonoLabel, TaxonomyChip } from "../components/ui/Badge";
import { ButtonLink, buttonClass } from "../components/ui/Button";
import { Band } from "../components/ui/Card";
import { RuleList } from "../components/ui/Table";
import { DailyChart, DailyLegend } from "../features/admin/DailyChart";
import { BarList, CountList, Stat, StatBand } from "../features/admin/parts";
import { AmendmentList } from "../features/supersessions/AmendmentList";
import type { Session } from "../lib/auth";
import type { Role } from "../lib/types";
import { stats, supersession, user } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderWithProviders } from "./render";

let session: Session | null = null;
vi.mock("../app/providers", () => ({ useAuth: () => ({ session }) }));

function signedInAs(role: Role | null) {
  session = role ? { token: "t", expiresAt: Date.now() + 600_000, user: user(role) } : null;
}

describe("paths and navigation", () => {
  it("builds document addresses under the Library", () => {
    expect(paths.document("doc-1")).toBe("/library/doc-1");
  });

  it("maps every retired /admin/* address to its new home", () => {
    expect(Object.fromEntries(legacyRedirects.map((r) => [r.from, r.to]))).toEqual({
      "/admin/documents": "/library",
      "/admin/supersessions": "/review/amendments",
      "/admin/conflicts": "/review/conflicts",
      "/admin/feedback": "/review/feedback",
      "/admin/overview": "/admin",
      "/admin/dashboard": "/admin",
    });
  });

  it.each<[Role, string[]]>([
    ["clinician", ["Ask"]],
    ["author", ["Ask", "Library", "Review"]],
    ["approver", ["Ask", "Library", "Review"]],
    ["admin", ["Ask", "Library", "Review", "Admin"]],
  ])("a %s sees %j in the top navigation", (role, labels) => {
    expect(visibleItems(MAIN_NAV, user(role)).map((i) => i.label)).toEqual(labels);
  });

  it("section navigation is hidden from roles that cannot open it", () => {
    expect(visibleItems(SECTION_NAV.admin, user("approver"))).toEqual([]);
    expect(visibleItems(SECTION_NAV.review, user("clinician"))).toEqual([]);
  });
});

describe("page frame", () => {
  it("Page sets the browser tab title and PageHeader shows eyebrow, title and actions", () => {
    render(
      <Page title="Library">
        <PageHeader
          eyebrow="Library"
          title="Documents"
          description="Every protocol."
          actions={<button>Upload</button>}
        />
        <SectionTitle actions={<span>legend</span>}>Versions (2)</SectionTitle>
      </Page>,
    );
    expect(document.title).toBe("Library · Lumina");
    expect(screen.getByRole("heading", { level: 1, name: "Documents" })).toBeInTheDocument();
    expect(screen.getByText("Every protocol.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Upload" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Versions (2)" })).toBeInTheDocument();
    expect(screen.getByText("legend")).toBeInTheDocument();
  });

  describe("AnnouncementBar", () => {
    beforeEach(() => sessionStorage.clear());

    it("says the documents are synthetic and stays dismissed for the session", async () => {
      const { unmount } = render(<AnnouncementBar />);
      expect(screen.getByRole("region", { name: "Announcement" })).toHaveTextContent(
        /every document is synthetic/,
      );
      await userEvent.click(screen.getByRole("button", { name: "Dismiss announcement" }));
      expect(screen.queryByRole("region", { name: "Announcement" })).not.toBeInTheDocument();
      unmount();
      render(<AnnouncementBar />);
      expect(screen.queryByRole("region", { name: "Announcement" })).not.toBeInTheDocument();
    });
  });

  describe("ErrorBoundary", () => {
    // React logs the caught error; keep the test output clean.
    beforeEach(() => {
      vi.spyOn(console, "error").mockImplementation(() => undefined);
    });
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it("replaces a crashed page with a calm message and a reload button", () => {
      function Broken(): never {
        throw new Error("boom");
      }
      render(
        <ErrorBoundary>
          <Broken />
        </ErrorBoundary>,
      );
      expect(screen.getByRole("alert")).toHaveTextContent("This page could not be shown.");
      expect(screen.getByRole("button", { name: "Reload" })).toBeInTheDocument();
    });

    it("renders its children when nothing fails", () => {
      render(
        <ErrorBoundary>
          <p>fine</p>
        </ErrorBoundary>,
      );
      expect(screen.getByText("fine")).toBeInTheDocument();
    });
  });

  it("NotFoundPage offers a way back to Ask", () => {
    renderWithProviders(<NotFoundPage />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Ask" })).toHaveAttribute("href", "/");
  });
});

describe("design-system primitives", () => {
  it("ButtonLink is a link styled as a pill button", () => {
    renderWithProviders(
      <ButtonLink to="/library" variant="outline">
        Open library
      </ButtonLink>,
    );
    const link = screen.getByRole("link", { name: "Open library" });
    expect(link).toHaveAttribute("href", "/library");
    expect(link.className).toContain("rounded-pill");
  });

  it("buttonClass composes variant, size and extra classes", () => {
    expect(buttonClass("primary", "sm", "mt-4")).toMatch(/bg-primary.*mt-4/);
    expect(buttonClass("outline")).toContain("border");
  });

  it("MonoLabel, TaxonomyChip, Band and RuleList render their content", () => {
    render(
      <Band tone="green" aria-label="band">
        <MonoLabel>Version 3</MonoLabel>
        <TaxonomyChip active>Protocol</TaxonomyChip>
        <RuleList>
          <li>row</li>
        </RuleList>
      </Band>,
    );
    const band = screen.getByRole("region", { name: "band" });
    expect(band).toHaveClass("bg-green");
    expect(within(band).getByText("Version 3")).toHaveClass("mono-label");
    expect(within(band).getByText("Protocol")).toHaveClass("bg-coral");
    expect(within(band).getByRole("listitem")).toHaveTextContent("row");
  });
});

describe("AmendmentList", () => {
  it("approvers confirm or reject a suggested link", async () => {
    signedInAs("approver");
    const api = mockApi({
      "PATCH /supersessions/link-2": supersession({ id: "link-2", confirmed: true }),
      "DELETE /supersessions/link-3": { ok: true, message: "deleted" },
    });
    renderWithProviders(
      <AmendmentList
        links={[
          supersession({ id: "link-2", confirmed: false, evidence: "replaces section 4.2" }),
          supersession({ id: "link-3", confirmed: false }),
        ]}
      />,
    );
    expect(screen.getByText("“replaces section 4.2”")).toBeInTheDocument();
    expect(screen.getAllByText("Suggested — needs review")).toHaveLength(2);
    await userEvent.click(screen.getAllByRole("button", { name: /Confirm/ })[0]!);
    await userEvent.click(screen.getAllByRole("button", { name: /Reject/ })[1]!);
    await waitFor(() =>
      expect(api.calls.map((c) => `${c.method} ${c.path}`)).toEqual(
        expect.arrayContaining(["PATCH /supersessions/link-2", "DELETE /supersessions/link-3"]),
      ),
    );
  });

  it("authors see the links but cannot confirm them", () => {
    signedInAs("author");
    renderWithProviders(<AmendmentList links={[supersession({ confirmed: false })]} />);
    expect(screen.getByText("Suggested — needs review")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Confirm/ })).not.toBeInTheDocument();
  });

  it("confirmed links show as confirmed with what they hide", () => {
    signedInAs("approver");
    renderWithProviders(<AmendmentList links={[supersession()]} />);
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(screen.getByLabelText("amends")).toBeInTheDocument();
  });
});

describe("admin charts and figures", () => {
  it("StatBand holds labelled figures", () => {
    render(
      <StatBand label="Usage">
        <Stat label="Questions" value="1,284" sub="last 30 days" />
      </StatBand>,
    );
    const band = screen.getByRole("region", { name: "Usage" });
    expect(band).toHaveTextContent("Questions");
    expect(band).toHaveTextContent("1,284");
    expect(band).toHaveTextContent("last 30 days");
  });

  it("BarList shows each share, largest first, or a message when empty", () => {
    const { rerender } = render(<BarList counts={{ a: 1, b: 3 }} labels={{ a: "Alpha", b: "Beta" }} />);
    const rows = screen.getAllByRole("listitem");
    expect(rows[0]).toHaveTextContent("Beta3 · 75%");
    expect(rows[1]).toHaveTextContent("Alpha1 · 25%");
    rerender(<BarList counts={{ route: 40, total: 90 }} order={["route", "total"]} unit="ms" />);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("route40 ms");
    rerender(<BarList counts={{}} empty="No questions yet." />);
    expect(screen.getByText("No questions yet.")).toBeInTheDocument();
  });

  it("CountList ranks items or says it is empty", () => {
    const { rerender } = render(<CountList items={[{ label: "P-ICU-07", count: 4 }]} empty="none" mono />);
    expect(screen.getByRole("listitem")).toHaveTextContent("P-ICU-074");
    rerender(<CountList items={[]} empty="No citations yet." />);
    expect(screen.getByText("No citations yet.")).toBeInTheDocument();
  });

  it("DailyChart draws the window, reads each day by keyboard and has a table view", async () => {
    render(
      <>
        <DailyLegend />
        <DailyChart stats={stats()} />
      </>,
    );
    expect(screen.getAllByText("Answered or clarified")[0]!.closest("p")).toHaveTextContent("Declined");
    const chart = screen.getByRole("img", { name: /12 questions over 30 days; busiest day had 12/ });

    chart.focus();
    const tooltip = await screen.findByRole("status");
    expect(tooltip).toHaveTextContent("9answered or clarified");
    expect(tooltip).toHaveTextContent("3declined");
    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.getByRole("status")).toHaveTextContent("0answered or clarified");

    await userEvent.click(screen.getByText("Show as table"));
    const table = screen.getByRole("table", { name: "Questions per day" });
    expect(within(table).getAllByRole("row")).toHaveLength(2); // header + the one day with questions
  });

  it("DailyChart says so when there were no questions", () => {
    render(<DailyChart stats={stats({ daily: [] })} />);
    expect(screen.getByText("No questions in this period.")).toBeInTheDocument();
  });
});
