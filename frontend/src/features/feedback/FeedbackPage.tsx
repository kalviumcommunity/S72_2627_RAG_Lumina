import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { CheckCircle2, Eye, Inbox } from "lucide-react";
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
import { relativeTime } from "../../lib/format";
import type { Feedback, FeedbackKind } from "../../lib/types";

type Status = Feedback["status"];

const KIND: Record<FeedbackKind, { label: string; tone: Tone }> = {
  wrong: { label: "Reported wrong", tone: "danger" },
  outdated: { label: "Reported outdated", tone: "amber" },
  unhelpful: { label: "Not helpful", tone: "neutral" },
  helpful: { label: "Helpful", tone: "success" },
};
const STATUS_TONE: Record<Status, Tone> = { open: "accent", acknowledged: "amber", resolved: "success" };

/** Reports from clinicians ("wrong", "outdated", "not helpful"), routed to the cited document's owner. */
export function FeedbackPage() {
  const [includeResolved, setIncludeResolved] = useState(false);
  const [acting, setActing] = useState<{ item: Feedback; status: Status } | null>(null);
  const inbox = useQuery({
    queryKey: ["feedback-inbox", includeResolved],
    queryFn: () => api.get<Feedback[]>("/feedback/inbox", { include_resolved: includeResolved }),
  });

  return (
    <AdminPage>
      <PageHeader
        title="Feedback"
        description="When a clinician flags an answer, the report comes to the owner of the cited document with the question, the answer and the clauses it cited."
        actions={
          <div className="flex gap-1 rounded-xl border border-border bg-surface-2 p-1">
            {([false, true] as const).map((value) => (
              <button
                key={String(value)}
                type="button"
                aria-pressed={includeResolved === value}
                onClick={() => setIncludeResolved(value)}
                className={clsx(
                  "min-h-9 rounded-lg px-3 text-sm",
                  includeResolved === value ? "bg-surface font-medium shadow-card" : "text-muted",
                )}
              >
                {value ? "All" : "Open"}
              </button>
            ))}
          </div>
        }
      />
      {inbox.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : inbox.isError ? (
        <ErrorNotice message={errorMessage(inbox.error)} />
      ) : !inbox.data?.length ? (
        <EmptyState icon={<Inbox className="h-8 w-8" />} title="Inbox is clear">
          No reports need your attention.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {inbox.data.map((fb) => (
            <Card key={fb.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={KIND[fb.kind].tone}>{KIND[fb.kind].label}</Badge>
                  <Badge tone={STATUS_TONE[fb.status]}>{fb.status}</Badge>
                  <span className="text-sm text-muted">
                    {fb.reporter ?? "A clinician"} · {relativeTime(fb.created_at)}
                    {fb.routed_to ? ` · routed to ${fb.routed_to}` : ""}
                  </span>
                </div>
                {fb.status !== "resolved" ? (
                  <div className="flex gap-2">
                    {fb.status === "open" ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setActing({ item: fb, status: "acknowledged" })}
                      >
                        <Eye className="h-4 w-4" /> Acknowledge
                      </Button>
                    ) : null}
                    <Button size="sm" onClick={() => setActing({ item: fb, status: "resolved" })}>
                      <CheckCircle2 className="h-4 w-4" /> Resolve
                    </Button>
                  </div>
                ) : null}
              </div>
              <dl className="mt-3 space-y-2 text-sm">
                <div>
                  <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                    Question (identifiers removed)
                  </dt>
                  <dd className="mt-0.5 font-medium">{fb.question}</dd>
                </div>
                {fb.answer ? (
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                      Answer given ({fb.outcome})
                    </dt>
                    <dd className="mt-0.5 line-clamp-4 whitespace-pre-line text-muted">{fb.answer}</dd>
                  </div>
                ) : null}
                {fb.comment ? (
                  <div className="rounded-xl border border-border bg-surface-2 p-3">
                    <dt className="text-xs font-semibold uppercase tracking-wide text-muted">
                      Clinician's comment
                    </dt>
                    <dd className="mt-0.5">{fb.comment}</dd>
                  </div>
                ) : null}
                {fb.cited.length ? (
                  <div className="flex flex-wrap items-center gap-1.5">
                    <dt className="text-xs text-muted">Cited:</dt>
                    {fb.cited.map((c) => (
                      <dd key={c}>
                        <Badge>{c}</Badge>
                      </dd>
                    ))}
                  </div>
                ) : null}
                {fb.resolution_note ? (
                  <div>
                    <dt className="text-xs font-semibold uppercase tracking-wide text-muted">Owner's note</dt>
                    <dd className="mt-0.5">{fb.resolution_note}</dd>
                  </div>
                ) : null}
              </dl>
            </Card>
          ))}
        </div>
      )}
      {acting ? <NoteDialog key={acting.item.id} {...acting} onClose={() => setActing(null)} /> : null}
    </AdminPage>
  );
}

function NoteDialog({ item, status, onClose }: { item: Feedback; status: Status; onClose: () => void }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [note, setNote] = useState(item.resolution_note ?? "");
  const save = useMutation({
    mutationFn: () =>
      api.patch<Feedback>(`/feedback/${item.id}`, { status, resolution_note: note.trim() || null }),
    onSuccess: () => {
      notify(status === "resolved" ? "Feedback resolved" : "Feedback acknowledged");
      void queryClient.invalidateQueries({ queryKey: ["feedback-inbox"] });
      void queryClient.invalidateQueries({ queryKey: ["admin-stats"] });
      onClose();
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={status === "resolved" ? "Resolve feedback" : "Acknowledge feedback"}
      description={
        status === "resolved"
          ? "Say what was done (e.g. circular issued, document corrected, or answer was correct)."
          : "Let the reporter know it is being looked at (optional note)."
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
            <Textarea
              {...props}
              rows={3}
              required={status === "resolved"}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          )}
        </Field>
        {save.error ? <ErrorNotice message={errorMessage(save.error)} /> : null}
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={save.isPending} disabled={status === "resolved" && !note.trim()}>
            Save
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
