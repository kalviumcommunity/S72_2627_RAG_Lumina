/** Every shared UI and feature component, rendered on its own. */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { Footer } from "../app/layout/Footer";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { EmptyState, ErrorNotice } from "../components/ui/EmptyState";
import { Field, Input, Select, Textarea } from "../components/ui/Field";
import { Segmented } from "../components/ui/Segmented";
import { Sheet } from "../components/ui/Sheet";
import { Skeleton } from "../components/ui/Skeleton";
import { Spinner } from "../components/ui/Spinner";
import { Table, Td, Th, Tr } from "../components/ui/Table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/Tabs";
import { useToast } from "../components/ui/Toast";
import { Tooltip } from "../components/ui/Tooltip";
import { CitationChip } from "../features/ask/CitationChip";
import { ConflictBanner } from "../features/ask/ConflictBanner";
import { FeedbackButtons } from "../features/ask/FeedbackDialog";
import { QuestionInput } from "../features/ask/QuestionInput";
import { QuickCard } from "../features/ask/QuickCard";
import { StreamProgress } from "../features/ask/StreamProgress";
import { StatusBadge } from "../features/documents/shared";
import { UploadDialog } from "../features/documents/UploadDialog";
import { RecentQuestions } from "../features/history/RecentQuestions";
import { PdfViewer } from "../features/sources/PdfViewer";
import { SourceSheet } from "../features/sources/SourceSheet";
import { VersionBadge } from "../features/sources/VersionBadge";
import { INTENDED_USE } from "../lib/constants";
import { citation, feedbackItem, historyItem, referenceData, source } from "./fixtures";
import { mockApi } from "./mockApi";
import { renderWithProviders } from "./render";

// jsdom cannot render PDFs: stand in for react-pdf with a two-page document.
vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: {} },
  Document: ({
    children,
    onLoadSuccess,
  }: {
    children: ReactNode;
    onLoadSuccess: (d: { numPages: number }) => void;
  }) => {
    setTimeout(() => onLoadSuccess({ numPages: 2 }), 0);
    return <div data-testid="pdf-document">{children}</div>;
  },
  Page: ({ pageNumber }: { pageNumber: number }) => <div data-testid="pdf-page">page {pageNumber}</div>,
}));

