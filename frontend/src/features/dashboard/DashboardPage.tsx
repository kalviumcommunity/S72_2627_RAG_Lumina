import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { CalendarClock, FileWarning, GitMerge, Inbox, SearchX, TriangleAlert } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link } from "react-router";

import { AdminPage, PageHeader } from "../../app/layout/AppShell";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { api, errorMessage } from "../../lib/api";
import { formatLatencyMs, percent } from "../../lib/format";
import type { Stats } from "../../lib/types";

const WINDOWS = [7, 30, 90] as const;

const ROUTE_LABEL: Record<string, string> = {
  answer: "Answered from documents",
  clarify: "Asked to clarify",
  out_of_scope: "Out of scope",
  high_risk: "Refused (patient-specific)",
};
const REASON_LABEL: Record<string, string> = {
  not_found: "Not in the approved documents",
  unverified: "Failed the evidence check",
  high_risk: "Patient-specific request",
  out_of_scope: "Out of scope",
  clarify: "Needed more detail",
  error: "System error",
};

/** Usage, safety and content-gap overview for administrators. */
export function DashboardPage() {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);
  const stats = useQuery({
    queryKey: ["admin-stats", days],
    queryFn: () => api.get<Stats>("/admin/stats", { days }),
    refetchInterval: 60_000,
  });

  return (
    <AdminPage>
      <PageHeader
        title="Dashboard"
        description="How Lumina is being used, how often it declines to answer, and which gaps in the documents need attention."
        actions={
          <div
            className="flex gap-1 rounded-xl border border-border bg-surface-2 p-1"
            role="group"
            aria-label="Time window"
          >
            {WINDOWS.map((d) => (
              <button
                key={d}
                type="button"
                aria-pressed={days === d}
                onClick={() => setDays(d)}
                className={clsx(
                  "min-h-9 rounded-lg px-3 text-sm",
                  days === d ? "bg-surface font-medium shadow-card" : "text-muted",
                )}
              >
                {d} days
              </button>
            ))}
          </div>
        }
      />
      {stats.isLoading ? (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-24" />
          ))}
          <Skeleton className="col-span-2 h-56 lg:col-span-4" />
        </div>
      ) : stats.isError ? (
        <ErrorNotice message={errorMessage(stats.error)} />
      ) : stats.data ? (
        <DashboardBody stats={stats.data} />
      ) : null}
    </AdminPage>
  );
}

