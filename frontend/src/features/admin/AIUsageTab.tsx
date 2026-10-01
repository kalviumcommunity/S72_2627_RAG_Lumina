import { Fragment, useState } from "react";

import { SectionTitle } from "../../app/layout/Page";
import { Table, Td, Th, Tr } from "../../components/ui/Table";
import { formatDateTime, formatLatencyMs, percent } from "../../lib/format";
import type { AIDecision, AIUsage } from "../../lib/types";
import { BarList, Stat, StatBand } from "./parts";

const MODE_LABEL: Record<string, string> = {
  llm: "Written by the AI model, then verified",
  extractive: "Quoted verbatim from the document",
  "not drafted": "No answer drafted (refused, clarify or not found)",
};
const SOURCE_LABEL: Record<string, string> = {
  rules: "Safety rules (deterministic)",
  llm: "AI classifier",
  "llm+rules": "AI classifier, overruled by clinical-term check",
  "not recorded": "Not recorded (asked before tracing was added)",
};
const STAGE_LABEL: Record<string, string> = {
  route: "1. Check the question",
  retrieve: "2. Find sources",
  generate: "3. Draft the answer",
  verify: "4. Verify every statement",
  total: "Total",
};
const TASK_LABEL: Record<string, string> = {
  classify: "Classify the question",
  generate: "Write the answer",
  verify: "Judge each statement",
  conflict: "Confirm a conflict",
};

/** How the AI is configured, what it did, and a per-question trace of its decisions. */
export function AIUsageTab({ ai }: { ai: AIUsage }) {
  const c = ai.config;
  const verified = ai.claims_checked ? ai.claims_supported / ai.claims_checked : null;
  return (
    <div className="space-y-14">
      <StatBand label="AI at a glance">
        <Stat label="Questions handled" value={ai.questions.toLocaleString()} />
        <Stat
          label="Statements verified"
          value={verified === null ? "—" : percent(verified)}
          sub={`${String(ai.claims_supported)} of ${String(ai.claims_checked)} kept; the rest were removed`}
        />
        <Stat
          label="Answers written by the AI"
          value={String(ai.generation_modes.llm ?? 0)}
          sub={`${String(ai.generation_modes.extractive ?? 0)} quoted verbatim`}
        />
        <Stat
          label="Identifiers removed"
          value={String(ai.pii_redacted)}
          sub="questions with patient details stripped before search"
        />
      </StatBand>

      <section aria-label="How the AI is set up">
        <SectionTitle>How the AI is set up</SectionTitle>
        <dl className="grid grid-cols-1 gap-x-12 border-t border-primary text-sm sm:grid-cols-2">
          <Row
            term="Answer model"
            value={c.llm_model ? `${c.llm_provider} · ${c.llm_model}` : "none — verbatim quotes only"}
          />
          <Row term="Reasoning (thinking) level" value={c.reasoning_level ?? "—"} />
          <Row term="Embeddings (semantic search)" value={c.embedding_model} />
          <Row term="Re-ranker" value={c.reranker_model} />
          <Row term="Identifier removal" value={c.pii_engine} />
          <Row
            term="Verifier"
            value={`${c.verifier_mode}, keeps a statement at score ≥ ${String(c.verifier_threshold)}`}
          />
          <Row term="Minimum relevance to answer" value={String(c.min_relevance)} />
          <Row
            term="Prompt versions"
            value={Object.entries(c.prompt_versions)
              .map(([k, v]) => `${k}@${v}`)
              .join(" · ")}
          />
        </dl>
      </section>

      <div className="grid grid-cols-1 gap-x-16 gap-y-14 lg:grid-cols-2">
        <section aria-label="How answers were produced">
          <SectionTitle>How answers were produced</SectionTitle>
          <BarList counts={ai.generation_modes} labels={MODE_LABEL} empty="No questions yet." />
        </section>
        <section aria-label="Who decided how to handle each question">
          <SectionTitle>Who decided how to handle each question</SectionTitle>
          <BarList counts={ai.route_sources} labels={SOURCE_LABEL} empty="No questions yet." />
        </section>
        <section aria-label="Average time per step">
          <SectionTitle>Average time per step</SectionTitle>
          <BarList
            counts={Object.fromEntries(Object.entries(ai.avg_stage_ms).map(([k, v]) => [k, Math.round(v)]))}
            labels={STAGE_LABEL}
            order={Object.keys(STAGE_LABEL)}
            unit="ms"
            empty="No timings yet."
          />
        </section>
        <section aria-label="AI model calls">
          <SectionTitle>AI model calls since the server started</SectionTitle>
          {ai.llm_calls.length ? (
            <Table label="AI model calls">
              <thead>
                <tr>
                  <Th>Step</Th>
                  <Th className="text-right">Calls</Th>
                  <Th className="text-right">Failed</Th>
                  <Th className="text-right">Avg time</Th>
                </tr>
              </thead>
              <tbody>
                {ai.llm_calls.map((u) => (
                  <Tr key={u.task}>
                    <Td>{TASK_LABEL[u.task] ?? u.task}</Td>
                    <Td className="text-right tabular-nums">{u.calls}</Td>
                    <Td className="text-right tabular-nums">
                      {u.failures}
                      {u.timeouts ? ` (${String(u.timeouts)} timed out)` : ""}
                    </Td>
                    <Td className="text-right tabular-nums">
                      {formatLatencyMs(u.avg_ms === null ? null : Math.round(u.avg_ms))}
                    </Td>
                  </Tr>
                ))}
              </tbody>
            </Table>
          ) : (
            <p className="text-sm text-muted">
              {c.llm_model
                ? "No AI model calls yet."
                : "No AI model configured: answers are verbatim quotes checked by the lexical verifier."}
            </p>
          )}
          {ai.llm_calls.some((u) => u.failures) ? (
            <p className="mt-3 text-micro text-muted">
              A failed or slow call never reaches the user: that step falls back to its deterministic version.
            </p>
          ) : null}
        </section>
      </div>

      <section aria-label="Recent decisions">
        <SectionTitle>Recent decisions</SectionTitle>
        <p className="-mt-2 mb-4 text-caption text-muted">
          What the system decided for each question and why. Open a row to see the full trace.
        </p>
        <DecisionTable decisions={ai.recent} />
      </section>
    </div>
  );
}

