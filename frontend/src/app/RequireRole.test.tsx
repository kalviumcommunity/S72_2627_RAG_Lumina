import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import type { Session } from "../lib/auth";
import type { Role } from "../lib/types";
import { user } from "../tests/fixtures";
import { RequireRole } from "./RequireRole";

let session: Session | null = null;
vi.mock("./providers", () => ({ useAuth: () => ({ session }) }));
vi.mock("./layout/AppShell", () => ({ AdminPage: ({ children }: { children: ReactNode }) => children }));

function renderAt(role: Role | null, required: Role) {
  session = role ? { token: "t", expiresAt: Date.now() + 60_000, user: user(role) } : null;
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/admin" element={<RequireRole role={required} />}>
          <Route index element={<p>secret admin page</p>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("RequireRole", () => {
  it.each<[Role, Role]>([
    ["author", "author"],
    ["approver", "author"],
    ["admin", "admin"],
  ])("lets a %s into a page that needs %s", (role, required) => {
    renderAt(role, required);
    expect(screen.getByText("secret admin page")).toBeInTheDocument();
  });

  it.each<[Role, Role]>([
    ["clinician", "author"],
    ["approver", "admin"],
  ])("keeps a %s out of a page that needs %s", (role, required) => {
    renderAt(role, required);
    expect(screen.queryByText("secret admin page")).not.toBeInTheDocument();
    expect(screen.getByText("Not available for your role")).toBeInTheDocument();
  });
});
