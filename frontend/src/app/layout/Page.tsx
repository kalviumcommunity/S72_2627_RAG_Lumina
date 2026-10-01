import { clsx } from "clsx";
import type { ReactNode } from "react";

import { useDocumentTitle } from "./useDocumentTitle";

/** Standard page container. `title` also becomes the browser tab title. */
export function Page({
  title,
  children,
  width = "wide",
  className,
}: {
  title?: string;
  children: ReactNode;
  width?: "wide" | "narrow";
  className?: string;
}) {
  useDocumentTitle(title);
  return (
    <div
      className={clsx(
        "mx-auto w-full px-4 pb-16 pt-10 sm:px-6 lg:px-10",
        width === "wide" ? "max-w-7xl" : "max-w-3xl",
        className,
      )}
    >
      {children}
    </div>
  );
}

/** Mono eyebrow, a display title, one sentence on what the page is for, and the page's actions. */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-6">
      <div className="max-w-3xl">
        {eyebrow ? <p className="mono-label mb-3 text-muted">{eyebrow}</p> : null}
        <h1 className="text-display">{title}</h1>
        {description ? <p className="mt-4 max-w-2xl text-lead text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-3">{actions}</div> : null}
    </header>
  );
}

/** Heading of a block inside a page: mono label, optional count and actions on the right. */
export function SectionTitle({ children, actions }: { children: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
      <h2 className="mono-label text-ink">{children}</h2>
      {actions}
    </div>
  );
}
