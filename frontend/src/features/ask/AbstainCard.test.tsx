import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { contact } from "../../tests/fixtures";
import { AbstainCard } from "./AbstainCard";

describe("AbstainCard", () => {
  it("explains a not-found abstention without escalation clutter when no contacts apply", () => {
    render(
      <AbstainCard
        escalation={{ reason: "not_found", message: "Not covered.", clarifying_question: null, contacts: [] }}
      />,
    );
    expect(screen.getByText("No approved document covers this")).toBeInTheDocument();
    expect(screen.queryByText("Escalate to")).not.toBeInTheDocument();
  });

  it("offers to add the missing detail for a clarify route", async () => {
    const onRefine = vi.fn();
    render(
      <AbstainCard
        escalation={{
          reason: "clarify",
          message: "Need more.",
          clarifying_question: "Adult or paediatric?",
          contacts: [],
        }}
        onRefine={onRefine}
      />,
    );
    expect(screen.getByText("Adult or paediatric?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add the detail" }));
    expect(onRefine).toHaveBeenCalledOnce();
  });

  it("dials the extension when there is no direct number, and hides the button when neither exists", () => {
    render(
      <AbstainCard
        escalation={{
          reason: "high_risk",
          message: "m",
          clarifying_question: null,
          contacts: [
            contact({ id: "1", role_label: "Pharmacy", phone: null, phone_ext: "3310" }),
            contact({ id: "2", role_label: "Rapid response", phone: null, phone_ext: null, pager: "99" }),
          ],
        }}
      />,
    );
    expect(screen.getByRole("link", { name: "Call Pharmacy" })).toHaveAttribute("href", "tel:3310");
    expect(screen.queryByRole("link", { name: "Call Rapid response" })).not.toBeInTheDocument();
    expect(screen.getByText("Pager 99")).toBeInTheDocument();
  });
});
