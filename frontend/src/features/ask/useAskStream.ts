/**
 * Streaming question state for the Ask page.
 *
 * Each question is an "exchange" that moves through stages as server events arrive:
 * routing → retrieving (route = answer) → verifying (sources shown) → done. The answer is only
 * ever set from the `answer` event, which the server emits after verification.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import { ApiError } from "../../lib/api";
import { streamQuery } from "../../lib/sse";
import type { QueryResponse, RouteEvent, SourceCard } from "../../lib/types";

export type Stage = "routing" | "retrieving" | "verifying" | "done" | "error" | "cancelled";

export interface Exchange {
  id: string;
  question: string;
  stage: Stage;
  route: RouteEvent | null;
  sources: SourceCard[];
  response: QueryResponse | null;
  error: string | null;
  startedAt: number;
}

const MAX_EXCHANGES = 12;

export function useAskStream(branchId: string | null) {
  const queryClient = useQueryClient();
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const controller = useRef<AbortController | null>(null);

  const update = useCallback((id: string, patch: Partial<Exchange>) => {
    setExchanges((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }, []);

  const busy = exchanges.some((e) => ["routing", "retrieving", "verifying"].includes(e.stage));

  const ask = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || busy) return;
      const id = crypto.randomUUID();
      const exchange: Exchange = {
        id,
        question: trimmed,
        stage: "routing",
        route: null,
        sources: [],
        response: null,
        error: null,
        startedAt: Date.now(),
      };
      setExchanges((prev) => [...prev.slice(-(MAX_EXCHANGES - 1)), exchange]);
      const abort = new AbortController();
      controller.current = abort;
      try {
        await streamQuery(
          trimmed,
          (event) => {
            switch (event.event) {
              case "route":
                update(id, {
                  route: event.data,
                  stage: event.data.route === "answer" ? "retrieving" : "verifying",
                });
                break;
              case "sources":
                update(id, { sources: event.data.sources, stage: "verifying" });
                break;
              case "answer":
                update(id, { response: event.data, stage: "done" });
                break;
              case "error":
                update(id, { error: event.data.message, stage: "error" });
                break;
              case "done":
                break;
            }
          },
          abort.signal,
          branchId,
        );
        void queryClient.invalidateQueries({ queryKey: ["query-history"] });
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          update(id, { stage: "cancelled" });
        } else {
          const message =
            err instanceof ApiError && err.status === 429
              ? "Too many questions in a minute — please wait a moment and try again."
              : err instanceof Error
                ? err.message
                : "The question could not be answered.";
          update(id, { error: message, stage: "error" });
        }
      } finally {
        controller.current = null;
      }
    },
    [busy, branchId, queryClient, update],
  );

  const cancel = useCallback(() => controller.current?.abort(), []);
  const clear = useCallback(() => setExchanges([]), []);

  return { exchanges, ask, cancel, clear, busy };
}
