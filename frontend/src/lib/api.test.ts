import { afterEach, describe, expect, it, vi } from "vitest";

import { user } from "../tests/fixtures";
import { api, ApiError } from "./api";
import { auth } from "./auth";

afterEach(() => {
  vi.unstubAllGlobals();
  auth.clear();
});

describe("api client", () => {
  it("sends the bearer token and drops empty query parameters", async () => {
    auth.set({ access_token: "tok", token_type: "bearer", expires_in: 900, user: user("admin") });
    const fetchMock = vi.fn().mockResolvedValue(new Response("[]", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await api.get("/admin/audit", { from: "", action: "query", limit: 50, to: undefined });
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/admin/audit?action=query&limit=50");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("maps the error envelope to ApiError", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "forbidden", message: "Approver role required" } }), {
          status: 403,
        }),
      ),
    );
    const err: unknown = await api.post("/documents/x/versions/y/approve").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 403, code: "forbidden", message: "Approver role required" });
  });

  it("signs the user out when the server says the token expired", async () => {
    auth.set({ access_token: "tok", token_type: "bearer", expires_in: 900, user: user("clinician") });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));
    await expect(api.get("/auth/me")).rejects.toBeInstanceOf(ApiError);
    expect(auth.token()).toBeNull();
  });
});
