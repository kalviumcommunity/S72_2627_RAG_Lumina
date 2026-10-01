import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ShieldCheck, X } from "lucide-react";
import { useState } from "react";

import { Page, PageHeader } from "../../app/layout/Page";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Textarea } from "../../components/ui/Field";
import { Segmented } from "../../components/ui/Segmented";
import { Skeleton } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { formatDate, percent, relativeTime, sectionLabel } from "../../lib/format";
import { queries, queryKeys } from "../../lib/queries";
import type { AdminConflict } from "../../lib/types";

type Status = AdminConflict["status"];
const TONE: Record<Status, Tone> = { open: "amber", resolved: "success", dismissed: "neutral" };
const FOUND_BY: Record<string, string | undefined> = {
  query: "while answering a question",
  ingest: "when the document was approved",
  user: "by a user",
};

/** Contradictions between current documents (found at ingest or while answering) for owners to fix. */
export function ConflictsPage() {
  const [show, setShow] = useState<"open" | "all">("open");
  const [acting, setActing] = useState<{ conflict: AdminConflict; status: Status } | null>(null);
  const conflicts = useQuery(queries.conflicts(show));

  return (
    <Page title="Conflicts">
      <PageHeader
        eyebrow="Review"
        title="Conflicts"
        description="Two current documents giving different values for the same step. Clinicians see both values with a warning until the owner resolves it."
        actions={
          <Segmented
            label="Show"
            value={show}
            onChange={setShow}
            options={[
              ["open", "Open"],
              ["all", "All"],
            ]}
          />
        }
      />
      {conflicts.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : conflicts.isError ? (
        <ErrorNotice message={errorMessage(conflicts.error)} />
      ) : !conflicts.data?.length ? (
        <EmptyState icon={<ShieldCheck className="h-6 w-6" />} title="No open conflicts">
          Current documents agree with each other on the values checked.
        </EmptyState>
      ) : (
        <ul className="space-y-6">
          {conflicts.data.map((c) => (
            <li key={c.id}>
              <ConflictCard conflict={c} onAct={(status) => setActing({ conflict: c, status })} />
            </li>
          ))}
        </ul>
      )}
      {acting ? <ResolveDialog key={acting.conflict.id} {...acting} onClose={() => setActing(null)} /> : null}
    </Page>
  );
}

/** A conflict read like a comparison table: the claim, then both clauses side by side. */
function ConflictCard({ conflict: c, onAct }: { conflict: AdminConflict; onAct: (status: Status) => void }) {
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-3xl space-y-2">
          <p className="flex flex-wrap items-center gap-3">
            <span className="text-sm font-medium">
              {c.a.doc_code} {sectionLabel(c.a.section_path)} · {c.b.doc_code}{" "}
              {sectionLabel(c.b.section_path)}
            </span>
            <Badge tone={TONE[c.status]}>{c.status}</Badge>
          </p>
          <p className="text-lg leading-snug">{c.description}</p>
          <p className="text-caption text-muted">
            Found {FOUND_BY[c.detected_by] ?? "by a user"} {relativeTime(c.created_at)}
            {c.confidence !== null ? ` · confidence ${percent(c.confidence)}` : ""}
            {c.owner ? ` · owner ${c.owner}` : ""}
          </p>
        </div>
        {c.status === "open" ? (
          <div className="flex items-center gap-4">
            <Button size="sm" onClick={() => onAct("resolved")}>
              <Check className="h-4 w-4" /> Resolve
            </Button>
            <Button variant="link" size="sm" onClick={() => onAct("dismissed")}>
              <X className="h-4 w-4" /> Dismiss
            </Button>
          </div>
        ) : null}
      </div>
      <div className="mt-6 grid gap-4 md:grid-cols-2">
        {[c.a, c.b].map((side, i) => (
          <div key={side.chunk_id} className="rounded-sm bg-stone p-5">
            <p className="mono-label text-muted">Source {i === 0 ? "A" : "B"}</p>
            <p className="mt-2 font-medium">
              {side.doc_code} v{side.version} {sectionLabel(side.section_path)}
            </p>
            <p className="text-micro text-muted">
              {side.title} · effective {formatDate(side.effective_from)}
            </p>
            <p className="mt-3 whitespace-pre-line text-sm">{side.text}</p>
          </div>
        ))}
      </div>
      {c.resolution_note ? (
        <p className="mt-5 border-t border-hairline pt-4 text-caption">
          <span className="mono-label mr-2 text-muted">Resolution</span>
          {c.resolution_note}
        </p>
      ) : null}
    </Card>
  );
}

function ResolveDialog({
  conflict,
  status,
  onClose,
}: {
  conflict: AdminConflict;
  status: Status;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () =>
      api.patch<AdminConflict>(`/conflicts/${conflict.id}`, { status, resolution_note: note.trim() || null }),
    onSuccess: () => {
      notify(status === "resolved" ? "Conflict resolved" : "Conflict dismissed");
      void queryClient.invalidateQueries({ queryKey: queryKeys.conflicts });
      onClose();
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={status === "resolved" ? "Resolve conflict" : "Dismiss conflict"}
      description={
        status === "resolved"
          ? "Describe what was changed (e.g. which document will be amended). This is kept in the audit log."
          : "Explain why this is not a real conflict (e.g. different patient groups)."
      }
    >
      <form
        className="space-y-5"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <Field label="Note">
          {(props) => (
            <Textarea {...props} rows={3} required value={note} onChange={(e) => setNote(e.target.value)} />
          )}
        </Field>
        {save.error ? <ErrorNotice message={errorMessage(save.error)} /> : null}
        <div className="flex items-center justify-end gap-4">
          <Button variant="link" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending} disabled={!note.trim()}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
