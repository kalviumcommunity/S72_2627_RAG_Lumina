import { clsx } from "clsx";

import { Spinner } from "../../components/ui/Spinner";
import type { Stage } from "./useAskStream";

const STEPS: { key: Stage; label: string; short: string }[] = [
  { key: "routing", label: "Checking the question", short: "Check" },
  { key: "retrieving", label: "Finding approved sources", short: "Search" },
  { key: "verifying", label: "Checking every statement against its source", short: "Verify" },
];

/** While an answer is prepared: the three pipeline steps, the current one spelled out. */
export function StreamProgress({ stage }: { stage: Stage }) {
  const index = STEPS.findIndex((s) => s.key === stage);
  const step = STEPS[index];
  if (!step) return null;
  return (
    <div className="rounded-md border border-hairline p-5" aria-live="polite">
      <ol className="flex gap-2" aria-hidden>
        {STEPS.map((s, i) => (
          <li
            key={s.key}
            className={clsx(
              "mono-label flex-1 border-t-2 pt-2",
              i < index
                ? "border-green text-green"
                : i === index
                  ? "border-primary text-ink"
                  : "border-hairline text-muted",
            )}
          >
            {String(i + 1).padStart(2, "0")} {s.short}
          </li>
        ))}
      </ol>
      <p className="mt-4 flex items-center gap-2">
        <Spinner className="h-4 w-4" />
        <span>{step.label}</span>
        <span className="mono-label text-muted">
          step {index + 1} of {STEPS.length}
        </span>
      </p>
    </div>
  );
}
