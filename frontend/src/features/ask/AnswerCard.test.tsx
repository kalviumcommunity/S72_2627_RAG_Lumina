import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { abstained, answered, citation } from "../../tests/fixtures";
import { renderWithProviders } from "../../tests/render";
import { AnswerCard } from "./AnswerCard";

describe("AnswerCard", () => {
  it("renders the verified answer with clickable citation chips", async () => {
    const onOpen = vi.fn();
    renderWithProviders(<AnswerCard response={answered()} onOpenSource={onOpen} />);

    expect(screen.getByText("Verified against sources")).toBeInTheDocument();
    expect(screen.getByText(/2 of 2 statements checked/)).toBeInTheDocument();
    const text = screen.getByTestId("answer-text");
    expect(text).toHaveTextContent("Hold the heparin infusion for 1 hour.");
    expect(text).not.toHaveTextContent("[S1]"); // markers become chips, not raw text

    const chips = within(text).getAllByRole("button", { name: /Open source S1: C-2026-09 §2/ });
    expect(chips).toHaveLength(2);
    await userEvent.click(chips[0]!);
    expect(onOpen).toHaveBeenCalledWith("chunk-1");
  });

  it("shows the key value and the amended clause in the source list", () => {
    renderWithProviders(<AnswerCard response={answered()} onOpenSource={() => undefined} />);
    expect(screen.getByRole("region", { name: "Key values" })).toHaveTextContent("1 hour");
    expect(screen.getByRole("region", { name: "Sources cited" })).toHaveTextContent("Amends P-ICU-07 §4.2");
  });

  it("marks partially verified answers and removed statements", () => {
    renderWithProviders(
      <AnswerCard
        response={answered({ outcome: "partial", verification: { claims: 3, supported: 2, judge: "llm" } })}
        onOpenSource={() => undefined}
      />,
    );
    expect(screen.getByText("Partly verified")).toBeInTheDocument();
    expect(screen.getByText(/1 unsupported removed/)).toBeInTheDocument();
  });

  it("never renders answer text for a high-risk refusal and offers escalation contacts", () => {
    renderWithProviders(
      <AnswerCard
        response={abstained("high_risk", {
          pii_redacted: true,
          redacted_question: "Heparin bolus for <PERSON>?",
        })}
        onOpenSource={() => undefined}
      />,
    );
    expect(screen.queryByTestId("answer-text")).not.toBeInTheDocument();
    expect(screen.getByText("No answer given")).toBeInTheDocument();
    expect(screen.getByText(/needs a clinical decision/)).toBeInTheDocument();
    expect(screen.getByText(/Patient identifiers were removed/)).toHaveTextContent("<PERSON>");
    expect(screen.getByRole("link", { name: "Call ICU consultant on call" })).toHaveAttribute(
      "href",
      "tel:+918040002201",
    );
  });

  it("shows both sides of a conflict and opens either source", async () => {
    const onOpen = vi.fn();
    const side = (id: string, code: string, snippet: string) => ({
      chunk_id: id,
      doc_code: code,
      title: code,
      version: "1",
      section_path: "5.1",
      effective_from: "2026-01-01",
      snippet,
      marker: null,
    });
    renderWithProviders(
      <AnswerCard
        response={answered({
          citations: [citation()],
          conflicts: [
            {
              id: "c1",
              description: "Repeat aPTT timing differs",
              detected_by: "query",
              status: "open",
              flagged_to_owner: true,
              newer: "b",
              a: side("a-chunk", "P-ICU-07", "Repeat aPTT 6 hours after any change."),
              b: side("b-chunk", "DG-02", "Repeat aPTT 4 hours after any change."),
            },
          ],
        })}
        onOpenSource={onOpen}
      />,
    );
    const banner = screen.getByRole("alert", { name: "Conflicting sources" });
    expect(banner).toHaveTextContent("6 hours");
    expect(banner).toHaveTextContent("4 hours");
    expect(within(banner).getByText("More recent")).toBeInTheDocument();
    await userEvent.click(within(banner).getByRole("button", { name: /DG-02/ }));
    expect(onOpen).toHaveBeenCalledWith("b-chunk");
  });
});
