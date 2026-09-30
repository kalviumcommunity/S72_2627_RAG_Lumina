import { clsx } from "clsx";
import { ArrowUpRight, BadgeCheck, EyeOff, GitMerge, MapPin, Quote, Timer } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { parseAnswer } from "../../lib/answerText";
import { formatLatencyMs, sectionLabel } from "../../lib/format";
import type { Citation, QueryResponse } from "../../lib/types";
import { VersionBadge } from "../sources/VersionBadge";
import { AbstainCard } from "./AbstainCard";
import { CitationChip } from "./CitationChip";
import { ConflictBanner } from "./ConflictBanner";
import { FeedbackButtons } from "./FeedbackDialog";
import { QuickCard } from "./QuickCard";

/** The verified answer: action-first text with citation chips, key values, conflicts, sources. */
export function AnswerCard({
  response,
  onOpenSource,
  onRefine,
}: {
  response: QueryResponse;
  onOpenSource: (chunkId: string) => void;
  onRefine?: () => void;
}) {
  const byMarker = new Map(response.citations.map((c) => [c.marker, c]));
  const answered = response.outcome !== "abstained" && response.answer;
  const verification = response.verification;
  const removed = verification ? verification.claims - verification.supported : 0;

  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface-2 px-4 py-2.5 text-sm">
        {answered ? (
          <Badge tone={response.outcome === "answered" ? "success" : "amber"}>
            <BadgeCheck className="h-3.5 w-3.5" aria-hidden />
            {response.outcome === "answered" ? "Verified against sources" : "Partly verified"}
          </Badge>
        ) : (
          <Badge tone={response.escalation?.reason === "high_risk" ? "danger" : "neutral"}>
            No answer given
          </Badge>
        )}
        {verification && answered ? (
          <span className="text-muted">
            {verification.supported} of {verification.claims} statements checked
            {removed > 0 ? ` · ${String(removed)} unsupported removed` : ""}
          </span>
        ) : null}
        {response.generation_mode === "extractive" && answered ? (
          <Badge tone="neutral">
            <Quote className="h-3 w-3" aria-hidden /> Quoted directly from the source
          </Badge>
        ) : null}
        <span className="ml-auto flex items-center gap-1 text-muted">
          <Timer className="h-3.5 w-3.5" aria-hidden />
          {formatLatencyMs(response.latency_ms)}
        </span>
      </div>

      <div className="space-y-4 p-4 sm:p-5">
        {response.pii_redacted ? (
          <p className="flex items-start gap-2 rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-muted">
            <EyeOff className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            Patient identifiers were removed before the question was processed or logged:
            <span className="font-medium text-text">“{response.redacted_question}”</span>
          </p>
        ) : null}

        <ConflictBanner conflicts={response.conflicts} onOpen={onOpenSource} />

        {answered && response.answer ? (
          <div className="space-y-2 text-[1.02rem] leading-relaxed" data-testid="answer-text">
            <AnswerBody answer={response.answer} byMarker={byMarker} onOpen={onOpenSource} />
          </div>
        ) : response.escalation ? (
          <AbstainCard escalation={response.escalation} onRefine={onRefine} />
        ) : null}

        <QuickCard values={response.quick_values} citations={response.citations} onOpen={onOpenSource} />

        {response.citations.length ? (
          <CitationList citations={response.citations} onOpen={onOpenSource} />
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2">
        <p className="text-xs text-muted">{response.disclaimer}</p>
        {response.outcome !== "abstained" || response.escalation?.reason === "not_found" ? (
          <FeedbackButtons queryId={response.query_id} />
        ) : null}
      </div>
    </Card>
  );
}

function AnswerBody({
  answer,
  byMarker,
  onOpen,
}: {
  answer: string;
  byMarker: Map<string, Citation>;
  onOpen: (chunkId: string) => void;
}) {
  const lines = parseAnswer(answer);
  const render = (line: (typeof lines)[number]) =>
    line.segments.map((seg, i) =>
      seg.kind === "text" ? (
        <span key={i}>{seg.text}</span>
      ) : (
        <CitationChip key={i} marker={seg.marker} citation={byMarker.get(seg.marker)} onOpen={onOpen} />
      ),
    );
  const bullets = lines.filter((l) => l.bullet);
  if (bullets.length === lines.length) {
    return (
      <ul className="list-disc space-y-1 pl-5">
        {lines.map((line, i) => (
          <li key={i}>{render(line)}</li>
        ))}
      </ul>
    );
  }
  return (
    <>
      {lines.map((line, i) => (
        <p key={i} className={clsx(line.bullet && "pl-4 before:-ml-4 before:mr-2 before:content-['•']")}>
          {render(line)}
        </p>
      ))}
    </>
  );
}

function CitationList({ citations, onOpen }: { citations: Citation[]; onOpen: (chunkId: string) => void }) {
  return (
    <section aria-label="Sources cited">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Sources cited</h3>
      <ul className="space-y-2">
        {citations.map((c) => (
          <li key={c.marker}>
            <button
              type="button"
              onClick={() => onOpen(c.chunk_id)}
              className="group flex w-full flex-col gap-1.5 rounded-xl border border-border bg-surface p-3 text-left hover:border-accent"
            >
              <span className="flex flex-wrap items-center gap-2">
                <span className="rounded-md bg-accent-soft px-1.5 font-mono text-xs font-semibold text-accent-text">
                  {c.marker}
                </span>
                <span className="font-semibold">
                  {c.doc_code} {sectionLabel(c.section_path)}
                </span>
                <span className="text-sm text-muted">{c.heading}</span>
                <ArrowUpRight className="ml-auto h-4 w-4 text-muted group-hover:text-accent" aria-hidden />
              </span>
              <span className="text-sm text-muted">{c.title}</span>
              <span className="flex flex-wrap items-center gap-1.5">
                <VersionBadge version={c.version} effectiveFrom={c.effective_from} />
                {c.amends.map((a) => (
                  <Badge key={`${a.doc_code}-${a.section_path ?? "all"}`} tone="amber">
                    <GitMerge className="h-3 w-3" aria-hidden />
                    Amends {a.doc_code}
                    {a.section_path ? ` ${sectionLabel(a.section_path)}` : ""}
                  </Badge>
                ))}
                {c.branch_specific ? (
                  <Badge tone="accent">
                    <MapPin className="h-3 w-3" aria-hidden /> Local to your branch
                  </Badge>
                ) : null}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
