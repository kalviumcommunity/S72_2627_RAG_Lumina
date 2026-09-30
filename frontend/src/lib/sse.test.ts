import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import { parseSseChunk, streamQuery } from "./sse";
import type { StreamEvent } from "./types";

describe("parseSseChunk", () => {
  it("parses complete events and keeps the incomplete tail", () => {
    const buffer =
      'event: route\ndata: {"route":"answer"}\n\n' +
      'event: done\ndata: {"query_id":"q1"}\n\n' +
      "event: answ";
    const { events, rest } = parseSseChunk(buffer);
    expect(events).toEqual([
      { event: "route", data: { route: "answer" } },
      { event: "done", data: { query_id: "q1" } },
    ]);
    expect(rest).toBe("event: answ");
  });

  it("normalises CRLF, skips keep-alive comments and malformed JSON", () => {
    const buffer = ": ping\r\n\r\nevent: sources\r\ndata: {not json}\r\n\r\nevent: done\r\ndata: {}\r\n\r\n";
    const { events, rest } = parseSseChunk(buffer);
    expect(events).toEqual([{ event: "done", data: {} }]);
    expect(rest).toBe("");
  });

  it("joins multi-line data fields", () => {
    const { events } = parseSseChunk('event: error\ndata: {"code":"x",\ndata: "message":"m"}\n\n');
    expect(events).toEqual([{ event: "error", data: { code: "x", message: "m" } }]);
  });
});

function streamResponse(chunks: string[], init: ResponseInit = { status: 200 }): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((c) => controller.enqueue(encoder.encode(c)));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" }, ...init });
}

describe("streamQuery", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs the question in the body (never the URL) and emits events across chunk boundaries", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        streamResponse([
          'event: route\ndata: {"rou',
          'te":"answer"}\n\nevent: done\n',
          'data: {"query_id":"q1"}\n\n',
        ]),
      );
    vi.stubGlobal("fetch", fetchMock);
    const events: StreamEvent[] = [];
    await streamQuery("heparin for Mr X?", (e) => events.push(e), undefined, "branch-1");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/v1/query/stream");
    expect(url).not.toContain("heparin");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ question: "heparin for Mr X?", branch_id: "branch-1" });
    expect(events.map((e) => e.event)).toEqual(["route", "done"]);
  });

  it("turns an error response into an ApiError with the server's message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ error: { code: "rate_limited", message: "Slow down" } }), {
          status: 429,
        }),
      ),
    );
    await expect(streamQuery("q", () => undefined)).rejects.toMatchObject({
      status: 429,
      code: "rate_limited",
      message: "Slow down",
    });
  });

  it("reports a network failure clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(streamQuery("q", () => undefined)).rejects.toBeInstanceOf(ApiError);
  });
});
