import { clsx } from "clsx";
import { Link } from "react-router";

import { SectionTitle } from "../../app/layout/Page";
import { paths } from "../../app/paths";
import { formatLatencyMs, percent } from "../../lib/format";
import type { Stats } from "../../lib/types";
import { DailyChart, DailyLegend } from "./DailyChart";
import { BarList, CountList, Stat, StatBand } from "./parts";

const ROUTE_LABEL: Record<string, string> = {
  answer: "Looked up in documents",
  clarify: "Asked to clarify",
  out_of_scope: "Out of scope",
  high_risk: "Refused (patient-specific)",
};
const REASON_LABEL: Record<string, string> = {
  not_found: "Not in the approved documents",
  high_risk: "Patient-specific request",
  out_of_scope: "Out of scope",
  clarify: "Needed more detail",
  unavailable: "Answer service unavailable",
};

/** Usage at a glance, the work queues, and gaps in the documents. */
export function OverviewTab({ stats }: { stats: Stats }) {
  const answeredShare = stats.total_questions ? (stats.answered + stats.partial) / stats.total_questions : 0;
  return (
    <div className="space-y-14">
      <StatBand label="Usage">
        <Stat
          label="Questions"
          value={stats.total_questions.toLocaleString()}
          sub={`last ${stats.window_days} days`}
        />
        <Stat
          label="Answered with citations"
          value={stats.total_questions ? percent(answeredShare) : "—"}
          sub={`${stats.answered} fully · ${stats.partial} partly`}
        />
        <Stat
          label="Declined to answer"
          value={stats.total_questions ? percent(stats.abstention_rate) : "—"}
          sub={`${stats.abstained} — by design when evidence is missing`}
        />
        <Stat
          label="Response time (median)"
          value={stats.latency_p50_ms !== null ? formatLatencyMs(Math.round(stats.latency_p50_ms)) : "—"}
          sub={
            stats.latency_p95_ms !== null
              ? `95% within ${formatLatencyMs(Math.round(stats.latency_p95_ms))}`
              : undefined
          }
        />
      </StatBand>

      <section aria-label="Work waiting">
        <SectionTitle>Work waiting for someone</SectionTitle>
        <ul className="grid grid-cols-1 border-t border-primary sm:grid-cols-2 lg:grid-cols-4">
          <Queue
            to={`${paths.library}?filter=pending`}
            label="Versions awaiting approval"
            count={stats.documents_awaiting_approval}
          />
          <Queue to={paths.amendments} label="Amendments to review" count={stats.pending_supersessions} />
          <Queue to={paths.conflicts} label="Open conflicts" count={stats.open_conflicts} />
          <Queue to={paths.feedback} label="Open feedback" count={stats.open_feedback} />
        </ul>
      </section>

      <section aria-label="Questions per day">
        <SectionTitle actions={<DailyLegend />}>Questions per day</SectionTitle>
        <DailyChart stats={stats} />
      </section>

      <div className="grid grid-cols-1 gap-x-16 gap-y-14 lg:grid-cols-2">
        <section aria-label="How questions were handled">
          <SectionTitle>How questions were handled</SectionTitle>
          <BarList counts={stats.route_counts} labels={ROUTE_LABEL} empty="No questions yet." />
          {Object.keys(stats.abstain_reasons).length ? (
            <div className="mt-10">
              <SectionTitle>Why answers were declined</SectionTitle>
              <BarList counts={stats.abstain_reasons} labels={REASON_LABEL} />
            </div>
          ) : null}
        </section>
        <section aria-label="Not covered by any document">
          <SectionTitle>Not covered by any document</SectionTitle>
          <p className="-mt-2 mb-4 text-caption text-muted">Candidates for a new protocol or circular.</p>
          <CountList items={stats.unanswered_questions} empty="Every question found a source." />
        </section>
        <section aria-label="Most asked">
          <SectionTitle>Most asked</SectionTitle>
          <CountList items={stats.top_questions} empty="No questions yet." />
        </section>
        <section aria-label="Most cited documents">
          <SectionTitle>Most cited documents</SectionTitle>
          <CountList items={stats.top_documents} empty="No citations yet." mono />
        </section>
      </div>

      <section aria-label="Overdue for review">
        <SectionTitle>Overdue for review ({stats.stale_documents.length})</SectionTitle>
        {stats.stale_documents.length ? (
          <ul className="divide-y divide-hairline border-y border-hairline">
            {stats.stale_documents.map((d) => (
              <li
                key={d.document_id}
                className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm"
              >
                <Link to={paths.document(d.document_id)} className="text-ink">
                  <span className="font-mono">
                    {d.doc_code} v{d.version}
                  </span>{" "}
                  — {d.title}
                </Link>
                <span className="text-error">{d.days_overdue} days overdue</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted">Every approved document is within its review date.</p>
        )}
      </section>
    </div>
  );
}

/** One work queue: the count leads, the label names where the link goes. */
function Queue({ to, label, count }: { to: string; label: string; count: number }) {
  return (
    <li className="border-b border-hairline sm:[&:nth-child(odd)]:border-r lg:border-r lg:last:border-r-0">
      <Link to={to} className="group block py-6 text-ink no-underline sm:px-6">
        <span className={clsx("block text-[2rem] font-semibold leading-none", !count && "text-muted")}>
          {count}
        </span>
        <span className="mt-3 block text-sm group-hover:underline">{label} →</span>
      </Link>
    </li>
  );
}
