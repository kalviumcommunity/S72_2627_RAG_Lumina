import { hasRole } from "../lib/auth";
import type { Role, User } from "../lib/types";
import { paths } from "./paths";

export interface NavItem {
  to: string;
  label: string;
  role: Role;
  /** Match the path exactly (only for "/"). */
  end?: boolean;
  /** Opens outside the single-page app (e.g. the API reference). */
  external?: boolean;
}

/** Top navigation: one entry per section. Clinicians only have Ask, so they get no menu at all. */
export const MAIN_NAV: NavItem[] = [
  { to: paths.ask, label: "Ask", role: "clinician", end: true },
  { to: paths.library, label: "Library", role: "author" },
  { to: paths.review, label: "Review", role: "author" },
  { to: paths.admin, label: "Admin", role: "admin" },
];

/** Second-level navigation inside a section. */
export const SECTION_NAV = {
  review: [
    { to: paths.amendments, label: "Amendments", role: "author" },
    { to: paths.conflicts, label: "Conflicts", role: "author" },
    { to: paths.feedback, label: "Feedback", role: "author" },
  ],
  admin: [
    { to: paths.admin, label: "Insights", role: "admin", end: true },
    { to: paths.audit, label: "Audit log", role: "admin" },
    { to: paths.apiDocs, label: "API reference", role: "admin", external: true },
  ],
} satisfies Record<string, NavItem[]>;

export type Section = keyof typeof SECTION_NAV;

export function visibleItems(items: NavItem[], user: User | null | undefined): NavItem[] {
  return items.filter((item) => hasRole(user, item.role));
}
