import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { CheckCircle2, ShieldCheck, TriangleAlert, XCircle } from "lucide-react";
import { useState } from "react";

import { AdminPage, PageHeader } from "../../app/layout/AppShell";
import { Badge, type Tone } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Textarea } from "../../components/ui/Field";
import { Skeleton } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { formatDate, percent, relativeTime, sectionLabel } from "../../lib/format";
import type { AdminConflict } from "../../lib/types";

type Status = AdminConflict["status"];
const TONE: Record<Status, Tone> = { open: "amber", resolved: "success", dismissed: "neutral" };

/** Contradictions between current documents (found at ingest or while answering) for owners to fix. */
export function ConflictsPage() {
  const [show, setShow] = useState<"open" | "all">("open");
  const [acting, setActing] = useState<{ conflict: AdminConflict; status: Status } | null>(null);
  const conflicts = useQuery({
    queryKey: ["conflicts", show],
    queryFn: () => api.get<AdminConflict[]>("/conflicts", show === "open" ? { status: "open" } : undefined),
  });

  return (
    <AdminPage>
      <PageHeader
        title="Conflicts"
        description="Two current documents giving different values for the same step. Clinicians see both values with a warning until the owner resolves it."
        actions={
          <div className="flex gap-1 rounded-xl border border-border bg-surface-2 p-1">
            {(["open", "all"] as const).map((value) => (
              <button
                key={value}
                type="button"
                aria-pressed={show === value}
                onClick={() => setShow(value)}
                className={clsx(
                  "min-h-9 rounded-lg px-3 text-sm",
                  show === value ? "bg-surface font-medium shadow-card" : "text-muted",
                )}
              >
                {value === "open" ? "Open" : "All"}
              </button>
            ))}
          </div>
        }
      />
      {conflicts.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : conflicts.isError ? (
        <ErrorNotice message={errorMessage(conflicts.error)} />
      ) : !conflicts.data?.length ? (
        <EmptyState icon={<ShieldCheck className="h-8 w-8 text-success" />} title="No open conflicts">
          Current documents agree with each other on the values checked.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {conflicts.data.map((c) => (
            <Card key={c.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="flex flex-wrap items-center gap-2 font-semibold">
                    <TriangleAlert className="h-4 w-4 text-amber" aria-hidden />
                    {c.a.doc_code} {sectionLabel(c.a.section_path)} vs {c.b.doc_code}{" "}
                    {sectionLabel(c.b.section_path)}
                    <Badge tone={TONE[c.status]}>{c.status}</Badge>
                  </p>
                  <p className="text-sm text-muted">
                    Found{" "}
                    {c.detected_by === "query"
                      ? "while answering a question"
                      : c.detected_by === "ingest"
                        ? "when the document was approved"
                        : "by a user"}{" "}
                    {relativeTime(c.created_at)}
                    {c.confidence !== null ? ` · confidence ${percent(c.confidence)}` : ""}
                    {c.owner ? ` · owner ${c.owner}` : ""}
                  </p>
                </div>
                {c.status === "open" ? (
                  <div className="flex gap-2">
                    <Button size="sm" onClick={() => setActing({ conflict: c, status: "resolved" })}>
                      <CheckCircle2 className="h-4 w-4" /> Resolve
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setActing({ conflict: c, status: "dismissed" })}
                    >
                      <XCircle className="h-4 w-4" /> Dismiss
                    </Button>
                  </div>
                ) : null}
              </div>
              <p className="mt-2 text-sm">{c.description}</p>
              <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
                {[c.a, c.b].map((side) => (
                  <div key={side.chunk_id} className="rounded-xl border border-border bg-surface-2 p-3">
                    <p className="text-sm font-semibold">
                      {side.doc_code} v{side.version} {sectionLabel(side.section_path)}
                    </p>
                    <p className="text-xs text-muted">
                      {side.title} · effective {formatDate(side.effective_from)}
                    </p>
                    <p className="mt-2 whitespace-pre-line text-sm">{side.text}</p>
                  </div>
                ))}
              </div>
              {c.resolution_note ? (
                <p className="mt-2 text-sm text-muted">Resolution: {c.resolution_note}</p>
              ) : null}
            </Card>
          ))}
        </div>
      )}
      {acting ? <ResolveDialog key={acting.conflict.id} {...acting} onClose={() => setActing(null)} /> : null}
    </AdminPage>
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
      void queryClient.invalidateQueries({ queryKey: ["conflicts"] });
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
        className="space-y-3"
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
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
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
