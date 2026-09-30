import { INTENDED_USE } from "../../lib/constants";

export function IntendedUseFooter() {
  return (
    <footer
      className="border-t border-border bg-surface px-4 py-2 text-center text-[0.72rem] leading-snug text-muted"
      aria-label="Intended use"
    >
      <p className="mx-auto max-w-5xl">
        {INTENDED_USE}{" "}
        <span className="font-medium text-amber">Demo corpus is SYNTHETIC — not clinical guidance.</span>
      </p>
    </footer>
  );
}