describe("basic UI components", () => {
  it("Badge, Card, Skeleton and Spinner render", () => {
    render(
      <Card>
        <Badge tone="success">Approved</Badge>
        <Badge tone="amber">Suggested</Badge>
        <Skeleton className="h-4" />
        <Spinner label="Loading" />
      </Card>,
    );
    expect(screen.getByText("Approved")).toBeInTheDocument();
    expect(screen.getByText("Suggested")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Loading" })).toBeInTheDocument();
  });

  it("Button is disabled and busy while loading", async () => {
    const onClick = vi.fn();
    const { rerender } = render(<Button onClick={onClick}>Save</Button>);
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onClick).toHaveBeenCalledOnce();
    rerender(
      <Button loading onClick={onClick}>
        Save
      </Button>,
    );
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute("aria-busy", "true");
  });

  it("EmptyState and ErrorNotice show their message", () => {
    render(
      <>
        <EmptyState title="Nothing here">Try again later</EmptyState>
        <ErrorNotice title="Failed" message="Server down" />
      </>,
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Server down");
  });

  it("Field wires its label, hint and error to the control", () => {
    render(
      <>
        <Field label="Title" hint="Short name">
          {(props) => <Input {...props} />}
        </Field>
        <Field label="Type" error="Required">
          {(props) => (
            <Select {...props}>
              <option>Protocol</option>
            </Select>
          )}
        </Field>
        <Field label="Notes">{(props) => <Textarea {...props} />}</Field>
      </>,
    );
    expect(screen.getByLabelText("Title")).toHaveAccessibleDescription("Short name");
    expect(screen.getByLabelText("Type")).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByLabelText("Notes")).toBeInTheDocument();
  });

  it("Segmented marks the selected option and reports changes", async () => {
    function Demo() {
      const [value, setValue] = useState("open");
      return (
        <Segmented
          label="Show"
          value={value}
          onChange={setValue}
          options={[
            ["open", "Open"],
            ["all", "All"],
          ]}
        />
      );
    }
    render(<Demo />);
    expect(screen.getByRole("button", { name: "Open" })).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(screen.getByRole("button", { name: "All" }));
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
  });

  it("Dialog and Sheet show their title and close", async () => {
    const onChange = vi.fn();
    render(
      <>
        <Dialog open onOpenChange={onChange} title="Confirm">
          <p>Dialog body</p>
        </Dialog>
      </>,
    );
    expect(screen.getByRole("dialog", { name: "Confirm" })).toHaveTextContent("Dialog body");
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onChange).toHaveBeenCalledWith(false);
  });

  it("Sheet renders its body and footer", () => {
    render(
      <Sheet open onOpenChange={() => undefined} title="Source" footer={<p>footer</p>}>
        <p>Sheet body</p>
      </Sheet>,
    );
    expect(screen.getByRole("dialog", { name: "Source" })).toHaveTextContent("Sheet body");
    expect(screen.getByText("footer")).toBeInTheDocument();
  });

  it("Tabs switch panels", async () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">First</TabsTrigger>
          <TabsTrigger value="b">Second</TabsTrigger>
        </TabsList>
        <TabsContent value="a">Panel A</TabsContent>
        <TabsContent value="b">Panel B</TabsContent>
      </Tabs>,
    );
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel A");
    await userEvent.click(screen.getByRole("tab", { name: "Second" }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent("Panel B");
  });

  it("Table renders headers and cells", () => {
    render(
      <Table label="People">
        <thead>
          <tr>
            <Th>Name</Th>
          </tr>
        </thead>
        <tbody>
          <Tr>
            <Td>Kavya</Td>
          </Tr>
        </tbody>
      </Table>,
    );
    expect(screen.getByRole("table", { name: "People" })).toHaveTextContent("Kavya");
  });

  it("Toast shows a notification", async () => {
    function Notifier() {
      const { notify } = useToast();
      return <button onClick={() => notify("Saved", { description: "All good" })}>notify</button>;
    }
    renderWithProviders(<Notifier />);
    await userEvent.click(screen.getByRole("button", { name: "notify" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("Tooltip wraps its trigger", () => {
    renderWithProviders(
      <Tooltip content="More info">
        <button>trigger</button>
      </Tooltip>,
    );
    expect(screen.getByRole("button", { name: "trigger" })).toBeInTheDocument();
  });

  it.each(["light", "dark"] as const)("Footer (%s) states the intended use", (tone) => {
    render(<Footer tone={tone} />);
    expect(screen.getByRole("contentinfo", { name: "Intended use" })).toHaveTextContent(INTENDED_USE);
  });
});

describe("Ask components", () => {
  it("StreamProgress shows the current step only while working", () => {
    const { rerender } = render(<StreamProgress stage="retrieving" />);
    expect(screen.getByText("Finding approved sources")).toBeInTheDocument();
    expect(screen.getByText("step 2 of 3")).toBeInTheDocument();
    rerender(<StreamProgress stage="done" />);
    expect(screen.queryByText(/step/)).not.toBeInTheDocument();
  });

  it("QuestionInput submits on Enter and offers Stop while busy", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();
    function Demo({ busy }: { busy: boolean }) {
      const [value, setValue] = useState("");
      return (
        <QuestionInput
          value={value}
          onChange={setValue}
          onSubmit={onSubmit}
          onCancel={onCancel}
          busy={busy}
        />
      );
    }
    const { rerender } = render(<Demo busy={false} />);
    expect(screen.getByRole("button", { name: "Ask" })).toBeDisabled();
    await userEvent.type(screen.getByRole("textbox"), "hello{Enter}");
    expect(onSubmit).toHaveBeenCalledOnce();
    rerender(<Demo busy />);
    await userEvent.click(screen.getByRole("button", { name: "Stop" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("CitationChip opens its clause; unknown markers stay plain text", async () => {
    const onOpen = vi.fn();
    renderWithProviders(
      <p>
        <CitationChip marker="S1" citation={citation()} onOpen={onOpen} />
        <CitationChip marker="S9" citation={undefined} onOpen={onOpen} />
      </p>,
    );
    await userEvent.click(screen.getByRole("button", { name: /Open source S1: C-2026-09 §2/ }));
    expect(onOpen).toHaveBeenCalledWith("chunk-1");
    expect(screen.getByText("[S9]")).toBeInTheDocument();
  });

  it("QuickCard opens the clause a value was copied from", async () => {
    const onOpen = vi.fn();
    render(
      <QuickCard
        values={[{ label: "Hold", value: "1 hour", source: "S1" }]}
        citations={[citation()]}
        onOpen={onOpen}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: /1 hour/ }));
    expect(onOpen).toHaveBeenCalledWith("chunk-1");
  });

  it("ConflictBanner renders nothing without conflicts", () => {
    const { container } = render(<ConflictBanner conflicts={[]} onOpen={() => undefined} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("FeedbackButtons send 'helpful' and 'report a problem'", async () => {
    const api = mockApi({ "POST /feedback": feedbackItem({ kind: "helpful" }) });
    renderWithProviders(<FeedbackButtons queryId="q-1" />);
    await userEvent.click(screen.getByRole("button", { name: "Helpful" }));
    await waitFor(() => expect(api.calls).toHaveLength(1));
    expect(screen.getByRole("button", { name: "Helpful" })).toBeDisabled();
  });

  it("FeedbackButtons: a report goes out with its kind and comment", async () => {
    let sent: unknown;
    mockApi({
      "POST /feedback": (_: URL, init?: RequestInit) => {
        sent = JSON.parse(init?.body as string);
        return feedbackItem();
      },
    });
    renderWithProviders(<FeedbackButtons queryId="q-1" />);
    await userEvent.click(screen.getByRole("button", { name: /Report a problem/ }));
    await userEvent.click(screen.getByRole("radio", { name: /Outdated/ }));
    await userEvent.type(screen.getByRole("textbox", { name: "Comment (optional)" }), "see C-2026-09");
    await userEvent.click(screen.getByRole("button", { name: "Send report" }));
    await waitFor(() =>
      expect(sent).toEqual({ query_id: "q-1", kind: "outdated", comment: "see C-2026-09" }),
    );
  });

  it("RecentQuestions lists the user's history and re-asks on click", async () => {
    mockApi({ "GET /query/history": [historyItem()] });
    const onPick = vi.fn();
    renderWithProviders(<RecentQuestions onPick={onPick} />);
    await userEvent.click(await screen.findByRole("button", { name: /Does Tazocin need AMS approval/ }));
    expect(onPick).toHaveBeenCalledWith("Does Tazocin need AMS approval?");
  });
});

describe("Source and document components", () => {
  it("VersionBadge and StatusBadge label versions", () => {
    render(
      <>
        <VersionBadge version="3" effectiveFrom="2025-11-01" status="superseded" current={false} />
        <StatusBadge status="draft" />
      </>,
    );
    expect(screen.getByText(/v3 · effective 1 Nov 2025/)).toBeInTheDocument();
    expect(screen.getByText("superseded")).toBeInTheDocument();
    expect(screen.getByText("Draft")).toBeInTheDocument();
  });

  it("SourceSheet opens the document with the cited clause highlighted", async () => {
    mockApi({ "GET /sources/chunk-1": source() });
    renderWithProviders(<SourceSheet chunkId="chunk-1" onClose={() => undefined} />);
    const sheet = await screen.findByRole("dialog");
    await waitFor(() => expect(sheet).toHaveTextContent("Heparin Nomogram Amendment"));
    const cited = sheet.querySelector('section[aria-current="true"]');
    expect(cited).toHaveTextContent("Cited clause");
    expect(cited).toHaveTextContent("hold the infusion for 1 hour");
    expect(sheet).toHaveTextContent("This document amends P-ICU-07 §4.2");
  });

  it("PdfViewer loads the file with the session and pages through it", async () => {
    mockApi({ "GET /sources/ver-1/file": new Response("%PDF-1.4", { status: 200 }) });
    renderWithProviders(
      <PdfViewer fileUrl="/api/v1/sources/ver-1/file" initialPage={1} boxes={[]} clauseText="x" />,
    );
    expect(await screen.findByText("Page 1 of 2")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    });
    expect(screen.getByTestId("pdf-page")).toHaveTextContent("page 2");
  });

  it("UploadDialog asks for a file before uploading", async () => {
    mockApi({ "GET /admin/reference-data": referenceData() });
    renderWithProviders(<UploadDialog open onOpenChange={() => undefined} />);
    expect(screen.getByRole("dialog", { name: "Upload a document" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Upload as draft/ }));
    expect(screen.getByText("Choose a file to upload")).toBeInTheDocument();
  });
});
