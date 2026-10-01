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
    return <span className="font-mono text-xs text-muted">[{marker}]</span>;
  }
  const label = `${citation.doc_code} ${sectionLabel(citation.section_path)}`;
  return (
    <Tooltip content={`${label} — ${citation.heading} (v${citation.version})`}>
      <button
        type="button"
        onClick={() => onOpen(citation.chunk_id)}
        aria-label={`Open source ${marker}: ${label}`}
        className="mx-0.5 inline-flex min-h-6 translate-y-[-2px] items-center rounded-xs border border-primary px-1.5 align-middle font-mono text-[0.7rem] transition-colors hover:bg-primary hover:text-white"
      >
        {marker}
      </button>
    </Tooltip>
  );
}
