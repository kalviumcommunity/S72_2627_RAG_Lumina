import { ArrowUpRight, Flag, TriangleAlert } from "lucide-react";

import { Badge } from "../../components/ui/Badge";
import { formatDate, sectionLabel } from "../../lib/format";
import type { ConflictInfo, ConflictSide } from "../../lib/types";

/** Amber banner: two approved documents disagree. Shows both values; never picks one clinically. */
export function ConflictBanner({
  conflicts,
  onOpen,
}: {
  conflicts: ConflictInfo[];
  onOpen: (chunkId: string) => void;
}) {
  if (!conflicts.length) return null;
  return (
    <section
      role="alert"
      aria-label="Conflicting sources"
      className="rounded-2xl border border-amber-border bg-amber-soft p-4"
    >
      <div className="flex items-center gap-2 font-semibold text-amber">
        <TriangleAlert className="h-5 w-5 shrink-0" aria-hidden />
        Approved documents disagree
      </div>
      <p className="mt-1 text-sm">
        Both values are shown with their sources. ProtoCite does not choose between them — follow local
        escalation if unsure.
      </p>
      {conflicts.map((conflict, index) => (
        <div key={conflict.id ?? index} className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
          <Side side={conflict.a} newer={conflict.newer === "a"} onOpen={onOpen} />
          <Side side={conflict.b} newer={conflict.newer === "b"} onOpen={onOpen} />
          {conflict.flagged_to_owner ? (
            <p className="flex items-center gap-1.5 text-xs text-muted md:col-span-2">
              <Flag className="h-3.5 w-3.5" aria-hidden /> Flagged to the document owner for resolution.
            </p>
          ) : null}
        </div>
      ))}
    </section>
  );
}

function Side({ side, newer, onOpen }: { side: ConflictSide; newer: boolean; onOpen: (id: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onOpen(side.chunk_id)}
      className="flex flex-col gap-1 rounded-xl border border-amber-border bg-surface p-3 text-left hover:border-amber"
    >
      <span className="flex flex-wrap items-center gap-1.5 text-sm font-semibold">
        {side.marker ? <span className="font-mono text-xs text-accent-text">[{side.marker}]</span> : null}
        {side.doc_code} {sectionLabel(side.section_path)}
        {newer ? <Badge tone="amber">More recent</Badge> : null}
        <ArrowUpRight className="ml-auto h-4 w-4 text-muted" aria-hidden />
      </span>
      <span className="text-xs text-muted">
        v{side.version} · effective {formatDate(side.effective_from)}
      </span>
      <span className="line-clamp-3 text-sm">{side.snippet}</span>
    </button>
  );
}
