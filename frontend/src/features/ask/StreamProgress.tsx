import { clsx } from "clsx";
import { Check, FileSearch, ShieldCheck, Split } from "lucide-react";

import { Skeleton } from "../../components/ui/Skeleton";
import { Spinner } from "../../components/ui/Spinner";
import { sectionLabel } from "../../lib/format";
import type { SourceCard } from "../../lib/types";
import type { Stage } from "./useAskStream";

const STEPS: { key: Stage; label: string; icon: typeof Split }[] = [
  { key: "routing", label: "Checking the question", icon: Split },
  { key: "retrieving", label: "Finding approved sources", icon: FileSearch },
  { key: "verifying", label: "Checking every statement against the source", icon: ShieldCheck },
];

const ORDER: Stage[] = ["routing", "retrieving", "verifying", "done"];

/** Live stage indicator while an answer is being prepared. */
export function StreamProgress({ stage }: { stage: Stage }) {
  const current = ORDER.indexOf(stage);
  return (
    <ol className="flex flex-col gap-1.5 sm:flex-row sm:gap-4" aria-live="polite">
      {STEPS.map((step, index) => {
        const done = current > index;
        const active = current === index;
        const Icon = step.icon;
        return (
          <li
            key={step.key}
            className={clsx(
              "flex items-center gap-2 text-sm",
              done ? "text-success" : active ? "font-medium text-text" : "text-muted",
            )}
          >
            {done ? (
              <Check className="h-4 w-4" aria-hidden />
            ) : active ? (
              <Spinner className="h-4 w-4 text-accent" />
            ) : (
              <Icon className="h-4 w-4" aria-hidden />
            )}
            {step.label}
          </li>
        );
      })}
    </ol>
  );
}

/** Retrieved passages appear as soon as they are found (before the answer is verified). */
export function SourceCards({
  sources,
  loading,
  onOpen,
}: {
  sources: SourceCard[];
  loading: boolean;
  onOpen: (chunkId: string) => void;
}) {
  if (loading && !sources.length) {
    return (
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" aria-hidden>
        {[0, 1].map((i) => (
          <div key={i} className="rounded-xl border border-border bg-surface p-3">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="mt-2 h-3 w-full" />
            <Skeleton className="mt-1.5 h-3 w-4/5" />
          </div>
        ))}
      </div>
    );
  }
  if (!sources.length) return null;
  return (
    <div>
      <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
        Approved sources found
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {sources.slice(0, 4).map((s) => (
          <button
            key={s.chunk_id}
            type="button"
            onClick={() => onOpen(s.chunk_id)}
            className="rounded-xl border border-border bg-surface p-3 text-left hover:border-accent"
          >
            <span className="flex items-center justify-between gap-2 text-sm font-semibold">
              <span>
                {s.doc_code} {sectionLabel(s.section_path)}
              </span>
              <span className="text-xs font-normal text-muted">v{s.version}</span>
            </span>
            <span className="block truncate text-xs text-muted">{s.heading}</span>
            <span className="mt-1 line-clamp-2 block text-sm">{s.snippet}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
