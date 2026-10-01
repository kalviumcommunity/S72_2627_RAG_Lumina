import { clsx } from "clsx";
import type { ReactNode } from "react";

import { percent } from "../../lib/format";

/**
 * A row of headline numbers on the deep-green feature band. Tiles are separated by 1px of
 * lighter green (the grid gap), not by boxes.
 */
export function StatBand({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section
      aria-label={label}
      className="grid grid-cols-1 gap-px overflow-hidden rounded-lg bg-white/15 sm:grid-cols-2 lg:grid-cols-4"
    >
      {children}
    </section>
  );
}

/** One number with a label. Proportional figures: a standalone number is not a column. */
export function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-green px-6 py-7 text-white">
      <p className="mono-label text-white/70">{label}</p>
      <p className="mt-3 text-[2.5rem] font-semibold leading-none tracking-tight">{value}</p>
      {sub ? <p className="mt-3 text-micro text-white/70">{sub}</p> : null}
    </div>
  );
}

/**
 * Horizontal bars for one series: each key's share of `counts`. Slot-1 hue (action blue) on a
 * stone track, 4px rounded data end, square at the baseline; values in text tokens.
 */
export function BarList({
  counts,
  labels = {},
  empty,
  unit,
  order,
}: {
  counts: Record<string, number>;
  labels?: Record<string, string>;
  empty?: string;
  unit?: string;
  /** Fixed key order (e.g. pipeline steps); default is largest first. */
  order?: string[];
}) {
  const entries = order
    ? order.filter((k) => k in counts).map((k): [string, number] => [k, counts[k] ?? 0])
    : Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  if (!total) return empty ? <p className="text-sm text-muted">{empty}</p> : null;
  const max = Math.max(...entries.map(([, n]) => n));
  return (
    <ul className="space-y-4">
      {entries.map(([key, n]) => (
        <li key={key}>
          <div className="flex justify-between gap-3 text-sm">
            <span>{labels[key] ?? key}</span>
            <span className="tabular-nums text-muted">
              {unit ? `${String(n)} ${unit}` : `${String(n)} · ${percent(n / total)}`}
            </span>
          </div>
          <div className="mt-1.5 h-2 rounded-r-xs bg-stone">
            <div
              className="h-2 rounded-r-xs bg-blue"
              style={{ width: `${String(Math.max(1.5, (n / max) * 100))}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Ranked list (label · count) as rule-separated rows. */
export function CountList({
  items,
  empty,
  mono,
}: {
  items: { label: string; count: number }[];
  empty: string;
  mono?: boolean;
}) {
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ol className="divide-y divide-hairline border-y border-hairline">
      {items.map((item) => (
        <li key={item.label} className="flex items-start justify-between gap-4 py-3 text-sm">
          <span className={clsx("min-w-0 break-words", mono && "font-mono")}>{item.label}</span>
          <span className="shrink-0 tabular-nums text-muted">{item.count}</span>
        </li>
      ))}
    </ol>
  );
}
