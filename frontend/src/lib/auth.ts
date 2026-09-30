/**
 * Session storage for the access token.
 *
 * sessionStorage (not localStorage): closing the browser on a shared ward terminal ends the
 * session. Tokens are short-lived (SESSION_IDLE_MINUTES, default 15); `useSessionKeepAlive`
 * refreshes the token only while the user is active, so an idle terminal locks itself.
 */
import type { Role, TokenResponse, User } from "./types";

const KEY = "protocite.session";
const ROLE_RANK: Record<Role, number> = { clinician: 0, author: 1, approver: 2, admin: 3 };

export interface Session {
  token: string;
  expiresAt: number; // epoch ms
  user: User;
}

type Listener = (session: Session | null, reason?: "expired" | "signed_out") => void;
const listeners = new Set<Listener>();
let current: Session | null = read();

function read(): Session | null {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Session;
    return parsed.expiresAt > Date.now() ? parsed : null;
  } catch {
    return null;
  }
}

function write(session: Session | null): void {
  try {
    if (session) sessionStorage.setItem(KEY, JSON.stringify(session));
    else sessionStorage.removeItem(KEY);
  } catch {
    /* storage unavailable (private mode): keep the session in memory only */
  }
}

export const auth = {
  get(): Session | null {
    if (current && current.expiresAt <= Date.now()) {
      this.clear("expired");
    }
    return current;
  },
  token(): string | null {
    return this.get()?.token ?? null;
  },
  set(response: TokenResponse): Session {
    current = {
      token: response.access_token,
      expiresAt: Date.now() + response.expires_in * 1000,
      user: response.user,
    };
    write(current);
    listeners.forEach((l) => l(current));
    return current;
  },
  clear(reason: "expired" | "signed_out" = "signed_out"): void {
    const had = current !== null;
    current = null;
    write(null);
    // Viewed sources are cached for offline use; a shared terminal must not keep them after sign-out.
    if ("caches" in window) void caches.delete("protocite-sources").catch(() => undefined);
    if (had) listeners.forEach((l) => l(null, reason));
  },
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
};

export function hasRole(user: User | null | undefined, minimum: Role): boolean {
  return !!user && ROLE_RANK[user.role] >= ROLE_RANK[minimum];
}

export const roleLabel: Record<Role, string> = {
  clinician: "Clinician",
  author: "Document author",
  approver: "Approver",
  admin: "Administrator",
};
