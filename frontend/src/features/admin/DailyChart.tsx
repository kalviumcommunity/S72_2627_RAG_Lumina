import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

import type { Stats } from "../../lib/types";

/**
 * Questions per day as stacked columns: declined (coral) on the baseline, answered or clarified
 * (blue) above, separated by a 2px surface gap. Palette checked with the dataviz validator
 * (blue #1863dc / coral #ff7759: CVD ΔE 27, normal ΔE 39). Coral sits below 3:1 on white, so the
 * legend is always shown and every value is also in the table view underneath.
 */

interface Day {
  day: string;
  handled: number;
  declined: number;
}

const HEIGHT = 200;
const PAD = { top: 12, right: 8, bottom: 26, left: 32 };
const GAP = 2;
const RADIUS = 4;

function isoDay(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(d.getFullYear())}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function shortDay(day: string): string {
  return new Date(`${day}T12:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

/** The server groups by UTC day, so the last column is the later of the browser's today and the
 *  newest day in the data (no column lost around midnight). Missing days are zero. */
function fillDays(stats: Stats): Day[] {
  const byDay = new Map(stats.daily.map((p) => [p.day, p]));
  const latest = stats.daily.reduce((max, p) => (p.day > max ? p.day : max), isoDay(new Date()));
  const end = new Date(`${latest}T12:00:00`);
  const days: Day[] = [];
  for (let i = stats.window_days - 1; i >= 0; i--) {
    const d = new Date(end);
    d.setDate(end.getDate() - i);
    const key = isoDay(d);
    const point = byDay.get(key);
    const questions = point?.questions ?? 0;
    const declined = point?.abstained ?? 0;
    days.push({ day: key, handled: questions - declined, declined });
  }
  return days;
}

/** Round the axis up to a clean step (1, 2, 5 × 10ⁿ) so tick labels are whole, readable numbers. */
function niceStep(raw: number): number {
  const p = 10 ** Math.floor(Math.log10(raw));
  const m = raw / p;
  return Math.max(1, (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p);
}

/** A column with a 4px rounded data end and a square base. */
function topRounded(x: number, y: number, w: number, h: number): string {
  const r = Math.min(RADIUS, w / 2, h);
  return `M${String(x)},${String(y + h)}V${String(y + r)}A${String(r)},${String(r)} 0 0 1 ${String(x + r)},${String(y)}H${String(x + w - r)}A${String(r)},${String(r)} 0 0 1 ${String(x + w)},${String(y + r)}V${String(y + h)}Z`;
}

function useWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.round(entry.contentRect.width));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export function DailyChart({ stats }: { stats: Stats }) {
  const days = fillDays(stats);
  const [ref, width] = useWidth<HTMLDivElement>(720);
  const [active, setActive] = useState<number | null>(null);
  const total = days.reduce((s, d) => s + d.handled + d.declined, 0);

  if (!total) return <p className="py-10 text-sm text-muted">No questions in this period.</p>;

  const busiest = Math.max(...days.map((d) => d.handled + d.declined));
  const step = niceStep(busiest / 4);
  const top = step * Math.ceil(busiest / step);
  const ticks = Array.from({ length: top / step + 1 }, (_, i) => i * step);
  const plotW = Math.max(1, width - PAD.left - PAD.right);
  const plotH = HEIGHT - PAD.top - PAD.bottom;
  const slot = plotW / days.length;
  const barW = Math.max(2, Math.min(24, slot - GAP));
  const y = (v: number) => PAD.top + plotH - (v / top) * plotH;
  const labelEvery = Math.ceil(days.length / Math.max(2, Math.floor(plotW / 64)));
  const current = active === null ? null : days[active];

  const onKeyDown = (e: KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const delta = e.key === "ArrowRight" ? 1 : -1;
    setActive((i) =>
      Math.min(days.length - 1, Math.max(0, (i ?? days.length - 1) + (i === null ? 0 : delta))),
    );
  };

  return (
    <div>
      <div ref={ref} className="relative">
        <svg
          width={width}
          height={HEIGHT}
          role="img"
          tabIndex={0}
          aria-label={`${String(total)} questions over ${String(stats.window_days)} days; busiest day had ${String(busiest)}. Use the arrow keys to read each day, or open the table below.`}
          className="block max-w-full rounded-xs focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-focus"
          onKeyDown={onKeyDown}
          onFocus={() => setActive((i) => i ?? days.length - 1)}
          onBlur={() => setActive(null)}
          onPointerLeave={() => setActive(null)}
        >
          {ticks.map((t) => (
            <g key={t}>
              <line
                x1={PAD.left}
                x2={width - PAD.right}
                y1={y(t)}
                y2={y(t)}
                className="stroke-border-light"
              />
              <text
                x={PAD.left - 8}
                y={y(t) + 4}
                textAnchor="end"
                className="fill-muted text-[11px] tabular-nums"
              >
                {t}
              </text>
            </g>
          ))}
          {days.map((d, i) => {
            const x = PAD.left + i * slot + (slot - barW) / 2;
            const declinedTop = y(d.declined);
            const handledBase = d.declined > 0 ? declinedTop - GAP : y(0);
            const handledTop = y(d.handled + d.declined) - (d.declined > 0 ? GAP : 0);
            const dim = active !== null && active !== i;
            return (
              <g key={d.day} opacity={dim ? 0.45 : 1}>
                {d.declined > 0 ? (
                  d.handled > 0 ? (
                    <rect
                      x={x}
                      y={declinedTop}
                      width={barW}
                      height={y(0) - declinedTop}
                      className="fill-coral"
                    />
                  ) : (
                    <path d={topRounded(x, declinedTop, barW, y(0) - declinedTop)} className="fill-coral" />
                  )
                ) : null}
                {d.handled > 0 ? (
                  <path
                    d={topRounded(x, handledTop, barW, Math.max(1, handledBase - handledTop))}
                    className="fill-blue"
                  />
                ) : null}
                {/* Hit target: the whole column slot, not just the painted pixels. */}
                <rect
                  x={PAD.left + i * slot}
                  y={PAD.top}
                  width={slot}
                  height={plotH}
                  fill="transparent"
                  onPointerEnter={() => setActive(i)}
                />
                {i % labelEvery === 0 ? (
                  <text
                    x={x + barW / 2}
                    y={HEIGHT - 8}
                    textAnchor="middle"
                    className="fill-muted text-[11px]"
                  >
                    {shortDay(d.day)}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>
        {current && active !== null ? (
          <div
            role="status"
            className="pointer-events-none absolute top-0 z-10 w-44 -translate-x-1/2 rounded-sm border border-hairline bg-canvas px-3 py-2 text-xs"
            style={{
              left: `${String(Math.min(width - 88, Math.max(88, PAD.left + (active + 0.5) * slot)))}px`,
            }}
          >
            <p className="text-muted">{shortDay(current.day)}</p>
            <p className="mt-1 flex items-center gap-2">
              <span className="h-0.5 w-3 bg-blue" aria-hidden />
              <span className="font-semibold tabular-nums">{current.handled}</span>
              <span className="text-muted">answered or clarified</span>
            </p>
            <p className="flex items-center gap-2">
              <span className="h-0.5 w-3 bg-coral" aria-hidden />
              <span className="font-semibold tabular-nums">{current.declined}</span>
              <span className="text-muted">declined</span>
            </p>
          </div>
        ) : null}
      </div>
      <details className="mt-4 text-sm">
        <summary className="cursor-pointer text-muted underline decoration-hairline underline-offset-4 hover:text-ink">
          Show as table
        </summary>
        <table className="mt-3 w-full max-w-md text-left" aria-label="Questions per day">
          <thead>
            <tr className="border-b border-hairline">
              <th className="mono-label py-2 font-normal text-muted">Day</th>
              <th className="mono-label py-2 text-right font-normal text-muted">Answered or clarified</th>
              <th className="mono-label py-2 text-right font-normal text-muted">Declined</th>
            </tr>
          </thead>
          <tbody>
            {days
              .filter((d) => d.handled + d.declined > 0)
              .map((d) => (
                <tr key={d.day} className="border-b border-hairline">
                  <td className="py-2">{shortDay(d.day)}</td>
                  <td className="py-2 text-right tabular-nums">{d.handled}</td>
                  <td className="py-2 text-right tabular-nums">{d.declined}</td>
                </tr>
              ))}
          </tbody>
        </table>
        <p className="mt-2 text-micro text-muted">Days with no questions are left out.</p>
      </details>
    </div>
  );
}

/** Legend: rect keys (the marks are columns), text in ink — never in the series colour. */
export function DailyLegend() {
  return (
    <p className="flex flex-wrap gap-x-5 gap-y-1 text-micro text-muted">
      <span className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-[2px] bg-blue" aria-hidden /> Answered or clarified
      </span>
      <span className="flex items-center gap-2">
        <span className="h-2.5 w-2.5 rounded-[2px] bg-coral" aria-hidden /> Declined
      </span>
    </p>
  );
}
