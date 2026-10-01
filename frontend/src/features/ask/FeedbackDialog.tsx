import { useMutation } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useState } from "react";

import { Button } from "../../components/ui/Button";
import { Dialog } from "../../components/ui/Dialog";
import { Field, Textarea } from "../../components/ui/Field";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import type { Feedback, FeedbackKind } from "../../lib/types";

const PROBLEMS: { value: Exclude<FeedbackKind, "helpful">; label: string; hint: string }[] = [
  { value: "wrong", label: "Wrong", hint: "The answer does not match the cited document" },
  { value: "outdated", label: "Outdated", hint: "A newer protocol or circular should apply" },
  { value: "unhelpful", label: "Unhelpful", hint: "Correct but did not answer my question" },
];

function useSendFeedback(queryId: string) {
  const { notify } = useToast();
  return useMutation({
    mutationFn: (body: { kind: FeedbackKind; comment?: string }) =>
      api.post<Feedback>("/feedback", { query_id: queryId, ...body }),
    onSuccess: (fb) =>
      notify(fb.kind === "helpful" ? "Thanks — feedback recorded" : "Reported to the document owner", {
        description: fb.routed_to ? `Routed to ${fb.routed_to}` : undefined,
      }),
    onError: (err) => notify("Feedback not sent", { description: errorMessage(err), tone: "error" }),
  });
}

/** Thumbs up, or "Report a problem" → Wrong / Outdated / Unhelpful + optional comment. */
export function FeedbackButtons({ queryId }: { queryId: string }) {
  const [open, setOpen] = useState(false);
  const [sent, setSent] = useState<FeedbackKind | null>(null);
  const send = useSendFeedback(queryId);
  return (
    <div className="flex items-center gap-2">
      <Button
        size="icon"
        variant="ghost"
        aria-label="Helpful"
        aria-pressed={sent === "helpful"}
        disabled={sent !== null}
        onClick={() => send.mutate({ kind: "helpful" }, { onSuccess: () => setSent("helpful") })}
        className={clsx("rounded-full", sent === "helpful" && "bg-green-wash text-green")}
      >
        <ThumbsUp className="h-4 w-4" />
      </Button>
      <Button size="sm" variant="outline" disabled={sent !== null} onClick={() => setOpen(true)}>
        <ThumbsDown className="h-4 w-4" />
        {sent && sent !== "helpful" ? "Reported" : "Report a problem"}
      </Button>
      <FeedbackDialog
        open={open}
        onOpenChange={setOpen}
        pending={send.isPending}
        onSubmit={(kind, comment) =>
          send.mutate(
            { kind, comment: comment || undefined },
            {
              onSuccess: () => {
                setSent(kind);
                setOpen(false);
              },
            },
          )
        }
      />
    </div>
  );
}

export function FeedbackDialog({
  open,
  onOpenChange,
  onSubmit,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (kind: FeedbackKind, comment: string) => void;
  pending: boolean;
}) {
  const [kind, setKind] = useState<Exclude<FeedbackKind, "helpful">>("wrong");
  const [comment, setComment] = useState("");
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Report a problem with this answer"
      description="The report goes to the owner of the cited document and is kept in the audit log. Do not include patient details."
    >
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(kind, comment.trim());
        }}
      >
        <fieldset>
          <legend className="mono-label mb-3 text-ink">What is wrong?</legend>
          <div className="grid gap-2">
            {PROBLEMS.map((p) => (
              <label
                key={p.value}
                className={clsx(
                  "flex min-h-11 cursor-pointer items-start gap-3 rounded-sm border px-4 py-3 transition-colors",
                  kind === p.value ? "border-primary bg-stone" : "border-hairline hover:border-primary",
                )}
              >
                <input
                  type="radio"
                  name="kind"
                  value={p.value}
                  checked={kind === p.value}
                  onChange={() => setKind(p.value)}
                  className="mt-1 accent-black"
                />
                <span>
                  <span className="block font-medium">{p.label}</span>
                  <span className="block text-caption text-muted">{p.hint}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        <Field label="Comment (optional)" hint="e.g. which circular or section you expected to see.">
          {(props) => (
            <Textarea
              {...props}
              rows={3}
              maxLength={2000}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
            />
          )}
        </Field>
        <div className="flex items-center justify-end gap-4">
          <Button variant="link" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button type="submit" loading={pending}>
            Send report
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
