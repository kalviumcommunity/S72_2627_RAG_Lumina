import { useQuery } from "@tanstack/react-query";
import { KeyRound, LogIn, ShieldAlert, Stethoscope } from "lucide-react";
import { useState } from "react";

import { useAuth } from "../../app/providers";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { Spinner } from "../../components/ui/Spinner";
import { API_BASE, api, errorMessage } from "../../lib/api";
import { roleLabel } from "../../lib/auth";
import { INTENDED_USE } from "../../lib/constants";
import type { Role, User } from "../../lib/types";

const ROLE_INFO: Record<Role, { tone: Tone; can: string }> = {
  clinician: { tone: "accent", can: "Ask questions and open cited sources" },
  author: { tone: "amber", can: "Upload documents, review amendments, conflicts and feedback" },
  approver: { tone: "success", can: "Everything an author can do, plus approve versions" },
  admin: { tone: "danger", can: "Everything, plus the dashboard and the audit log" },
};
const ROLE_ORDER: Role[] = ["clinician", "author", "approver", "admin"];

/** Sign-in. In the demo, pick a seeded user (dev auth); with OIDC configured, use hospital SSO. */
export function LoginPage() {
  const { devLogin, lastExit, config } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const users = useQuery({
    queryKey: ["dev-users"],
    queryFn: () => api.get<User[]>("/auth/dev-users"),
    enabled: config?.dev_auth !== false,
  });

  const signIn = async (email: string) => {
    setBusy(email);
    setError(null);
    try {
      await devLogin(email);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(null);
    }
  };

  const sorted = [...(users.data ?? [])].sort(
    (a, b) =>
      ROLE_ORDER.indexOf(a.role) - ROLE_ORDER.indexOf(b.role) || a.display_name.localeCompare(b.display_name),
  );

  return (
    <main className="flex min-h-full flex-col items-center justify-center bg-bg px-4 py-10">
      <div className="w-full max-w-lg space-y-6">
        <header className="space-y-2 text-center">
          <div className="mx-auto inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-accent-soft text-accent-text">
            <Stethoscope className="h-7 w-7" aria-hidden />
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Lumina</h1>
          <p className="mx-auto max-w-sm text-sm text-muted">
            Answers from your hospital's approved protocols, drug guidelines and circulars, with the exact
            clause cited.
          </p>
        </header>

        {lastExit === "expired" ? (
          <div
            role="status"
            className="flex items-center gap-2 rounded-xl border border-amber-border bg-amber-soft p-3 text-sm text-amber"
          >
            <ShieldAlert className="h-4 w-4 shrink-0" aria-hidden />
            You were signed out after {config?.session_idle_minutes ?? 15} minutes without activity.
          </div>
        ) : null}
        {error ? <ErrorNotice title="Could not sign in" message={error} /> : null}

        {config?.oidc_enabled ? (
          <Button className="w-full" onClick={() => window.location.assign(`${API_BASE}/auth/oidc/login`)}>
            <KeyRound className="h-4 w-4" /> Sign in with hospital SSO
          </Button>
        ) : null}

        {config?.dev_auth !== false ? (
          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-border px-4 py-3">
              <h2 className="font-semibold">Choose a demo user</h2>
              <Badge tone="amber">Demo sign-in</Badge>
            </div>
            <div className="p-2">
              {users.isLoading ? (
                <div className="space-y-2 p-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-14 w-full" />
                  ))}
                </div>
              ) : users.isError ? (
                <div className="p-2">
                  <ErrorNotice message={errorMessage(users.error)} />
                </div>
              ) : !sorted.length ? (
                <p className="p-4 text-center text-sm text-muted">No users yet. Run the seed script first.</p>
              ) : (
                <ul className="space-y-1">
                  {sorted.map((u) => (
                    <li key={u.id}>
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void signIn(u.email)}
                        className="group flex min-h-14 w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-surface-2 disabled:opacity-60"
                      >
                        <span className="min-w-0">
                          <span className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{u.display_name}</span>
                            <Badge tone={ROLE_INFO[u.role].tone}>{roleLabel[u.role]}</Badge>
                            {u.branch ? <span className="text-xs text-muted">{u.branch.name}</span> : null}
                          </span>
                          <span className="mt-0.5 block text-xs text-muted">{ROLE_INFO[u.role].can}</span>
                        </span>
                        {busy === u.email ? (
                          <Spinner className="h-4 w-4" label="Signing in" />
                        ) : (
                          <LogIn
                            className="h-4 w-4 shrink-0 text-muted group-hover:text-accent"
                            aria-hidden
                          />
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </Card>
        ) : null}

        <p className="text-center text-xs leading-relaxed text-muted">
          {INTENDED_USE}{" "}
          <span className="font-medium text-amber">
            The demo documents are SYNTHETIC and are not clinical guidance.
          </span>
          {config ? (
            <span className="mt-1 block">
              Answer model: {config.llm_provider}
              {config.llm_model ? ` (${config.llm_model})` : ""}
            </span>
          ) : null}
        </p>
      </div>
    </main>
  );
}
