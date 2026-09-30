import { describe, expect, it, vi } from "vitest";

import { user } from "../tests/fixtures";
import { auth, hasRole } from "./auth";

describe("auth", () => {
  it("ranks roles clinician < author < approver < admin", () => {
    expect(hasRole(user("clinician"), "author")).toBe(false);
    expect(hasRole(user("author"), "author")).toBe(true);
    expect(hasRole(user("approver"), "author")).toBe(true);
    expect(hasRole(user("approver"), "admin")).toBe(false);
    expect(hasRole(user("admin"), "approver")).toBe(true);
    expect(hasRole(null, "clinician")).toBe(false);
  });

  it("keeps the session in sessionStorage and notifies listeners on sign-out", () => {
    const listener = vi.fn();
    const unsubscribe = auth.subscribe(listener);
    auth.set({ access_token: "tok", token_type: "bearer", expires_in: 900, user: user("clinician") });
    expect(auth.token()).toBe("tok");
    expect(sessionStorage.getItem("protocite.session")).toContain("tok");

    auth.clear("signed_out");
    expect(auth.token()).toBeNull();
    expect(sessionStorage.getItem("protocite.session")).toBeNull();
    expect(listener).toHaveBeenLastCalledWith(null, "signed_out");
    unsubscribe();
  });

  it("expires the session once its lifetime has passed", () => {
    vi.useFakeTimers();
    try {
      auth.set({ access_token: "tok", token_type: "bearer", expires_in: 60, user: user("clinician") });
      vi.advanceTimersByTime(61_000);
      expect(auth.get()).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
