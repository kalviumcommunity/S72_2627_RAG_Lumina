import { motion, useReducedMotion } from "motion/react";
import { AlertTriangle, BookMarked, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useAuth } from "../../app/providers";
import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { RecentQuestions } from "../history/RecentQuestions";
import { SourceSheet } from "../sources/SourceSheet";
import { AnswerCard } from "./AnswerCard";
import { EXAMPLES } from "./examples";
import { QuestionInput, type QuestionInputHandle } from "./QuestionInput";
import { SourceCards, StreamProgress } from "./StreamProgress";
import { useAskStream, type Exchange } from "./useAskStream";

export function AskPage() {
  const { session, config } = useAuth();
  const [question, setQuestion] = useState("");
  const [openChunk, setOpenChunk] = useState<string | null>(null);
  const input = useRef<QuestionInputHandle>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const { exchanges, ask, cancel, busy } = useAskStream(session?.user.branch?.id ?? null);
  const reduceMotion = useReducedMotion();

  const submit = (text = question) => {
    if (!text.trim() || busy) return;
    setQuestion("");
    void ask(text);
  };

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end", behavior: reduceMotion ? "auto" : "smooth" });
  }, [exchanges, reduceMotion]);

  return (
    <div className="flex min-h-full flex-col">
      <div className="mx-auto w-full max-w-3xl flex-1 space-y-5 px-4 pb-6 pt-5">
        {exchanges.length === 0 ? (
          <Welcome
            onPick={submit}
            branch={session?.user.branch?.name}
            llm={config?.llm_provider === "none" ? null : (config?.llm_model ?? null)}
          />
        ) : (
          exchanges.map((exchange) => (
            <motion.div
              key={exchange.id}
              initial={reduceMotion ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2 }}
            >
              <ExchangeView
                exchange={exchange}
                onOpenSource={setOpenChunk}
                onRefine={() => {
                  setQuestion(`${exchange.question} — `);
                  input.current?.focus();
                }}
              />
            </motion.div>
          ))
        )}
        <div ref={bottom} />
      </div>

      <div className="sticky bottom-0 z-20 border-t border-border bg-bg/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur">
        <div className="mx-auto max-w-3xl">
          <QuestionInput
            ref={input}
            value={question}
            onChange={setQuestion}
            onSubmit={() => submit()}
            onCancel={cancel}
            busy={busy}
          />
          <p id="question-hint" className="mt-1.5 px-1 text-xs text-muted">
            Answers come only from approved, current documents. Don't type patient names or IDs — they are
            removed automatically.
          </p>
        </div>
      </div>

      <SourceSheet chunkId={openChunk} onClose={() => setOpenChunk(null)} />
    </div>
  );
}

function Welcome({
  onPick,
  branch,
  llm,
}: {
  onPick: (q: string) => void;
  branch?: string;
  llm: string | null;
}) {
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent-text">
            <BookMarked className="h-5 w-5" aria-hidden />
          </span>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Ask the approved protocols</h1>
            <p className="mt-1 text-sm text-muted">
              Every statement is checked against the exact clause it cites, with version and effective date.
              If no approved document answers, you get the right person to call instead.
            </p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {branch ? <Badge tone="accent">Showing documents for {branch}</Badge> : null}
              <Badge>
                <Sparkles className="h-3 w-3" aria-hidden />{" "}
                {llm ? `AI drafting: ${llm.split(",")[0] ?? llm}` : "Verbatim mode"}
              </Badge>
            </div>
          </div>
        </div>
      </Card>

      <section aria-label="Example questions">
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Try an example</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {EXAMPLES.map((ex) => (
            <button
              key={ex.question}
              type="button"
              onClick={() => onPick(ex.question)}
              className="flex min-h-11 flex-col items-start rounded-xl border border-border bg-surface px-3 py-2.5 text-left hover:border-accent hover:bg-accent-soft/40"
            >
              <span className="text-sm font-medium">{ex.question}</span>
              <span className="mt-0.5 text-xs text-muted">{ex.shows}</span>
            </button>
          ))}
        </div>
      </section>

      <RecentQuestions onPick={onPick} />
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
    <div className="space-y-3">
      <div className="flex justify-end">
        <p
          className="max-w-[85%] rounded-2xl rounded-br-md bg-accent px-4 py-2.5 text-accent-fg"
          data-testid="question"
        >
          {shownQuestion}
        </p>
      </div>
      {inFlight ? (
        <Card className="space-y-3 p-4">
          <StreamProgress stage={exchange.stage} />
          {exchange.route?.route === "answer" ? (
            <SourceCards
              sources={exchange.sources}
              loading={exchange.stage === "retrieving"}
              onOpen={onOpenSource}
            />
          ) : null}
        </Card>
      ) : null}
      {exchange.response ? (
        <AnswerCard response={exchange.response} onOpenSource={onOpenSource} onRefine={onRefine} />
      ) : null}
      {exchange.stage === "error" ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-2xl border border-danger-border bg-danger-soft p-4 text-sm"
        >
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden />
          <div>
            <p className="font-medium text-danger">No answer — nothing unverified was shown</p>
            <p className="text-text">{exchange.error}</p>
          </div>
        </div>
      ) : null}
      {exchange.stage === "cancelled" ? <p className="text-sm text-muted">Stopped.</p> : null}
    </div>
  );
}
