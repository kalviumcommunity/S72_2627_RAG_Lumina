import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { clsx } from "clsx";
import {
  BookOpenCheck,
  FileStack,
  GitMerge,
  Inbox,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Monitor,
  Moon,
  ScrollText,
  Sun,
  TriangleAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, Outlet } from "react-router";

import { hasRole, roleLabel } from "../../lib/auth";
import type { Role } from "../../lib/types";
import { useAuth, useTheme, type ThemePreference } from "../providers";
import { IntendedUseFooter } from "./IntendedUseFooter";

interface NavItem {
  to: string;
  label: string;
  icon: ReactNode;
  role: Role;
}

const NAV: NavItem[] = [
  { to: "/", label: "Ask", icon: <MessageSquareText className="h-4 w-4" />, role: "clinician" },
  { to: "/admin/documents", label: "Documents", icon: <FileStack className="h-4 w-4" />, role: "author" },
  { to: "/admin/supersessions", label: "Amendments", icon: <GitMerge className="h-4 w-4" />, role: "author" },
  { to: "/admin/conflicts", label: "Conflicts", icon: <TriangleAlert className="h-4 w-4" />, role: "author" },
  { to: "/admin/feedback", label: "Feedback", icon: <Inbox className="h-4 w-4" />, role: "author" },
  {
    to: "/admin/dashboard",
    label: "Dashboard",
    icon: <LayoutDashboard className="h-4 w-4" />,
    role: "admin",
  },
  { to: "/admin/audit", label: "Audit log", icon: <ScrollText className="h-4 w-4" />, role: "admin" },
];

const THEMES: { value: ThemePreference; label: string; icon: ReactNode }[] = [
  { value: "light", label: "Light", icon: <Sun className="h-4 w-4" /> },
  { value: "dark", label: "Dark", icon: <Moon className="h-4 w-4" /> },
  { value: "system", label: "Match device", icon: <Monitor className="h-4 w-4" /> },
];

function navClass({ isActive }: { isActive: boolean }) {
  return clsx(
    "inline-flex min-h-10 items-center gap-2 whitespace-nowrap rounded-xl px-3 text-sm font-medium transition-colors",
    isActive ? "bg-accent-soft text-accent-text" : "text-muted hover:bg-surface-2 hover:text-text",
  );
}

export function AppShell() {
  const { session, signOut } = useAuth();
  const { preference, setPreference } = useTheme();
  const user = session?.user;
  const items = NAV.filter((item) => hasRole(user, item.role));
  const menuItem =
    "flex min-h-11 cursor-pointer items-center gap-2 rounded-lg px-3 text-sm outline-none data-[highlighted]:bg-surface-2";

  return (
    <div className="flex h-full flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-50 focus:rounded-lg focus:bg-surface focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-7xl items-center gap-2 px-3 sm:px-4">
          <NavLink
            to="/"
            className="mr-2 flex shrink-0 items-center gap-2 rounded-lg font-semibold"
            aria-label="Lumina home"
          >
            <img src="/favicon.svg" alt="" className="h-8 w-8" />
            <span className="text-lg tracking-tight">Lumina</span>
          </NavLink>
          {items.length > 1 ? (
            <nav aria-label="Main" className="hidden min-w-0 flex-1 items-center gap-1 xl:flex">
              {items.map((item) => (
                <NavLink key={item.to} to={item.to} end={item.to === "/"} className={navClass}>
                  {item.icon}
                  {item.label}
                </NavLink>
              ))}
            </nav>
          ) : null}
          {/* Spacer when the nav is collapsed into the menu (always for clinicians, below xl for others). */}
          <div className={clsx("flex-1", items.length > 1 && "xl:hidden")} />
          {user?.branch ? (
            <span className="hidden shrink-0 whitespace-nowrap rounded-full border border-border px-2.5 py-1 text-xs text-muted sm:inline">
              {user.branch.name}
            </span>
          ) : null}
          <DropdownMenu.Root>
            <DropdownMenu.Trigger
              className="inline-flex min-h-11 items-center gap-2 rounded-xl px-2 hover:bg-surface-2"
              aria-label="Account and navigation menu"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-sm font-semibold text-accent-text">
                {user?.display_name.replace(/^(Dr|Sr)\s+/, "").charAt(0) ?? "?"}
              </span>
              <Menu
                className={clsx("h-5 w-5 text-muted xl:hidden", items.length <= 1 && "hidden")}
                aria-hidden
              />
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                align="end"
                sideOffset={6}
                className="z-50 w-72 rounded-2xl border border-border bg-surface p-2 shadow-xl"
              >
                <div className="px-3 py-2">
                  <p className="font-medium">{user?.display_name}</p>
                  <p className="text-sm text-muted">
                    {user ? roleLabel[user.role] : ""}
                    {user?.branch ? ` · ${user.branch.name}` : ""}
                  </p>
                </div>
                {items.length > 1 ? (
                  <div className="xl:hidden">
                    <DropdownMenu.Separator className="my-1 h-px bg-border" />
                    {items.map((item) => (
                      <DropdownMenu.Item key={item.to} asChild>
                        <NavLink to={item.to} end={item.to === "/"} className={menuItem}>
                          {item.icon}
                          {item.label}
                        </NavLink>
                      </DropdownMenu.Item>
                    ))}
                  </div>
                ) : null}
                <DropdownMenu.Separator className="my-1 h-px bg-border" />
                <DropdownMenu.Label className="px-3 pt-1 text-xs font-medium uppercase tracking-wide text-muted">
                  Theme
                </DropdownMenu.Label>
                <DropdownMenu.RadioGroup
                  value={preference}
                  onValueChange={(v) => setPreference(v as ThemePreference)}
                >
                  {THEMES.map((t) => (
                    <DropdownMenu.RadioItem key={t.value} value={t.value} className={menuItem}>
                      {t.icon}
                      <span className="flex-1">{t.label}</span>
                      <DropdownMenu.ItemIndicator className="text-accent-text">●</DropdownMenu.ItemIndicator>
                    </DropdownMenu.RadioItem>
                  ))}
                </DropdownMenu.RadioGroup>
                <DropdownMenu.Separator className="my-1 h-px bg-border" />
                <DropdownMenu.Item asChild>
                  <a href="/docs" target="_blank" rel="noreferrer" className={menuItem}>
                    <BookOpenCheck className="h-4 w-4" />
                    API documentation
                  </a>
                </DropdownMenu.Item>
                <DropdownMenu.Item onSelect={signOut} className={menuItem}>
                  <LogOut className="h-4 w-4" />
                  Sign out
                </DropdownMenu.Item>
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>
      </header>
      <main id="main" className="min-h-0 flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <IntendedUseFooter />
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}

export function AdminPage({ children }: { children: ReactNode }) {
  return <div className="mx-auto w-full max-w-6xl px-4 py-6">{children}</div>;
}
