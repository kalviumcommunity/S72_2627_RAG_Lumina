import { Outlet } from "react-router";

import { ButtonLink } from "../components/ui/Button";
import { hasRole, roleLabel } from "../lib/auth";
import type { Role } from "../lib/types";
import { Page } from "./layout/Page";
import { paths } from "./paths";
import { useAuth } from "./providers";

/** Renders nested routes only for users with at least `role`. The API enforces the same rule. */
export function RequireRole({ role }: { role: Role }) {
  const { session } = useAuth();
  if (hasRole(session?.user, role)) return <Outlet />;
  return (
    <Page title="Not available" width="narrow">
      <div className="py-16">
        <p className="mono-label text-muted">Access</p>
        <h1 className="mt-3 text-section">Not available for your role</h1>
        <p className="mt-4 text-lead text-muted">
          This page needs the {roleLabel[role]} role. You are signed in as{" "}
          {session ? roleLabel[session.user.role] : "a guest"}.
        </p>
        <ButtonLink to={paths.ask} className="mt-8">
          Back to Ask
        </ButtonLink>
      </div>
    </Page>
  );
}
