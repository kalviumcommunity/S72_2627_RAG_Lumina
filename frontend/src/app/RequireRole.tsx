import { ShieldX } from "lucide-react";
import { Link, Outlet } from "react-router";

import { hasRole, roleLabel } from "../lib/auth";
import type { Role } from "../lib/types";
import { AdminPage } from "./layout/AppShell";
import { useAuth } from "./providers";

/** Renders nested admin routes only for users with at least `role`. */
export function RequireRole({ role }: { role: Role }) {
  const { session } = useAuth();
  if (hasRole(session?.user, role)) return <Outlet />;
  return (
    <AdminPage>
      <div className="mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 text-center">
        <ShieldX className="mx-auto h-8 w-8 text-muted" aria-hidden />
        <h1 className="mt-2 text-lg font-semibold">Not available for your role</h1>
        <p className="mt-1 text-sm text-muted">
          This page needs the {roleLabel[role]} role. You are signed in as{" "}
          {session ? roleLabel[session.user.role] : "a guest"}.
        </p>
        <Link to="/" className="mt-4 inline-block text-sm font-medium">
          Back to Ask
        </Link>
      </div>
    </AdminPage>
  );
}
