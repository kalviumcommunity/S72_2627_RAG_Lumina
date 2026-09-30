import type { Citation, QuickValue } from "../../lib/types";

/** Key values (dose / time / threshold) — each one opens the clause it was copied from. */
export function QuickCard({
  values,
  citations,
  onOpen,
}: {
  values: QuickValue[];
  citations: Citation[];
  onOpen: (chunkId: string) => void;
}) {
  if (!values.length) return null;
  const byMarker = new Map(citations.map((c) => [c.marker, c]));
  return (
    <section aria-label="Key values">
      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Key values</h3>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {values.map((qv, index) => {
          const citation = byMarker.get(qv.source);
          return (
            <button
              key={`${qv.label}-${String(index)}`}
              type="button"
              disabled={!citation}
              onClick={() => citation && onOpen(citation.chunk_id)}
              className="flex min-h-11 flex-col items-start rounded-xl border border-border bg-surface-2 px-3 py-2 text-left hover:border-accent disabled:cursor-default disabled:hover:border-border"
            >
              <span className="text-xs text-muted">{qv.label}</span>
              <span className="flex w-full items-baseline justify-between gap-2">
                <span className="font-semibold">{qv.value}</span>
                {citation ? (
                  <span className="shrink-0 font-mono text-[0.7rem] text-accent-text">
                    {qv.source} · {citation.doc_code}
                  </span>
                ) : null}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
