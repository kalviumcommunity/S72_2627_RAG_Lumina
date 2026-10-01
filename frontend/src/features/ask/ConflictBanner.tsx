import { formatDate, sectionLabel } from "../../lib/format";
import type { ConflictInfo, ConflictSide } from "../../lib/types";

/** Two approved documents disagree: both values are shown; Lumina never picks one clinically. */
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
      className="rounded-md border border-coral bg-coral-wash p-5"
    >
      <p className="mono-label text-coral-ink">Conflict</p>
      <p className="mt-2 text-feature">Approved documents disagree</p>
      <p className="mt-1 text-sm">
        Both values are shown with their sources. Lumina does not choose between them — follow local
        escalation if unsure.
      </p>
      {conflicts.map((conflict, index) => (
        <div key={conflict.id ?? index} className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">
          <Side side={conflict.a} newer={conflict.newer === "a"} onOpen={onOpen} />
          <Side side={conflict.b} newer={conflict.newer === "b"} onOpen={onOpen} />
          {conflict.flagged_to_owner ? (
            <p className="text-micro text-muted md:col-span-2">
              Flagged to the document owner for resolution.
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
      className="flex flex-col gap-1.5 rounded-sm border border-coral-soft bg-canvas p-4 text-left transition-colors hover:border-primary"
    >
      <span className="flex flex-wrap items-center gap-2 text-sm font-medium">
        {side.marker ? <span className="mono-label text-ink">[{side.marker}]</span> : null}
        {side.doc_code} {sectionLabel(side.section_path)}
        {newer ? (
          <span className="rounded-xs bg-primary px-1.5 py-0.5 text-xs text-white">More recent</span>
        ) : null}
      </span>
      <span className="text-micro text-muted">
        v{side.version} · effective {formatDate(side.effective_from)}
      </span>
      <span className="line-clamp-3 text-sm">{side.snippet}</span>
    </button>
  );
}
