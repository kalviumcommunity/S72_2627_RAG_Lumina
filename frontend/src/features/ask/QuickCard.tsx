import type { Citation, QuickValue } from "../../lib/types";

/** Key values (dose / time / threshold) on warm stone cards — each opens the clause it came from. */
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
      <h3 className="mono-label mb-2 text-ink">Key values</h3>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {values.map((qv, index) => {
          const citation = byMarker.get(qv.source);
          return (
            <button
              key={`${qv.label}-${String(index)}`}
              type="button"
              disabled={!citation}
              onClick={() => citation && onOpen(citation.chunk_id)}
              className="flex flex-col items-start rounded-sm bg-stone px-4 py-3.5 text-left transition-colors hover:bg-stone-hover disabled:cursor-default disabled:hover:bg-stone"
            >
              <span className="text-micro text-muted">{qv.label}</span>
              <span className="mt-1 flex w-full items-baseline justify-between gap-3">
                {/* Short values (doses, times) read as figures; long notes drop to body size. */}
                <span className={qv.value.length > 28 ? "text-base" : "text-feature"}>{qv.value}</span>
                {citation ? (
                  <span className="mono-label shrink-0 text-muted">
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
