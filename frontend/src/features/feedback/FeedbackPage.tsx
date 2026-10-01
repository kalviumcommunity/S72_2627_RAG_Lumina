import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, Inbox } from "lucide-react";
import { useState, type ReactNode } from "react";

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
import { relativeTime } from "../../lib/format";
import { queries, queryKeys } from "../../lib/queries";
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
  const inbox = useQuery(queries.feedback(includeResolved));

  return (
    <Page title="Feedback">
      <PageHeader
        eyebrow="Review"
        title="Feedback"
        description="When a clinician flags an answer, the report comes to the owner of the cited document with the question, the answer and the clauses it cited."
        actions={
          <Segmented
            label="Show"
            value={includeResolved}
            onChange={setIncludeResolved}
            options={[
              [false, "Open"],
              [true, "All"],
            ]}
          />
        }
      />
      {inbox.isLoading ? (
        <Skeleton className="h-48 w-full" />
      ) : inbox.isError ? (
        <ErrorNotice message={errorMessage(inbox.error)} />
      ) : !inbox.data?.length ? (
        <EmptyState icon={<Inbox className="h-6 w-6" />} title="Inbox is clear">
          No reports need your attention.
        </EmptyState>
      ) : (
        <ul className="space-y-6">
          {inbox.data.map((fb) => (
            <li key={fb.id}>
              <FeedbackCard item={fb} onAct={(status) => setActing({ item: fb, status })} />
            </li>
          ))}
        </ul>
      )}
      {acting ? <NoteDialog key={acting.item.id} {...acting} onClose={() => setActing(null)} /> : null}
    </Page>
  );
}

function Entry({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="mono-label text-muted">{label}</dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}

function FeedbackCard({ item: fb, onAct }: { item: Feedback; onAct: (status: Status) => void }) {
  return (
    <Card className="p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={KIND[fb.kind].tone}>{KIND[fb.kind].label}</Badge>
          <Badge tone={STATUS_TONE[fb.status]}>{fb.status}</Badge>
          <span className="text-caption text-muted">
            {fb.reporter ?? "A clinician"} · {relativeTime(fb.created_at)}
            {fb.routed_to ? ` · routed to ${fb.routed_to}` : ""}
          </span>
        </div>
        {fb.status !== "resolved" ? (
          <div className="flex items-center gap-3">
            {fb.status === "open" ? (
              <Button size="sm" variant="outline" onClick={() => onAct("acknowledged")}>
                <Eye className="h-4 w-4" /> Acknowledge
              </Button>
            ) : null}
            <Button size="sm" onClick={() => onAct("resolved")}>
              <Check className="h-4 w-4" /> Resolve
            </Button>
          </div>
        ) : null}
      </div>
      <dl className="mt-6 space-y-5 text-sm">
        <Entry label="Question (identifiers removed)">
          <span className="text-feature">{fb.question}</span>
        </Entry>
        {fb.answer ? (
          <Entry label={`Answer given (${fb.outcome})`}>
            <span className="line-clamp-4 whitespace-pre-line text-muted">{fb.answer}</span>
          </Entry>
        ) : null}
        {fb.comment ? (
          <div className="rounded-sm bg-stone p-4">
            <dt className="mono-label text-muted">Clinician's comment</dt>
            <dd className="mt-1">{fb.comment}</dd>
          </div>
        ) : null}
        {fb.cited.length ? (
          <div className="flex flex-wrap items-center gap-2">
            <dt className="mono-label text-muted">Cited</dt>
            {fb.cited.map((c) => (
              <dd key={c}>
                <Badge>{c}</Badge>
              </dd>
            ))}
          </div>
        ) : null}
        {fb.resolution_note ? (
          <div className="border-t border-hairline pt-4">
            <Entry label="Owner's note">{fb.resolution_note}</Entry>
          </div>
        ) : null}
      </dl>
    </Card>
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.feedback });
      void queryClient.invalidateQueries({ queryKey: queryKeys.stats });
      void queryClient.invalidateQueries({ queryKey: queryKeys.overview });
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
        className="space-y-5"
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
        <div className="flex items-center justify-end gap-4">
          <Button variant="link" onClick={onClose}>
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
