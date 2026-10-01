import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { ToastProvider } from "../components/ui/Toast";
import { API_BASE, api, ApiError } from "../lib/api";
import { auth, type Session } from "../lib/auth";
import { queries } from "../lib/queries";
import type { AuthConfig, TokenResponse } from "../lib/types";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) =>
        !(error instanceof ApiError && [401, 403, 404].includes(error.status)) && count < 2,
    },
  },
});

// ---- auth ----------------------------------------------------------------------------------------

interface AuthState {
  session: Session | null;
  lastExit: "expired" | "signed_out" | null;
  config: AuthConfig | undefined;
  devLogin: (email: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

function useSessionKeepAlive(session: Session | null) {
  const lastActivity = useRef(0);
  useEffect(() => {
    lastActivity.current = Date.now();
    const mark = () => {
      lastActivity.current = Date.now();
    };
    const events = ["pointerdown", "keydown", "touchstart", "wheel"] as const;
    events.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    return () => events.forEach((e) => window.removeEventListener(e, mark));
  }, []);
  useEffect(() => {
    if (!session) return;
    const timer = window.setInterval(() => {
      const current = auth.get(); // clears an expired session → listeners redirect to sign-in
      if (!current) return;
      const remaining = current.expiresAt - Date.now();
      const activeRecently = Date.now() - lastActivity.current < 4 * 60_000;
      if (activeRecently && remaining < 5 * 60_000) {
        api.post<TokenResponse>("/auth/refresh").then(
          (r) => auth.set(r),
          () => undefined,
        );
      }
    }, 30_000);
    return () => window.clearInterval(timer);
  }, [session]);
}

/** Hospital SSO: the API redirects to /auth/callback#token=… after OIDC sign-in. The fragment never
 *  reaches a server log; exchange the token for a full session and drop it from the address bar. */
export async function completeSsoSignIn(): Promise<TokenResponse | null> {
  const match = /[#&]token=([^&]+)/.exec(window.location.hash);
  if (!match?.[1]) return null;
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { Accept: "application/json", Authorization: `Bearer ${decodeURIComponent(match[1])}` },
    });
    return response.ok ? ((await response.json()) as TokenResponse) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => auth.get());
  const [lastExit, setLastExit] = useState<"expired" | "signed_out" | null>(null);
  const config = useQuery(queries.authConfig());

  useEffect(
    () =>
      auth.subscribe((next, reason) => {
        setSession(next);
        if (!next) {
          setLastExit(reason ?? "signed_out");
          queryClient.clear();
        }
      }),
    [],
  );
  useSessionKeepAlive(session);
  useEffect(() => {
    void completeSsoSignIn().then((response) => {
      if (response) auth.set(response);
    });
  }, []);

  const devLogin = useCallback(async (email: string) => {
    const response = await api.post<TokenResponse>("/auth/dev-login", { email });
    setLastExit(null);
    auth.set(response);
  }, []);
  const signOut = useCallback(() => auth.clear("signed_out"), []);

  const value = useMemo(
    () => ({ session, lastExit, config: config.data, devLogin, signOut }),
    [session, lastExit, config.data, devLogin, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <TooltipPrimitive.Provider delayDuration={300}>
          <AuthProvider>{children}</AuthProvider>
        </TooltipPrimitive.Provider>
      </ToastProvider>
    </QueryClientProvider>
  );
}
