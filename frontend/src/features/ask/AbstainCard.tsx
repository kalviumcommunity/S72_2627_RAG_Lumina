import { clsx } from "clsx";
import { Phone } from "lucide-react";

import { Button } from "../../components/ui/Button";
import { RuleList } from "../../components/ui/Table";
import type { Contact, Escalation } from "../../lib/types";

const REASONS: Record<Escalation["reason"], { label: string; title: string; frame: string }> = {
  high_risk: {
    label: "Patient-specific",
    title: "This needs a clinical decision, not a document lookup",
    frame: "border border-error bg-error-wash",
  },
  not_found: { label: "Not found", title: "No approved document covers this", frame: "bg-stone" },
  out_of_scope: { label: "Out of scope", title: "Outside Lumina's scope", frame: "bg-stone" },
  clarify: { label: "Clarify", title: "One more detail is needed", frame: "bg-blue-wash" },
  unavailable: {
    label: "Unavailable",
    title: "The answer service could not complete safely",
    frame: "border border-coral-soft bg-coral-wash",
  },
};

function telHref(value: string): string {
  return `tel:${value.replace(/[^\d+]/g, "")}`;
}

function ContactRow({ contact }: { contact: Contact }) {
  const dial = contact.phone ?? contact.phone_ext;
  return (
    <li className="flex items-center justify-between gap-4 py-3.5">
      <div className="min-w-0">
        <p className="font-medium">{contact.role_label}</p>
        <p className="font-mono text-sm text-muted">
          {contact.phone_ext ? `Ext ${contact.phone_ext}` : null}
          {contact.phone_ext && contact.pager ? " · " : null}
          {contact.pager ? `Pager ${contact.pager}` : null}
        </p>
        {contact.notes ? <p className="mt-0.5 text-micro text-muted">{contact.notes}</p> : null}
      </div>
      {dial ? (
        <a
          href={telHref(dial)}
          className="inline-flex min-h-10 shrink-0 items-center gap-2 rounded-pill bg-primary px-5 text-sm font-medium text-white no-underline hover:bg-primary-hover"
          aria-label={`Call ${contact.role_label}`}
        >
          <Phone className="h-4 w-4" aria-hidden />
          Call
        </a>
      ) : null}
    </li>
  );
}

/** Shown instead of an answer: why Lumina abstained and who to contact at this branch. */
export function AbstainCard({ escalation, onRefine }: { escalation: Escalation; onRefine?: () => void }) {
  const reason = REASONS[escalation.reason];
  return (
    <section aria-label="No answer given" className="space-y-6">
      <div className={clsx("rounded-md p-5", reason.frame)}>
        <p className={clsx("mono-label", escalation.reason === "high_risk" ? "text-error" : "text-muted")}>
          {reason.label}
        </p>
        <p className="mt-2 text-feature">{reason.title}</p>
        <p className="mt-2 text-sm">{escalation.message}</p>
        {escalation.clarifying_question ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <p className="font-medium">{escalation.clarifying_question}</p>
            {onRefine ? (
              <Button size="sm" variant="outline" onClick={onRefine}>
                Add the detail
              </Button>
            ) : null}
          </div>
        ) : null}
      </div>
      {escalation.contacts.length ? (
        <div>
          <h3 className="mono-label mb-1 text-ink">Escalate to</h3>
          <RuleList>
            {escalation.contacts.map((contact) => (
              <ContactRow key={contact.id} contact={contact} />
            ))}
          </RuleList>
        </div>
      ) : null}
    </section>
  );
}
