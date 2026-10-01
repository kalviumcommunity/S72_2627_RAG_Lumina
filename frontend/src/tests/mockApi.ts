/**
 * Stub `fetch` for component and page tests: each API path returns a fixture.
 *
 * Keys are "METHOD /path" (path after /api/v1, no query string); a trailing "*" matches any suffix.
 * Values are the JSON body, or a function of the request that returns one. Unmatched requests get a
 * 404 and are recorded in `unmatched`, so a test can assert the page only called what it should.
 */
import { vi } from "vitest";

/** A JSON body, a Response, or a function of the request returning either. */
type Handler = unknown;

export interface ApiMock {
  calls: { method: string; path: string; search: string }[];
  unmatched: string[];
}

export function mockApi(routes: Record<string, Handler>): ApiMock {
  const state: ApiMock = { calls: [], unmatched: [] };
  vi.spyOn(globalThis, "fetch").mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    const path = url.pathname.replace(/^\/api\/v1/, "");
    state.calls.push({ method, path, search: url.search });
    const key = `${method} ${path}`;
    const match = Object.keys(routes).find((k) =>
      k.endsWith("*") ? key.startsWith(k.slice(0, -1)) : k === key,
    );
    if (match === undefined) {
      state.unmatched.push(key);
      return Promise.resolve(
        new Response(JSON.stringify({ error: { code: "not_found", message: `no mock for ${key}` } }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        }),
      );
    }
    const handler = routes[match];
    const body: unknown =
      typeof handler === "function" ? (handler as (u: URL, i?: RequestInit) => unknown)(url, init) : handler;
    if (body instanceof Response) return Promise.resolve(body);
    return Promise.resolve(
      new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
  });
  return state;
}
