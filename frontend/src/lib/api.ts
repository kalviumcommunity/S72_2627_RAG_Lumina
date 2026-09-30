/** Typed fetch client for /api/v1 (same origin; the dev server proxies /api to the backend). */
import { auth } from "./auth";

export const API_BASE = "/api/v1";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface RequestOptions {
  body?: unknown;
  form?: FormData;
  query?: Query;
  signal?: AbortSignal;
}

function url(path: string, query?: Query): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
  }
  const s = qs.toString();
  return `${API_BASE}${path}${s ? `?${s}` : ""}`;
}

export function authHeaders(): Record<string, string> {
  const token = auth.token();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function toError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let message = response.statusText || "Request failed";
  let details: unknown;
  try {
    const body = (await response.json()) as {
      error?: { code?: string; message?: string; details?: unknown };
    };
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      details = body.error.details;
    }
  } catch {
    /* non-JSON error body */
  }
  if (response.status === 401) auth.clear("expired");
  return new ApiError(response.status, code, message, details);
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json", ...authHeaders() };
  let body: BodyInit | undefined;
  if (options.form) {
    body = options.form;
  } else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(url(path, options.query), { method, headers, body, signal: options.signal });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") throw err;
    throw new ApiError(0, "network_error", "Cannot reach ProtoCite. Check the connection and try again.");
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query, signal?: AbortSignal) => request<T>("GET", path, { query, signal }),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, { body }),
  postForm: <T>(path: string, form: FormData) => request<T>("POST", path, { form }),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, { body }),
  del: <T>(path: string) => request<T>("DELETE", path),
  /** Authenticated binary download (PDF viewer, CSV export). */
  async blob(path: string, query?: Query): Promise<Blob> {
    const response = await fetch(url(path, query), { headers: authHeaders() });
    if (!response.ok) throw await toError(response);
    return response.blob();
  },
};

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
