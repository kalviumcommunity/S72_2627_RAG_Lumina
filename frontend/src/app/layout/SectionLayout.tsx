import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowUpRight } from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { queries } from "../../lib/queries";
import { SECTION_NAV, visibleItems, type NavItem, type Section } from "../navigation";
import { paths } from "../paths";
import { useAuth } from "../providers";

function pillClass({ isActive }: { isActive: boolean }) {
  return clsx(
    "inline-flex min-h-9 items-center gap-2 whitespace-nowrap rounded-xl border px-4 text-sm no-underline transition-colors",
    isActive ? "border-primary bg-primary text-white" : "border-hairline text-ink hover:border-primary",
  );
}

/** Items waiting in each review queue — the same queries the queue pages use, so no extra requests. */
function useReviewCounts(enabled: boolean): Record<string, number | undefined> {
  const links = useQuery({ ...queries.supersessions(), enabled });
  const conflicts = useQuery({ ...queries.conflicts("open"), enabled });
  const feedback = useQuery({ ...queries.feedback(false), enabled });
  return {
    [paths.amendments]: links.data?.filter((l) => !l.confirmed).length,
    [paths.conflicts]: conflicts.data?.length,
    [paths.feedback]: feedback.data?.length,
  };
}

function SectionNavLink({ item, count }: { item: NavItem; count: number | undefined }) {
  if (item.external) {
    return (
      <a href={item.to} target="_blank" rel="noreferrer" className={pillClass({ isActive: false })}>
        {item.label}
        <ArrowUpRight className="h-3.5 w-3.5" aria-hidden />
      </a>
    );
  }
  return (
    <NavLink to={item.to} end={item.end} className={pillClass}>
      {({ isActive }) => (
        <>
          {item.label}
          {count !== undefined ? (
            <span
              className={clsx(
                "rounded-full px-1.5 font-mono text-[0.7rem]",
                isActive ? "bg-white/15" : count ? "bg-coral-wash text-coral-ink" : "bg-stone text-muted",
              )}
              aria-label={`${String(count)} waiting`}
            >
              {count}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  );
}

/** A section (Review, Admin) with its own second-level navigation above the page. */
export function SectionLayout({ section }: { section: Section }) {
  const { session } = useAuth();
  const items = visibleItems(SECTION_NAV[section], session?.user);
  const counts = useReviewCounts(section === "review");
  return (
    <>
      <div className="border-b border-hairline">
        <nav
          aria-label={section === "review" ? "Review queues" : "Administration"}
          className="mx-auto flex max-w-7xl gap-2 overflow-x-auto px-4 py-3 sm:px-6 lg:px-10"
        >
          {items.map((item) => (
            <SectionNavLink key={item.to} item={item} count={counts[item.to]} />
          ))}
        </nav>
      </div>
      <Outlet />
    </>
  );
}
