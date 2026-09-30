import { CircleHelp, Info, Phone, SearchX, ShieldAlert, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "../../components/ui/Button";
import type { Contact, Escalation } from "../../lib/types";

const REASONS: Record<Escalation["reason"], { title: string; icon: ReactNode; tone: string }> = {
  high_risk: {
    title: "This needs a clinical decision, not a document lookup",
    icon: <ShieldAlert className="h-5 w-5" aria-hidden />,
    tone: "border-danger-border bg-danger-soft text-danger",
  },
  not_found: {
    title: "No approved document covers this",
    icon: <SearchX className="h-5 w-5" aria-hidden />,
    tone: "border-border bg-surface-2 text-text",
  },
  out_of_scope: {
    title: "Outside ProtoCite's scope",
    icon: <Info className="h-5 w-5" aria-hidden />,
    tone: "border-border bg-surface-2 text-text",
  },
  clarify: {
    title: "One more detail is needed",
    icon: <CircleHelp className="h-5 w-5" aria-hidden />,
    tone: "border-accent/30 bg-accent-soft text-accent-text",
  },
  unavailable: {
    title: "The answer service could not complete safely",
    icon: <TriangleAlert className="h-5 w-5" aria-hidden />,
    tone: "border-amber-border bg-amber-soft text-amber",
  },
};

function telHref(value: string): string {
  return `tel:${value.replace(/[^\d+]/g, "")}`;
}

function ContactRow({ contact }: { contact: Contact }) {
  const dial = contact.phone ?? contact.phone_ext;
  return (
    <li className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-3 py-2">
      <div className="min-w-0">
        <p className="font-medium">{contact.role_label}</p>
        <p className="text-sm text-muted">
          {contact.phone_ext ? `Ext ${contact.phone_ext}` : null}
          {contact.phone_ext && contact.pager ? " · " : null}
          {contact.pager ? `Pager ${contact.pager}` : null}
        </p>
        {contact.notes ? <p className="text-xs text-muted">{contact.notes}</p> : null}
      </div>
      {dial ? (
        <a
          href={telHref(dial)}
          className="inline-flex h-11 min-w-11 shrink-0 items-center justify-center gap-1.5 rounded-xl bg-accent px-3 text-sm font-medium text-accent-fg hover:bg-accent-hover"
          aria-label={`Call ${contact.role_label}`}
        >
          <Phone className="h-4 w-4" aria-hidden />
          <span className="hidden sm:inline">Call</span>
        </a>
      ) : null}
    </li>
  );
}

/** Shown instead of an answer: why ProtoCite abstained and who to contact at this branch. */
export function AbstainCard({ escalation, onRefine }: { escalation: Escalation; onRefine?: () => void }) {
  const reason = REASONS[escalation.reason];
  return (
    <section aria-label="No answer given" className="space-y-3">
      <div className={`rounded-2xl border p-4 ${reason.tone}`}>
        <p className="flex items-center gap-2 font-semibold">
          {reason.icon}
          {reason.title}
        </p>
        <p className="mt-1 text-sm text-text">{escalation.message}</p>
        {escalation.clarifying_question ? (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-text">{escalation.clarifying_question}</p>
            {onRefine ? (
              <Button size="sm" variant="secondary" onClick={onRefine}>
                Add the detail
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {escalation.contacts.length ? (
        <div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Escalate to</h3>
          <ul className="space-y-2">
            {escalation.contacts.map((contact) => (
              <ContactRow key={contact.id} contact={contact} />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