function Row({ term, value }: { term: string; value: string }) {
  return (
    <div className="flex justify-between gap-6 border-b border-hairline py-3">
      <dt className="text-muted">{term}</dt>
      <dd className="text-right">{value}</dd>
    </div>
  );
}

function outcomeLabel(d: AIDecision): string {
  if (d.outcome === "answered") return "Answered";
  if (d.outcome === "partial") return "Partly answered";
  const reasons: Record<string, string> = {
    high_risk: "Refused — patient-specific",
    not_found: "Not found — escalated",
    out_of_scope: "Out of scope",
    clarify: "Asked to clarify",
    unavailable: "Service unavailable",
  };
  return reasons[d.abstain_reason ?? ""] ?? "Declined";
}

function DecisionTable({ decisions }: { decisions: AIDecision[] }) {
  const [open, setOpen] = useState<string | null>(null);
  if (!decisions.length) return <p className="text-sm text-muted">No questions in this period.</p>;
  return (
    <Table label="Recent decisions">
      <thead>
        <tr>
          <Th>When</Th>
          <Th>Who</Th>
          <Th>Question (identifiers removed)</Th>
          <Th>Result</Th>
          <Th className="text-right">Time</Th>
          <Th>
            <span className="sr-only">Details</span>
          </Th>
        </tr>
      </thead>
      <tbody>
        {decisions.map((d) => {
          const expanded = open === d.query_id;
          return (
            <Fragment key={d.query_id}>
              <Tr className={expanded ? "border-b-0" : undefined}>
                <Td className="whitespace-nowrap text-muted">{formatDateTime(d.created_at)}</Td>
                <Td className="whitespace-nowrap">{d.user ?? "—"}</Td>
                <Td className="min-w-64">{d.question}</Td>
                <Td className="whitespace-nowrap">{outcomeLabel(d)}</Td>
                <Td className="text-right tabular-nums">{formatLatencyMs(d.latency_ms)}</Td>
                <Td className="text-right">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => setOpen(expanded ? null : d.query_id)}
                    className="-my-2 min-h-9 text-sm underline decoration-hairline underline-offset-4 hover:decoration-ink"
                  >
                    {expanded ? "Hide" : "Trace"}
                  </button>
                </Td>
              </Tr>
              {expanded ? (
                <Tr>
                  <Td colSpan={6} className="pb-5 pt-0">
                    <Trace d={d} />
                  </Td>
                </Tr>
              ) : null}
            </Fragment>
          );
        })}
      </tbody>
    </Table>
  );
}

function Trace({ d }: { d: AIDecision }) {
  const steps: [string, string][] = [
    [
      "1. Route",
      `${d.route}${d.route_reason ? ` — ${d.route_reason}` : ""}${d.route_source ? ` · decided by: ${SOURCE_LABEL[d.route_source] ?? d.route_source}` : ""}`,
    ],
    [
      "2. Search terms",
      [
        d.key_terms.length ? `key terms: ${d.key_terms.join(", ")}` : "",
        d.expansions.length ? `abbreviations expanded: ${d.expansions.join("; ")}` : "",
      ]
        .filter(Boolean)
        .join(" · ") || "—",
    ],
    ["3. Draft", d.generation_mode ? (MODE_LABEL[d.generation_mode] ?? d.generation_mode) : "not drafted"],
    [
      "4. Verification",
      d.claims
        ? `${String(d.supported)} of ${String(d.claims)} statements kept (judge: ${d.judge ?? "—"})`
        : "—",
    ],
    ["Cited", d.cited.length ? d.cited.join(", ") : "—"],
    [
      "Timings",
      Object.entries(d.timings_ms)
        .filter(([k]) => k in STAGE_LABEL)
        .map(([k, v]) => `${k} ${formatLatencyMs(v)}`)
        .join(" · ") || "—",
    ],
  ];
  return (
    <div className="space-y-4 rounded-sm bg-stone p-5 text-sm">
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-[10rem_1fr]">
        {steps.map(([term, value]) => (
          <Fragment key={term}>
            <dt className="mono-label pt-0.5 text-muted">{term}</dt>
            <dd>{value}</dd>
          </Fragment>
        ))}
      </dl>
      {d.dropped.length ? (
        <div>
          <p className="font-medium">Removed by the verifier (never shown to the clinician)</p>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {d.dropped.map((x, i) => (
              <li key={i}>
                “{x.claim}” <span className="text-muted">— {x.issue ?? "unsupported"}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
