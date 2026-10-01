import { clsx } from "clsx";

import { INTENDED_USE } from "../../lib/constants";

/** The intended-use statement, required on every screen. Slim inside the app, a dark band elsewhere. */
export function Footer({ tone = "light" }: { tone?: "light" | "dark" }) {
  return (
    <footer
      id="intended-use"
      aria-label="Intended use"
      className={clsx(
        "px-4 sm:px-6 lg:px-10",
        tone === "light" ? "border-t border-hairline bg-canvas py-3" : "bg-primary py-12 text-white",
      )}
    >
      <div className="mx-auto flex max-w-7xl flex-col gap-2 sm:flex-row sm:items-baseline sm:gap-6">
        <p className={clsx("mono-label shrink-0", tone === "light" ? "text-ink" : "text-coral")}>
          Intended use
        </p>
        <p className={clsx("text-micro", tone === "light" ? "text-muted" : "text-muted-dark")}>
          {INTENDED_USE}
        </p>
      </div>
    </footer>
  );
}
