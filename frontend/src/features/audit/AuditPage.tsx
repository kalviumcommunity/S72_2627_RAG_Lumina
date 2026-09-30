import { useMutation, useQuery } from "@tanstack/react-query";
import { Download, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { AdminPage, PageHeader } from "../../app/layout/AppShell";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Input, Select } from "../../components/ui/Field";
import { Skeleton } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import type { AuditEvent, AuditVerify } from "../../lib/types";

const ACTIONS = ["", "query", "version", "supersession", "conflict", "feedback", "auth", "review"];

/** Append-only, hash-chained record of every question, approval and admin change. */
export function AuditPage() {
  const { notify } = useToast();
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  const filters = { from, to, action };

  const events = useQuery({
    queryKey: ["audit-events", filters],
    queryFn: () => api.get<AuditEvent[]>("/admin/audit", { ...filters, limit: 200 }),
  });
  const verify = useMutation({ mutationFn: () => api.get<AuditVerify>("/admin/audit/verify") });
  const exportCsv = useMutation({
    mutationFn: async () => {
      const blob = await api.blob("/admin/audit", { ...filters, format: "csv", limit: 10000 });
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `protocite-audit-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(href), 1000);
    },
    onError: (err) => notify("Export failed", { description: errorMessage(err), tone: "error" }),
  });

  return (
    <AdminPage>
      <PageHeader
        title="Audit log"
        description="Every question, answer, approval and admin action, in order. Each entry includes the hash of the one before it, so any edit or deletion breaks the chain and shows up in the check."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={() => exportCsv.mutate()} loading={exportCsv.isPending}>
              <Download className="h-4 w-4" /> Export CSV
            </Button>
            <Button onClick={() => verify.mutate()} loading={verify.isPending}>
              <ShieldCheck className="h-4 w-4" /> Check chain
            </Button>
          </div>
        }
      />

      {verify.data ? (
        <div
          role="status"
          className={
            verify.data.ok
              ? "mb-4 flex items-start gap-3 rounded-2xl border border-success/30 bg-success-soft p-4 text-sm"
              : "mb-4 flex items-start gap-3 rounded-2xl border border-danger-border bg-danger-soft p-4 text-sm"
          }
        >
          {verify.data.ok ? (
            <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-success" aria-hidden />
          ) : (
            <ShieldAlert className="mt-0.5 h-5 w-5 shrink-0 text-danger" aria-hidden />
          )}
          <div>
            <p className="font-semibold">{verify.data.ok ? "Chain intact" : "Chain broken"}</p>
            <p className="text-muted">
              {verify.data.ok
                ? `All ${verify.data.events_checked.toLocaleString()} entries link correctly to the previous one.`
                : `Entry #${String(verify.data.first_bad_seq)} does not match: ${verify.data.reason ?? "hash mismatch"}.`}
            </p>
          </div>
        </div>
      ) : verify.error ? (
        <div className="mb-4">
          <ErrorNotice message={errorMessage(verify.error)} />
        </div>
      ) : null}

      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Field label="From">
          {(props) => <Input {...props} type="date" value={from} onChange={(e) => setFrom(e.target.value)} />}
        </Field>
        <Field label="To">
          {(props) => <Input {...props} type="date" value={to} onChange={(e) => setTo(e.target.value)} />}
        </Field>
        <Field label="Kind of action">
          {(props) => (
            <Select {...props} value={action} onChange={(e) => setAction(e.target.value)}>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a ? `${a}.*` : "All"}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>

      {events.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : events.isError ? (
        <ErrorNotice message={errorMessage(events.error)} />
      ) : !events.data?.length ? (
        <EmptyState title="No entries match these filters" />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-border bg-surface-2 text-xs uppercase tracking-wide text-muted">
                <tr>
                  <th className="px-3 py-2">#</th>
                  <th className="px-3 py-2">When</th>
                  <th className="px-3 py-2">Action</th>
                  <th className="px-3 py-2">By</th>
                  <th className="px-3 py-2">Hash</th>
                  <th className="px-3 py-2">
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {events.data.map((e) => (
                  <AuditRow
                    key={e.seq}
                    event={e}
                    expanded={open === e.seq}
                    onToggle={() => setOpen(open === e.seq ? null : e.seq)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </AdminPage>
  );
}

function AuditRow({
  event,
  expanded,
  onToggle,
}: {
  event: AuditEvent;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr className="align-top">
        <td className="px-3 py-2 font-mono text-xs text-muted">{event.seq}</td>
        <td className="whitespace-nowrap px-3 py-2">{formatDateTime(event.created_at)}</td>
        <td className="px-3 py-2">
          <Badge className="font-mono">{event.action}</Badge>
          <span className="ml-2 text-xs text-muted">{event.entity_type}</span>
        </td>
        <td className="px-3 py-2">{event.actor ?? "system"}</td>
        <td className="px-3 py-2 font-mono text-xs text-muted" title={event.hash}>
          {event.hash.slice(0, 12)}…
        </td>
        <td className="px-3 py-2 text-right">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="min-h-9 rounded-lg px-2 text-accent-text hover:underline"
          >
            {expanded ? "Hide" : "Details"}
          </button>
        </td>
      </tr>
      {expanded ? (
        <tr>
          <td colSpan={6} className="bg-surface-2 px-3 py-3">
            <p className="mb-1 font-mono text-xs text-muted">
              prev {event.prev_hash.slice(0, 16)}… → this {event.hash.slice(0, 16)}…
              {event.entity_id ? ` · entity ${event.entity_id}` : ""}
            </p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-surface p-3 font-mono text-xs">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </td>
        </tr>
      ) : null}
    </>
  );
}
