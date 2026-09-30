import { Badge, type Tone } from "../../components/ui/Badge";
import type { VersionStatus } from "../../lib/types";

const STATUS: Record<VersionStatus, { label: string; tone: Tone }> = {
  draft: { label: "Draft", tone: "accent" },
  approved: { label: "Approved", tone: "success" },
  superseded: { label: "Superseded", tone: "amber" },
  retired: { label: "Retired", tone: "danger" },
};

export function StatusBadge({ status }: { status: VersionStatus }) {
  const s = STATUS[status];
  return <Badge tone={s.tone}>{s.label}</Badge>;
}
