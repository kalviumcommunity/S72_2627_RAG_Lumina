import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../../lib/api";
import { streamQuery } from "../../lib/sse";
import type { StreamEvent } from "../../lib/types";
import { answered } from "../../tests/fixtures";
import { useAskStream } from "./useAskStream";

vi.mock("../../lib/sse", () => ({ streamQuery: vi.fn() }));
const mockStream = vi.mocked(streamQuery);

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>;
}

describe("useAskStream", () => {
  beforeEach(() => {
    mockStream.mockReset();
  });

  it("moves through routing → verifying → done and only sets the answer from the answer event", async () => {
    const stages: string[] = [];
    let emit: (e: StreamEvent) => void = () => undefined;
    let finish: () => void = () => undefined;
    mockStream.mockImplementation((_q, onEvent) => {
      emit = onEvent;
      return new Promise<void>((resolve) => {
        finish = resolve;
      });
    });
    const { result } = renderHook(() => useAskStream("branch-1"), { wrapper });

    act(() => {
      void result.current.ask("  heparin step?  ");
    });
    await waitFor(() => expect(result.current.exchanges).toHaveLength(1));
    expect(result.current.exchanges[0]).toMatchObject({ question: "heparin step?", stage: "routing" });
    expect(result.current.busy).toBe(true);
    expect(mockStream).toHaveBeenCalledWith(
      "heparin step?",
      expect.any(Function),
      expect.any(AbortSignal),
      "branch-1",
    );

    act(() => {
      emit({
        event: "route",
        data: { route: "answer", reason: "", redacted_question: "q", pii_redacted: false },
      });
    });
    stages.push(result.current.exchanges[0]!.stage);
    act(() => {
      emit({ event: "sources", data: { sources: [], timings_ms: {} } });
    });
    stages.push(result.current.exchanges[0]!.stage);
    expect(result.current.exchanges[0]!.response).toBeNull();
    act(() => {
      emit({ event: "answer", data: answered() });
    });
    stages.push(result.current.exchanges[0]!.stage);
    await act(async () => {
      finish();
      await Promise.resolve();
    });

    expect(stages).toEqual(["retrieving", "verifying", "done"]);
    expect(result.current.exchanges[0]!.response?.query_id).toBe("q-1");
    expect(result.current.busy).toBe(false);
  });

  it("goes straight to the answer stage for a refusal (no retrieval)", () => {
    let emit: (e: StreamEvent) => void = () => undefined;
    mockStream.mockImplementation((_q, onEvent) => {
      emit = onEvent;
      return new Promise<void>(() => undefined);
    });
    const { result } = renderHook(() => useAskStream(null), { wrapper });
    act(() => {
      void result.current.ask("dose for this patient?");
    });
    act(() => {
      emit({
        event: "route",
        data: { route: "high_risk", reason: "", redacted_question: "q", pii_redacted: true },
      });
    });
    expect(result.current.exchanges[0]!.stage).toBe("verifying");
  });

  it("ignores empty questions", () => {
    const { result } = renderHook(() => useAskStream(null), { wrapper });
    act(() => {
      void result.current.ask("   ");
    });
    expect(mockStream).not.toHaveBeenCalled();
    expect(result.current.exchanges).toHaveLength(0);
  });

  it("shows a friendly message when rate limited", async () => {
    mockStream.mockRejectedValue(new ApiError(429, "rate_limited", "Too many"));
    const { result } = renderHook(() => useAskStream(null), { wrapper });
    await act(async () => {
      await result.current.ask("q");
    });
    expect(result.current.exchanges[0]).toMatchObject({ stage: "error" });
    expect(result.current.exchanges[0]!.error).toMatch(/wait a moment/);
  });

  it("marks the exchange cancelled when the user stops it", async () => {
    mockStream.mockImplementation(
      (_q, _on, signal) =>
        new Promise<void>((_resolve, reject) => {
          signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );
    const { result } = renderHook(() => useAskStream(null), { wrapper });
    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = result.current.ask("q");
    });
    await waitFor(() => expect(result.current.busy).toBe(true));
    await act(async () => {
      result.current.cancel();
      await pending;
    });
    expect(result.current.exchanges[0]!.stage).toBe("cancelled");
  });
});
