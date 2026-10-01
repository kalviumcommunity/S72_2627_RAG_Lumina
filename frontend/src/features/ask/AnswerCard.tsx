import { ArrowUpRight } from "lucide-react";

import { Badge, TaxonomyChip, type Tone } from "../../components/ui/Badge";
import { RuleList } from "../../components/ui/Table";
import { parseAnswer } from "../../lib/answerText";
import { formatDate, sectionLabel } from "../../lib/format";
import type { Citation, QueryResponse } from "../../lib/types";
import { AbstainCard } from "./AbstainCard";
import { CitationChip } from "./CitationChip";
import { ConflictBanner } from "./ConflictBanner";
import { FeedbackButtons } from "./FeedbackDialog";
import { QuickCard } from "./QuickCard";

function status(response: QueryResponse): { label: string; tone: Tone } {
  if (response.outcome === "abstained" || !response.answer)
    return { label: "No answer given", tone: "neutral" };
  return response.outcome === "answered"
    ? { label: "Verified against sources", tone: "success" }
    : { label: "Partly verified", tone: "amber" };
}

/** The verified answer: cited text, key values, conflicts and the sources behind it. */
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
  const { label, tone } = status(response);

  return (
    <article className="rounded-md border border-hairline bg-canvas">
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-hairline px-5 py-3.5 sm:px-6">
        <Badge tone={tone}>{label}</Badge>
        {verification && answered ? (
          <span className="text-caption text-muted">
            {verification.supported} of {verification.claims} statements checked
            {removed > 0 ? ` · ${String(removed)} unsupported removed` : ""}
          </span>
        ) : null}
      </header>

      <div className="space-y-8 px-5 py-6 sm:px-6">
        {response.pii_redacted ? (
          <p className="rounded-sm bg-stone px-4 py-3 text-caption">
            <span className="mono-label mr-2 text-muted">Identifiers removed</span>
            Patient identifiers were removed before the question was processed or logged:{" "}
            <span className="font-medium">“{response.redacted_question}”</span>
          </p>
        ) : null}

        <ConflictBanner conflicts={response.conflicts} onOpen={onOpenSource} />

        {answered && response.answer ? (
          <div className="space-y-3 text-lead leading-relaxed" data-testid="answer-text">
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

      <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-hairline px-5 py-3 sm:px-6">
        <p className="text-micro text-muted">{response.disclaimer}</p>
        {response.outcome !== "abstained" || response.escalation?.reason === "not_found" ? (
          <FeedbackButtons queryId={response.query_id} />
        ) : null}
      </footer>
    </article>
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
  if (lines.some((l) => l.bullet)) {
    return (
      <ul className="list-disc space-y-2 pl-5">
        {lines.map((line, i) => (
          <li key={i}>{render(line)}</li>
        ))}
      </ul>
    );
  }
  return (
    <>
      {lines.map((line, i) => (
        <p key={i}>{render(line)}</p>
      ))}
    </>
  );
}

function CitationList({ citations, onOpen }: { citations: Citation[]; onOpen: (chunkId: string) => void }) {
  return (
    <section aria-label="Sources cited">
      <h3 className="mono-label mb-2 text-ink">Sources cited</h3>
      <RuleList>
        {citations.map((c) => (
          <li key={c.marker}>
            <button
              type="button"
              onClick={() => onOpen(c.chunk_id)}
              className="group grid w-full grid-cols-[2.5rem_1fr_auto] items-start gap-x-3 py-3.5 text-left"
            >
              <span className="mono-label pt-0.5 text-ink">[{c.marker}]</span>
              <span className="min-w-0">
                <span className="block">
                  <span className="font-medium">
                    {c.doc_code} {sectionLabel(c.section_path)}
                  </span>{" "}
                  <span className="text-muted">— {c.heading}</span>
                </span>
                <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-micro text-muted">
                  <span>{c.title}</span>
                  <span>
                    v{c.version} · effective {formatDate(c.effective_from)}
                  </span>
                  {c.amends.map((a) => (
                    <TaxonomyChip key={`${a.doc_code}-${a.section_path ?? "all"}`}>
                      Amends {a.doc_code}
                      {a.section_path ? ` ${sectionLabel(a.section_path)}` : ""}
                    </TaxonomyChip>
                  ))}
                  {c.branch_specific ? <Badge tone="accent">Local to your branch</Badge> : null}
                </span>
              </span>
              <ArrowUpRight className="h-4 w-4 text-muted group-hover:text-ink" aria-hidden />
            </button>
          </li>
        ))}
      </RuleList>
    </section>
  );
}
