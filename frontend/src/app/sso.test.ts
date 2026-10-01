import { describe, expect, it } from "vitest";

import { mockApi } from "../tests/mockApi";
import { user } from "../tests/fixtures";
import { completeSsoSignIn } from "./providers";

describe("hospital SSO sign-in", () => {
  it("exchanges the token from the redirect for a session and removes it from the address bar", async () => {
    let authorization: string | null = null;
    mockApi({
      "POST /auth/refresh": (_: URL, init?: RequestInit) => {
        authorization = new Headers(init?.headers).get("Authorization");
        return { access_token: "fresh", token_type: "bearer", expires_in: 900, user: user("clinician") };
      },
    });
    window.history.pushState({}, "", "/auth/callback#token=abc.def");
    const session = await completeSsoSignIn();
    expect(session?.access_token).toBe("fresh");
    expect(authorization).toBe("Bearer abc.def");
    expect(window.location.hash).toBe("");
  });

  it("does nothing on a normal page load", async () => {
    const api = mockApi({});
    window.history.pushState({}, "", "/");
    expect(await completeSsoSignIn()).toBeNull();
    expect(api.calls).toEqual([]);
  });

  it("returns no session when the token is rejected", async () => {
    mockApi({});
    window.history.pushState({}, "", "/auth/callback#token=expired");
    expect(await completeSsoSignIn()).toBeNull();
  });
});
