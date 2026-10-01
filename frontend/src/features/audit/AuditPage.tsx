import { useMutation, useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { Download, ShieldAlert, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Page, PageHeader } from "../../app/layout/Page";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Field, Input, Select } from "../../components/ui/Field";
import { Skeleton } from "../../components/ui/Skeleton";
import { Table, Td, Th, Tr } from "../../components/ui/Table";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import { queries } from "../../lib/queries";
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

  const events = useQuery(queries.audit(filters));
  const verify = useMutation({ mutationFn: () => api.get<AuditVerify>("/admin/audit/verify") });
  const exportCsv = useMutation({
    mutationFn: async () => {
      const blob = await api.blob("/admin/audit", { ...filters, format: "csv", limit: 10000 });
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = `lumina-audit-${new Date().toISOString().slice(0, 10)}.csv`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(href), 1000);
    },
    onError: (err) => notify("Export failed", { description: errorMessage(err), tone: "error" }),
  });

  return (
    <Page title="Audit log">
      <PageHeader
        eyebrow="Admin"
        title="Audit log"
        description="Every question, answer, approval and admin action, in order. Each entry includes the hash of the one before it, so any edit or deletion breaks the chain and shows up in the check."
        actions={
          <>
            <Button variant="outline" onClick={() => exportCsv.mutate()} loading={exportCsv.isPending}>
              <Download className="h-4 w-4" /> Export CSV
            </Button>
            <Button onClick={() => verify.mutate()} loading={verify.isPending}>
              <ShieldCheck className="h-4 w-4" /> Check chain
            </Button>
          </>
        }
      />

      {verify.data ? (
        <ChainStatus result={verify.data} />
      ) : verify.error ? (
        <div className="mb-8">
          <ErrorNotice message={errorMessage(verify.error)} />
        </div>
      ) : null}

      <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
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
        <Table label="Audit entries">
          <thead>
            <tr>
              <Th>#</Th>
              <Th>When</Th>
              <Th>Action</Th>
              <Th>By</Th>
              <Th>Hash</Th>
              <Th>
                <span className="sr-only">Details</span>
              </Th>
            </tr>
          </thead>
          <tbody>
            {events.data.map((e) => (
              <AuditRow
                key={e.seq}
                event={e}
                expanded={open === e.seq}
                onToggle={() => setOpen(open === e.seq ? null : e.seq)}
              />
            ))}
          </tbody>
        </Table>
      )}
    </Page>
  );
}

function ChainStatus({ result }: { result: AuditVerify }) {
  const Icon = result.ok ? ShieldCheck : ShieldAlert;
  return (
    <div
      role="status"
      className={clsx(
        "mb-8 flex items-start gap-3 rounded-sm border px-5 py-4 text-sm",
        result.ok ? "border-green/25 bg-green-wash" : "border-error bg-error-wash",
      )}
    >
      <Icon
        className={clsx("mt-0.5 h-5 w-5 shrink-0", result.ok ? "text-green" : "text-error")}
        aria-hidden
      />
      <div>
        <p className="font-medium">{result.ok ? "Chain intact" : "Chain broken"}</p>
        <p className="text-muted">
          {result.ok
            ? `All ${result.events_checked.toLocaleString()} entries link correctly to the previous one.`
            : `Entry #${String(result.first_bad_seq)} does not match: ${result.reason ?? "hash mismatch"}.`}
        </p>
      </div>
    </div>
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
      <Tr className={clsx(expanded && "border-b-0")}>
        <Td className="font-mono text-xs text-muted">{event.seq}</Td>
        <Td className="whitespace-nowrap">{formatDateTime(event.created_at)}</Td>
        <Td>
          <span className="font-mono text-sm">{event.action}</span>
          <span className="ml-2 text-micro text-muted">{event.entity_type}</span>
        </Td>
        <Td>{event.actor ?? "system"}</Td>
        <Td className="font-mono text-xs text-muted" title={event.hash}>
          {event.hash.slice(0, 12)}…
        </Td>
        <Td className="text-right">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="-my-2 min-h-9 text-sm underline decoration-hairline underline-offset-4 hover:decoration-ink"
          >
            {expanded ? "Hide" : "Details"}
          </button>
        </Td>
      </Tr>
      {expanded ? (
        <Tr>
          <Td colSpan={6} className="pb-5 pt-0">
            <p className="mb-2 font-mono text-xs text-muted">
              prev {event.prev_hash.slice(0, 16)}… → this {event.hash.slice(0, 16)}…
              {event.entity_id ? ` · entity ${event.entity_id}` : ""}
            </p>
            <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all rounded-sm bg-stone p-4 font-mono text-xs">
              {JSON.stringify(event.payload, null, 2)}
            </pre>
          </Td>
        </Tr>
      ) : null}
    </>
  );
}