function DashboardBody({ stats }: { stats: Stats }) {
  const answeredShare = stats.total_questions ? (stats.answered + stats.partial) / stats.total_questions : 0;
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi
          label="Questions"
          value={stats.total_questions.toLocaleString()}
          sub={`last ${stats.window_days} days`}
        />
        <Kpi
          label="Answered with citations"
          value={stats.total_questions ? percent(answeredShare) : "—"}
          sub={`${stats.answered} full · ${stats.partial} partial`}
        />
        <Kpi
          label="Declined to answer"
          value={stats.total_questions ? percent(stats.abstention_rate) : "—"}
          sub={`${stats.abstained} questions — by design, when evidence is missing`}
        />
        <Kpi
          label="Response time (median)"
          value={stats.latency_p50_ms !== null ? formatLatencyMs(Math.round(stats.latency_p50_ms)) : "—"}
          sub={
            stats.latency_p95_ms !== null
              ? `95% within ${formatLatencyMs(Math.round(stats.latency_p95_ms))}`
              : undefined
          }
        />
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <QueueTile
          to="/admin/documents?filter=pending"
          icon={<FileWarning className="h-5 w-5" />}
          label="Awaiting approval"
          count={stats.documents_awaiting_approval}
        />
        <QueueTile
          to="/admin/supersessions"
          icon={<GitMerge className="h-5 w-5" />}
          label="Amendments to review"
          count={stats.pending_supersessions}
        />
        <QueueTile
          to="/admin/conflicts"
          icon={<TriangleAlert className="h-5 w-5" />}
          label="Open conflicts"
          count={stats.open_conflicts}
        />
        <QueueTile
          to="/admin/feedback"
          icon={<Inbox className="h-5 w-5" />}
          label="Open feedback"
          count={stats.open_feedback}
        />
      </div>

      <Card className="p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Questions per day</h2>
          <div className="flex gap-4 text-xs text-muted">
            <Legend swatch="bg-accent" label="Answered or clarified" />
            <Legend swatch="bg-amber" label="Declined" />
          </div>
        </div>
        <DailyChart stats={stats} />
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card className="p-4">
          <h2 className="mb-3 font-semibold">How questions were handled</h2>
          <Breakdown counts={stats.route_counts} labels={ROUTE_LABEL} empty="No questions yet." />
          {Object.keys(stats.abstain_reasons).length ? (
            <>
              <h3 className="mb-2 mt-5 text-sm font-semibold text-muted">Why answers were declined</h3>
              <Breakdown counts={stats.abstain_reasons} labels={REASON_LABEL} tone="amber" />
            </>
          ) : null}
        </Card>
        <Card className="p-4">
          <h2 className="mb-1 flex items-center gap-2 font-semibold">
            <SearchX className="h-4 w-4 text-amber" aria-hidden /> Not covered by any document
          </h2>
          <p className="mb-3 text-sm text-muted">
            Questions Lumina could not answer. These are candidates for new protocols or circulars.
          </p>
          <CountList items={stats.unanswered_questions} empty="Every question found a source." />
        </Card>
        <Card className="p-4">
          <h2 className="mb-3 font-semibold">Most asked</h2>
          <CountList items={stats.top_questions} empty="No questions yet." />
        </Card>
        <Card className="p-4">
          <h2 className="mb-3 font-semibold">Most cited documents</h2>
          <CountList items={stats.top_documents} empty="No citations yet." mono />
        </Card>
      </div>

      <Card className="p-4">
        <h2 className="mb-3 flex items-center gap-2 font-semibold">
          <CalendarClock className="h-4 w-4 text-danger" aria-hidden /> Overdue for review (
          {stats.stale_documents.length})
        </h2>
        {stats.stale_documents.length ? (
          <ul className="divide-y divide-border">
            {stats.stale_documents.map((d) => (
              <li key={d.document_id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <Link to={`/admin/documents/${d.document_id}`} className="font-medium">
                  {d.doc_code} v{d.version} — {d.title}
                </Link>
                <Badge tone="danger">{d.days_overdue} days overdue</Badge>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Every approved document is within its review date.</p>
        )}
      </Card>
    </div>
  );
}

function Kpi({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <Card className="p-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub ? <p className="mt-0.5 text-xs text-muted">{sub}</p> : null}
    </Card>
  );
}

function QueueTile({
  to,
  icon,
  label,
  count,
}: {
  to: string;
  icon: ReactNode;
  label: string;
  count: number;
}) {
  return (
    <Link
      to={to}
      className={clsx(
        "flex min-h-16 items-center gap-3 rounded-2xl border p-3 no-underline transition-colors",
        count
          ? "border-amber-border bg-amber-soft text-text hover:border-amber"
          : "border-border bg-surface text-muted hover:bg-surface-2",
      )}
    >
      <span className={count ? "text-amber" : "text-muted"}>{icon}</span>
      <span className="min-w-0">
        <span className="block text-xl font-semibold tabular-nums text-text">{count}</span>
        <span className="block text-xs">{label}</span>
      </span>
    </Link>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className={clsx("h-2.5 w-2.5 rounded-sm", swatch)} aria-hidden />
      {label}
    </span>
  );
}

function localIso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${String(d.getFullYear())}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** Stacked daily bars (answered vs declined); days without questions are shown as gaps. */
function DailyChart({ stats }: { stats: Stats }) {
  const byDay = new Map(stats.daily.map((p) => [p.day, p]));
  const days: { day: string; questions: number; abstained: number }[] = [];
  const today = new Date();
  for (let i = stats.window_days - 1; i >= 0; i--) {
    const d = new Date(today);
    d.setDate(today.getDate() - i);
    const key = localIso(d);
    const point = byDay.get(key);
    days.push({ day: key, questions: point?.questions ?? 0, abstained: point?.abstained ?? 0 });
  }
  const max = Math.max(1, ...days.map((d) => d.questions));
  const W = 720;
  const H = 180;
  const pad = { top: 8, bottom: 22, left: 28 };
  const plotH = H - pad.top - pad.bottom;
  const slot = (W - pad.left) / days.length;
  const barW = Math.max(2, Math.min(18, slot * 0.7));
  const y = (v: number) => pad.top + plotH - (v / max) * plotH;
  const labelEvery = Math.ceil(days.length / 8);
  const total = days.reduce((s, d) => s + d.questions, 0);

  if (!total) return <p className="py-10 text-center text-sm text-muted">No questions in this period.</p>;

  return (
    <svg
      viewBox={`0 0 ${String(W)} ${String(H)}`}
      className="h-48 w-full"
      role="img"
      aria-label={`${String(total)} questions over ${String(stats.window_days)} days; busiest day had ${String(max)}.`}
      preserveAspectRatio="none"
    >
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line
            x1={pad.left}
            x2={W}
            y1={y(max * f)}
            y2={y(max * f)}
            stroke="var(--border)"
            strokeDasharray={f ? "3 3" : undefined}
          />
          <text x={pad.left - 6} y={y(max * f) + 4} textAnchor="end" fontSize="10" fill="var(--text-muted)">
            {Math.round(max * f)}
          </text>
        </g>
      ))}
      {days.map((d, i) => {
        const x = pad.left + i * slot + (slot - barW) / 2;
        const handled = d.questions - d.abstained;
        return (
          <g key={d.day}>
            <title>{`${d.day}: ${String(d.questions)} questions, ${String(d.abstained)} declined`}</title>
            {handled > 0 ? (
              <rect
                x={x}
                y={y(d.questions)}
                width={barW}
                height={y(d.abstained) - y(d.questions)}
                fill="var(--accent)"
                rx="1.5"
              />
            ) : null}
            {d.abstained > 0 ? (
              <rect
                x={x}
                y={y(d.abstained)}
                width={barW}
                height={y(0) - y(d.abstained)}
                fill="var(--amber)"
                rx="1.5"
              />
            ) : null}
            {i % labelEvery === 0 ? (
              <text x={x + barW / 2} y={H - 6} textAnchor="middle" fontSize="10" fill="var(--text-muted)">
                {d.day.slice(5)}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

function Breakdown({
  counts,
  labels,
  tone = "accent",
  empty,
}: {
  counts: Record<string, number>;
  labels: Record<string, string>;
  tone?: "accent" | "amber";
  empty?: string;
}) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  if (!total) return empty ? <p className="text-sm text-muted">{empty}</p> : null;
  return (
    <ul className="space-y-2">
      {entries.map(([key, n]) => (
        <li key={key}>
          <div className="flex justify-between text-sm">
            <span>{labels[key] ?? key}</span>
            <span className="tabular-nums text-muted">
              {n} · {percent(n / total)}
            </span>
          </div>
          <div className="mt-1 h-2 rounded-full bg-surface-2">
            <div
              className={clsx("h-2 rounded-full", tone === "amber" ? "bg-amber" : "bg-accent")}
              style={{ width: `${String(Math.max(2, (n / total) * 100))}%` }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function CountList({ items, empty, mono }: { items: Stats["top_questions"]; empty: string; mono?: boolean }) {
  if (!items.length) return <p className="text-sm text-muted">{empty}</p>;
  return (
    <ol className="space-y-1.5">
      {items.map((item) => (
        <li
          key={item.label}
          className="flex items-start justify-between gap-3 rounded-lg bg-surface-2 px-3 py-2 text-sm"
        >
          <span className={clsx("min-w-0 break-words", mono && "font-mono")}>{item.label}</span>
          <Badge className="shrink-0 tabular-nums">{item.count}</Badge>
        </li>
      ))}
    </ol>
  );
}
