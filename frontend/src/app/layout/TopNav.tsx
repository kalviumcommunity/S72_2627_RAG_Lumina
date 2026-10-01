import { clsx } from "clsx";
import { Menu, X } from "lucide-react";
import { useState } from "react";
import { NavLink, useLocation } from "react-router";

import { roleLabel } from "../../lib/auth";
import { MAIN_NAV, visibleItems } from "../navigation";
import { paths } from "../paths";
import { useAuth } from "../providers";

function linkClass({ isActive }: { isActive: boolean }) {
  return clsx(
    "rounded-pill px-4 py-2 text-sm no-underline transition-colors",
    isActive ? "bg-primary text-white" : "text-ink hover:bg-stone",
  );
}

/** Three zones: wordmark left, sections centred, identity and sign-out right. */
export function TopNav() {
  const { session, signOut } = useAuth();
  const user = session?.user;
  const items = visibleItems(MAIN_NAV, user);
  const hasMenu = items.length > 1;
  // The menu belongs to the page it was opened on, so it closes itself on navigation.
  const location = useLocation();
  const [openOn, setOpenOn] = useState<string | null>(null);
  const open = openOn === location.pathname;

  return (
    <header className="sticky top-0 z-30 border-b border-hairline bg-canvas/95 backdrop-blur">
      <div className="mx-auto grid h-16 max-w-7xl grid-cols-[1fr_auto] items-center gap-4 px-4 sm:px-6 md:grid-cols-[1fr_auto_1fr] lg:px-10">
        <NavLink
          to={paths.ask}
          className="justify-self-start font-display text-2xl tracking-tight text-black no-underline"
          aria-label="Lumina home"
        >
          Lumina
        </NavLink>

        {hasMenu ? (
          <nav aria-label="Main" className="hidden items-center gap-1 md:flex">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                {item.label}
              </NavLink>
            ))}
          </nav>
        ) : (
          <span className="hidden md:block" />
        )}

        <div className="flex items-center justify-self-end gap-3">
          <span className="hidden text-right leading-tight lg:block">
            <span className="block text-sm text-ink">{user?.display_name}</span>
            <span className="block text-micro text-muted">
              {user ? roleLabel[user.role] : ""}
              {user?.branch ? ` · ${user.branch.name}` : ""}
            </span>
          </span>
          <button
            type="button"
            onClick={signOut}
            className="min-h-9 rounded-pill border border-primary px-4 text-sm hover:bg-primary hover:text-white"
          >
            Sign out
          </button>
          {hasMenu ? (
            <button
              type="button"
              className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-hairline md:hidden"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              aria-controls="mobile-menu"
              onClick={() => setOpenOn(open ? null : location.pathname)}
            >
              {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
            </button>
          ) : null}
        </div>
      </div>

      {hasMenu && open ? (
        <nav id="mobile-menu" aria-label="Main" className="border-t border-hairline px-4 py-3 md:hidden">
          <p className="mb-2 text-micro text-muted">
            {user?.display_name} · {user ? roleLabel[user.role] : ""}
          </p>
          <div className="flex flex-col gap-1">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
      ) : null}
    </header>
  );
}
