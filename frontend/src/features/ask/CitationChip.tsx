import { clsx } from "clsx";

import { Tooltip } from "../../components/ui/Tooltip";
import { sectionLabel } from "../../lib/format";
import type { Citation } from "../../lib/types";

/** Inline [S1] marker: shows which clause backs the sentence and opens it. */
export function CitationChip({
  marker,
  citation,
  onOpen,
}: {
  marker: string;
  citation: Citation | undefined;
  onOpen: (chunkId: string) => void;
}) {
  if (!citation) {
    return <span className="text-xs text-muted">[{marker}]</span>;
  }
  const label = `${citation.doc_code} ${sectionLabel(citation.section_path)}`;
  return (
    <Tooltip content={`${label} — ${citation.heading} (v${citation.version})`}>
      <button
        type="button"
        onClick={() => onOpen(citation.chunk_id)}
        aria-label={`Open source ${marker}: ${label}`}
        className={clsx(
          "mx-0.5 inline-flex min-h-6 translate-y-[-1px] items-center rounded-md border px-1.5 align-middle",
          "border-accent/30 bg-accent-soft font-mono text-[0.72rem] font-semibold text-accent-text",
          "hover:border-accent hover:bg-accent hover:text-accent-fg",
        )}
      >
        {marker}
      </button>
    </Tooltip>
  );
}
