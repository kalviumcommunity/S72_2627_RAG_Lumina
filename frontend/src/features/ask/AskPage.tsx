import { ArrowRight } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useDocumentTitle } from "../../app/layout/useDocumentTitle";
import { useAuth } from "../../app/providers";
import { TaxonomyChip } from "../../components/ui/Badge";
import { RuleList } from "../../components/ui/Table";
import { RecentQuestions } from "../history/RecentQuestions";
import { SourceSheet } from "../sources/SourceSheet";
import { AnswerCard } from "./AnswerCard";
import { EXAMPLES } from "./examples";
import { QuestionInput, type QuestionInputHandle } from "./QuestionInput";
import { StreamProgress } from "./StreamProgress";
import { useAskStream, type Exchange } from "./useAskStream";

/** Everyone's first page: ask a question, read the verified answer, open the cited clause. */
export function AskPage() {
  useDocumentTitle("Ask");
  const { session } = useAuth();
  const [question, setQuestion] = useState("");
  const [openChunk, setOpenChunk] = useState<string | null>(null);
  const input = useRef<QuestionInputHandle>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const { exchanges, ask, cancel, busy } = useAskStream(session?.user.branch?.id ?? null);

  const submit = (text = question) => {
    if (!text.trim() || busy) return;
    setQuestion("");
    void ask(text);
  };

  useEffect(() => {
    // Only follow the conversation; on first load the page title must stay in view (phones).
    if (exchanges.length) bottom.current?.scrollIntoView({ block: "end" });
  }, [exchanges]);

  return (
    <div className="flex min-h-full flex-col">
      <div className="mx-auto w-full max-w-4xl flex-1 px-4 pb-10 pt-12 sm:px-6 sm:pt-16">
        {exchanges.length === 0 ? (
          <Welcome onPick={submit} branch={session?.user.branch?.name} />
        ) : (
          <div className="space-y-10">
            {exchanges.map((exchange) => (
              <ExchangeView
                key={exchange.id}
                exchange={exchange}
                onOpenSource={setOpenChunk}
                onRefine={() => {
                  setQuestion(`${exchange.question} — `);
                  input.current?.focus();
                }}
              />
            ))}
          </div>
        )}
        <div ref={bottom} />
      </div>

      <div className="sticky bottom-0 z-20 border-t border-hairline bg-canvas/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur sm:px-6">
        <div className="mx-auto max-w-4xl">
          <QuestionInput
            ref={input}
            value={question}
            onChange={setQuestion}
            onSubmit={() => submit()}
            onCancel={cancel}
            busy={busy}
          />
          <p id="question-hint" className="mt-2 px-1 text-micro text-muted">
            Answers come only from approved, current documents. Do not type patient names or IDs — they are
            removed automatically.
          </p>
        </div>
      </div>

      <SourceSheet chunkId={openChunk} onClose={() => setOpenChunk(null)} />
    </div>
  );
}

function Welcome({ onPick, branch }: { onPick: (q: string) => void; branch?: string }) {
  return (
    <div>
      <p className="mono-label text-muted">Ask{branch ? ` · ${branch}` : ""}</p>
      <h1 className="mt-4 text-display">Ask the approved protocols</h1>
      <p className="mt-5 max-w-2xl text-lead text-muted">
        Every sentence links to the exact clause it came from. If no approved document covers your question,
        you get the right person to call instead of a guess.
      </p>

      <section aria-label="Example questions" className="mt-14">
        <h2 className="mono-label mb-3 text-ink">Try an example</h2>
        <RuleList>
          {EXAMPLES.map((ex) => (
            <li key={ex.question}>
              <button
                type="button"
                onClick={() => onPick(ex.question)}
                className="group grid w-full grid-cols-[1fr_auto] items-center gap-x-6 gap-y-2 py-4 text-left sm:grid-cols-[1fr_8rem_1.25rem]"
              >
                <span>
                  <span className="block text-lg leading-snug">{ex.question}</span>
                  <span className="mt-0.5 block text-caption text-muted">{ex.shows}</span>
                </span>
                <span className="justify-self-end sm:justify-self-start">
                  <TaxonomyChip>{ex.tag}</TaxonomyChip>
                </span>
                <ArrowRight
                  className="hidden h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink sm:block"
                  aria-hidden
                />
              </button>
            </li>
          ))}
        </RuleList>
      </section>

      <div className="mt-14">
        <RecentQuestions onPick={onPick} />
      </div>
    </div>
  );
}

function ExchangeView({
  exchange,
  onOpenSource,
  onRefine,
}: {
  exchange: Exchange;
  onOpenSource: (chunkId: string) => void;
  onRefine: () => void;
}) {
  const inFlight = ["routing", "retrieving", "verifying"].includes(exchange.stage);
  const shownQuestion = exchange.route?.pii_redacted ? exchange.route.redacted_question : exchange.question;
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <p className="max-w-[85%] rounded-md bg-stone px-5 py-3 text-lead" data-testid="question">
          {shownQuestion}
        </p>
      </div>
      {inFlight ? <StreamProgress stage={exchange.stage} /> : null}
      {exchange.response ? (
        <AnswerCard response={exchange.response} onOpenSource={onOpenSource} onRefine={onRefine} />
      ) : null}
      {exchange.stage === "error" ? (
        <div role="alert" className="rounded-md border border-error bg-error-wash p-5">
          <p className="mono-label text-error">Error</p>
          <p className="mt-1 font-medium">No answer — nothing unverified was shown</p>
          <p className="mt-1 text-sm">{exchange.error}</p>
        </div>
      ) : null}
      {exchange.stage === "cancelled" ? <p className="text-caption text-muted">Stopped.</p> : null}
    </div>
  );
}
