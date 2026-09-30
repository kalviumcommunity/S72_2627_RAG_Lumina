/**
 * Streaming answer reader.
 *
 * Uses fetch (not EventSource) so the question travels in a POST body with the Authorization
 * header — never in a URL. The server sends: route → sources → answer (only after verification)
 * → done.
 */
import { API_BASE, ApiError, authHeaders } from "./api";
import { auth } from "./auth";
import type { StreamEvent } from "./types";

export function parseSseChunk(buffer: string): { events: StreamEvent[]; rest: string } {
  const events: StreamEvent[] = [];
  const normalised = buffer.replace(/\r\n/g, "\n");
  const blocks = normalised.split("\n\n");
  const rest = blocks.pop() ?? "";
  for (const block of blocks) {
    let name = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue; // comment / keep-alive
      if (line.startsWith("event:")) name = line.slice(6).trim();
      else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) continue;
    try {
      const parsed: unknown = JSON.parse(data.join("\n"));
      events.push({ event: name, data: parsed } as StreamEvent);
    } catch {
      /* ignore malformed event */
    }
  }
  return { events, rest };
}

export async function streamQuery(
  question: string,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
  branchId?: string | null,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...authHeaders() },
      body: JSON.stringify({ question, branch_id: branchId ?? null }),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach Lumina. Check the connection and try again.");
  }
  if (!response.ok || !response.body) {
    let message = "The question could not be answered";
    let code = `http_${response.status}`;
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      message = body.error?.message ?? message;
      code = body.error?.code ?? code;
    } catch {
      /* ignore */
    }
    if (response.status === 401) auth.clear("expired");
    throw new ApiError(response.status, code, message);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const { events, rest } = parseSseChunk(buffer);
    buffer = rest;
    events.forEach(onEvent);
  }
  const { events } = parseSseChunk(buffer + "\n\n");
  events.forEach(onEvent);
}
