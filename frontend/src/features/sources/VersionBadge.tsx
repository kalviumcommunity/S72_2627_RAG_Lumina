import { CalendarCheck } from "lucide-react";

import { Badge, type Tone } from "../../components/ui/Badge";
import { formatDate } from "../../lib/format";

const STATUS_TONE: Record<string, Tone> = {
  approved: "success",
  superseded: "amber",
  retired: "danger",
  draft: "neutral",
};

/** "v3 · effective 1 Nov 2025" — every citation shows which version and since when it applies. */
export function VersionBadge({
  version,
  effectiveFrom,
  status,
  current,
}: {
  version: string;
  effectiveFrom: string;
  status?: string;
  current?: boolean;
}) {
  const tone: Tone = status ? (STATUS_TONE[status] ?? "neutral") : "accent";
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <Badge tone={tone}>
        <CalendarCheck className="h-3 w-3" aria-hidden />v{version} · effective {formatDate(effectiveFrom)}
      </Badge>
      {status && status !== "approved" ? <Badge tone={tone}>{status}</Badge> : null}
      {current ? <Badge tone="success">Current version</Badge> : null}
    </span>
  );
}
