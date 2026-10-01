import { useQuery } from "@tanstack/react-query";

import { Skeleton } from "../../components/ui/Skeleton";
import { RuleList } from "../../components/ui/Table";
import { relativeTime } from "../../lib/format";
import { queries } from "../../lib/queries";

const OUTCOME_LABEL: Record<string, string> = {
  answered: "answered",
  partial: "partly answered",
  abstained: "escalated",
};

/** Your recent questions — stored on the server only in redacted form (no identifiers). */
export function RecentQuestions({ onPick }: { onPick: (question: string) => void }) {
  const history = useQuery(queries.history(5));
  if (history.isLoading) {
    return (
      <div className="space-y-2" aria-hidden>
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-5/6" />
      </div>
    );
  }
  const items = history.data ?? [];
  if (!items.length) return null;
  return (
    <section aria-label="Recent questions">
      <h2 className="mono-label mb-3 text-ink">Your recent questions</h2>
      <RuleList>
        {items.map((item) => (
          <li key={item.query_id}>
            <button
              type="button"
              onClick={() => onPick(item.question)}
              className="flex w-full items-baseline justify-between gap-4 py-3 text-left hover:text-black"
            >
              <span className="line-clamp-2">{item.question}</span>
              <span className="mono-label shrink-0 text-muted">
                {item.outcome ? OUTCOME_LABEL[item.outcome] : item.route} · {relativeTime(item.created_at)}
              </span>
            </button>
          </li>
        ))}
      </RuleList>
    </section>
  );
}
