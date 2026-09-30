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
import { api, ApiError } from "../lib/api";
import { auth, type Session } from "../lib/auth";
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

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(() => auth.get());
  const [lastExit, setLastExit] = useState<"expired" | "signed_out" | null>(null);
  const config = useQuery({
    queryKey: ["auth-config"],
    queryFn: () => api.get<AuthConfig>("/auth/config"),
    staleTime: 5 * 60_000,
  });

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

// ---- theme ---------------------------------------------------------------------------------------

export type ThemePreference = "light" | "dark" | "system";
const THEME_KEY = "protocite.theme";

interface ThemeState {
  preference: ThemePreference;
  resolved: "light" | "dark";
  setPreference: (p: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

function readPreference(): ThemePreference {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" || v === "system" ? v : "system";
  } catch {
    return "system";
  }
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(readPreference);
  const [systemDark, setSystemDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (e: MediaQueryListEvent) => setSystemDark(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  const resolved = preference === "system" ? (systemDark ? "dark" : "light") : preference;
  useEffect(() => {
    document.documentElement.dataset.theme = resolved;
  }, [resolved]);
  const setPreference = useCallback((p: ThemePreference) => {
    setPreferenceState(p);
    try {
      localStorage.setItem(THEME_KEY, p);
    } catch {
      /* storage unavailable: preference lasts for this page only */
    }
  }, []);
  const value = useMemo(
    () => ({ preference, resolved, setPreference }),
    [preference, resolved, setPreference],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme outside ThemeProvider");
  return ctx;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ToastProvider>
          <TooltipPrimitive.Provider delayDuration={300}>
            <AuthProvider>{children}</AuthProvider>
          </TooltipPrimitive.Provider>
        </ToastProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
