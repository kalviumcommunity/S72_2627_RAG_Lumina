import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";

import { Skeleton } from "../../components/ui/Skeleton";
import { api } from "../../lib/api";
import { relativeTime } from "../../lib/format";
import type { HistoryItem } from "../../lib/types";

const OUTCOME_LABEL: Record<string, string> = {
  answered: "answered",
  partial: "partly answered",
  abstained: "escalated",
};

/** Your recent questions — stored on the server only in redacted form (no identifiers). */
export function RecentQuestions({ onPick }: { onPick: (question: string) => void }) {
  const history = useQuery({
    queryKey: ["query-history"],
    queryFn: () => api.get<HistoryItem[]>("/query/history", { limit: 8 }),
  });
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
      <h2 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
        <History className="h-3.5 w-3.5" aria-hidden /> Your recent questions
      </h2>
      <ul className="space-y-1.5">
        {items.map((item) => (
          <li key={item.query_id}>
            <button
              type="button"
              onClick={() => onPick(item.question)}
              className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-border bg-surface px-3 py-2 text-left text-sm hover:border-accent"
            >
              <span className="line-clamp-2">{item.question}</span>
              <span className="shrink-0 text-xs text-muted">
                {item.outcome ? OUTCOME_LABEL[item.outcome] : item.route} · {relativeTime(item.created_at)}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
