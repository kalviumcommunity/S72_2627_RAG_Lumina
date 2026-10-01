import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Check, X } from "lucide-react";

import { useAuth } from "../../app/providers";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { RuleList } from "../../components/ui/Table";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { hasRole } from "../../lib/auth";
import { formatDate, sectionLabel } from "../../lib/format";
import { queryKeys } from "../../lib/queries";
import type { ActionResult, Supersession } from "../../lib/types";

/** Amendment links as rule-separated rows: source → replaced section, evidence, confirm / reject. */
export function AmendmentList({ links, documentId }: { links: Supersession[]; documentId?: string }) {
  const { session } = useAuth();
  const canApprove = hasRole(session?.user, "approver");
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const change = useMutation({
    mutationFn: async ({ id, confirm }: { id: string; confirm: boolean }): Promise<void> => {
      if (confirm) await api.patch<Supersession>(`/supersessions/${id}`, { confirmed: true });
      else await api.del<ActionResult>(`/supersessions/${id}`);
    },
    onSuccess: (_, vars) => {
      notify(vars.confirm ? "Amendment confirmed" : "Suggestion rejected");
      void queryClient.invalidateQueries({ queryKey: queryKeys.supersessions });
      if (documentId) void queryClient.invalidateQueries({ queryKey: queryKeys.document(documentId) });
    },
    onError: (err) => notify("Could not update the link", { description: errorMessage(err), tone: "error" }),
  });
  return (
    <RuleList>
      {links.map((l) => (
        <li key={l.id} className="grid gap-4 py-5 md:grid-cols-[1fr_auto] md:items-start">
          <div className="min-w-0 space-y-2">
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              <span className="font-mono text-sm">
                {l.source_doc_code} v{l.source_version_label}
              </span>
              <ArrowRight className="h-4 w-4 text-muted" aria-label="amends" />
              <span className="text-lg">
                {l.target_doc_code}
                {l.target_section_path ? ` ${sectionLabel(l.target_section_path)}` : " (whole document)"}
              </span>
              {l.confirmed ? (
                <Badge tone="success">Confirmed</Badge>
              ) : (
                <Badge tone="amber">Suggested — needs review</Badge>
              )}
              {l.source_status !== "approved" ? <Badge>{l.source_status} source</Badge> : null}
            </p>
            <p className="text-caption text-muted">
              From {formatDate(l.effective_from)}
              {l.hides_sections.length
                ? ` · hides ${l.hides_sections.map(sectionLabel).join(", ")}`
                : " · hides nothing yet"}
            </p>
            {l.evidence ? <p className="text-caption italic text-muted">“{l.evidence}”</p> : null}
          </div>
          {!l.confirmed && canApprove ? (
            <div className="flex items-center gap-4">
              <Button
                size="sm"
                loading={change.isPending}
                onClick={() => change.mutate({ id: l.id, confirm: true })}
              >
                <Check className="h-4 w-4" /> Confirm
              </Button>
              <Button variant="link" size="sm" onClick={() => change.mutate({ id: l.id, confirm: false })}>
                <X className="h-4 w-4" /> Reject
              </Button>
            </div>
          ) : null}
        </li>
      ))}
    </RuleList>
  );
}
