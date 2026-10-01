import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState } from "react";

import { AnnouncementBar } from "../../app/layout/AnnouncementBar";
import { Footer } from "../../app/layout/Footer";
import { useDocumentTitle } from "../../app/layout/useDocumentTitle";
import { useAuth } from "../../app/providers";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { Spinner } from "../../components/ui/Spinner";
import { API_BASE, errorMessage } from "../../lib/api";
import { roleLabel } from "../../lib/auth";
import { queries } from "../../lib/queries";
import type { Role } from "../../lib/types";

/** What each role can do — shown next to the demo users so the audience sees the permission model. */
const ROLE_CAN: Record<Role, string> = {
  clinician: "Asks questions and opens the cited sources",
  author: "Uploads documents; reviews amendments, conflicts and feedback",
  approver: "Everything an author does, plus approves versions",
  admin: "Everything, plus the admin insights and the audit log",
};
const ROLE_ORDER: Role[] = ["clinician", "author", "approver", "admin"];

const PRINCIPLES: [title: string, body: string][] = [
  [
    "Every sentence is cited",
    "Answers link to the exact clause, version and effective date. A sentence its source does not support is removed before anyone sees it.",
  ],
  [
    "Only what is in force",
    "Drafts, retired versions and clauses replaced by a newer circular never appear in an answer.",
  ],
  [
    "Knows when not to answer",
    "Patient-specific questions are refused and routed to the right person to call — with one tap.",
  ],
];

/** Sign-in. In the demo, pick a seeded user (dev auth); with OIDC configured, use hospital SSO. */
export function LoginPage() {
  useDocumentTitle("Sign in");
  const { devLogin, lastExit, config } = useAuth();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const users = useQuery({ ...queries.devUsers(), enabled: config?.dev_auth !== false });

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

  const groups = ROLE_ORDER.map((role) => ({
    role,
    users: (users.data ?? [])
      .filter((u) => u.role === role)
      .sort((a, b) => a.display_name.localeCompare(b.display_name)),
  })).filter((group) => group.users.length);

  return (
    <div className="flex min-h-full flex-col bg-canvas">
      <AnnouncementBar />
      <header className="mx-auto flex h-16 w-full max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-10">
        <span className="font-display text-2xl tracking-tight text-black">Lumina</span>
        {config?.oidc_enabled ? (
          <Button onClick={() => window.location.assign(`${API_BASE}/auth/oidc/login`)}>
            Sign in with hospital SSO
          </Button>
        ) : null}
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 pb-24 pt-12 sm:px-6 sm:pt-20 lg:px-10">
        <p className="mono-label text-muted">Clinical protocol assistant</p>
        <h1 className="mt-5 max-w-5xl text-hero">Answers you can trace to the clause.</h1>
        <p className="mt-6 max-w-2xl text-lead text-muted">
          Lumina answers on-call questions from your hospital's approved protocols, drug guidelines and
          circulars — and shows the exact clause, version and effective date behind every sentence.
        </p>

        <div className="mt-8 max-w-2xl space-y-3">
          {lastExit === "expired" ? (
            <p role="status" className="rounded-sm border border-hairline bg-stone px-4 py-3 text-sm">
              You were signed out after {config?.session_idle_minutes ?? 15} minutes without activity.
            </p>
          ) : null}
          {error ? <ErrorNotice title="Could not sign in" message={error} /> : null}
        </div>

        <div className="mt-16 grid gap-12 lg:mt-24 lg:grid-cols-[1fr_1.1fr] lg:gap-20">
          <section aria-label="How Lumina works">
            <ol>
              {PRINCIPLES.map(([title, body], index) => (
                <li key={title} className="grid grid-cols-[3rem_1fr] gap-2 border-t border-hairline py-7">
                  <span className="mono-label pt-1.5 text-muted">{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h2 className="text-feature">{title}</h2>
                    <p className="mt-2 text-muted">{body}</p>
                  </div>
                </li>
              ))}
            </ol>
          </section>

          {config?.dev_auth !== false ? (
            <Card tone="dark" className="self-start p-6 sm:p-8" aria-label="Demo users" role="region">
              <p className="mono-label text-coral">Demo sign-in</p>
              <h2 className="mt-2 text-card-heading">Choose a demo user</h2>
              <p className="mt-2 text-sm text-muted-dark">
                Each role sees different pages. No password in the demo.
              </p>

              {users.isLoading ? (
                <div className="mt-6 space-y-2">
                  {[0, 1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-11 w-full bg-white/10" />
                  ))}
                </div>
              ) : users.isError ? (
                <div className="mt-6">
                  <ErrorNotice message={errorMessage(users.error)} />
                </div>
              ) : !groups.length ? (
                <p className="mt-6 text-sm text-muted-dark">No users yet. Run the seed script first.</p>
              ) : (
                <div className="mt-6 space-y-6">
                  {groups.map((group) => (
                    <div key={group.role}>
                      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                        <span className="mono-label rounded-xs bg-white/10 px-2 py-0.5 text-white">
                          {roleLabel[group.role]}
                        </span>
                        <span className="text-micro text-muted-dark">{ROLE_CAN[group.role]}</span>
                      </div>
                      <ul className="mt-2 divide-y divide-white/10 border-y border-white/10">
                        {group.users.map((u) => (
                          <li key={u.id}>
                            <button
                              type="button"
                              disabled={busy !== null}
                              onClick={() => void signIn(u.email)}
                              className="group flex w-full items-center justify-between gap-3 py-3 text-left hover:bg-white/5 disabled:opacity-50"
                            >
                              <span>
                                <span className="text-white">{u.display_name}</span>
                                {u.branch ? (
                                  <span className="ml-2 text-micro text-muted-dark">{u.branch.name}</span>
                                ) : null}
                              </span>
                              {busy === u.email ? (
                                <Spinner className="h-4 w-4 text-white" label="Signing in" />
                              ) : (
                                <ArrowRight
                                  className="h-4 w-4 text-muted-dark transition-transform group-hover:translate-x-0.5 group-hover:text-white"
                                  aria-hidden
                                />
                              )}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
              {config ? (
                <p className="mono-label mt-6 text-muted-dark">
                  Answer model · {config.llm_provider}
                  {config.llm_model ? ` · ${config.llm_model}` : ""}
                </p>
              ) : null}
            </Card>
          ) : null}
        </div>
      </main>

      <Footer tone="dark" />
    </div>
  );
}
