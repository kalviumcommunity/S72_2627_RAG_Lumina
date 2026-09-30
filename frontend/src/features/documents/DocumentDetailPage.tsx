import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import {
  ArrowLeft,
  Archive,
  CheckCircle2,
  ChevronDown,
  FileWarning,
  GitMerge,
  Loader2,
  RefreshCw,
  ScanText,
  Upload,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router";
import remarkGfm from "remark-gfm";

import { AdminPage } from "../../app/layout/AppShell";
import { useAuth } from "../../app/providers";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { hasRole } from "../../lib/auth";
import { daysUntil, formatDate, formatDateTime, percent, sectionLabel } from "../../lib/format";
import type { ActionResult, ChunkPreview, DocumentDetail, Supersession, Version } from "../../lib/types";
import { DOC_TYPE_LABEL } from "./labels";
import { StatusBadge } from "./shared";
import { UploadDialog } from "./UploadDialog";

export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const [uploadOpen, setUploadOpen] = useState(false);
  const doc = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api.get<DocumentDetail>(`/documents/${documentId}`),
    refetchInterval: (q) =>
      q.state.data?.versions.some((v) => ["pending", "processing"].includes(v.ingest_status)) ? 1500 : false,
  });

  if (doc.isLoading) {
    return (
      <AdminPage>
        <Skeleton className="h-10 w-1/2" />
        <Skeleton className="mt-4 h-48 w-full" />
      </AdminPage>
    );
  }
  if (doc.isError || !doc.data) {
    return (
      <AdminPage>
        <ErrorNotice message={errorMessage(doc.error)} />
      </AdminPage>
    );
  }
  const d = doc.data;
  const pendingLinks = (versionId: string) =>
    d.supersessions_out.filter((s) => s.source_version_id === versionId && !s.confirmed);

  return (
    <AdminPage>
      <Link to="/admin/documents" className="mb-3 inline-flex items-center gap-1 text-sm">
        <ArrowLeft className="h-4 w-4" aria-hidden /> All documents
      </Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-sm font-semibold text-accent-text">{d.doc_code}</p>
          <h1 className="text-2xl font-semibold tracking-tight">{d.title}</h1>
          <p className="mt-1 text-sm text-muted">
            {DOC_TYPE_LABEL[d.doc_type]}
            {d.department ? ` · ${d.department.name}` : ""} · Owner: {d.owner?.display_name ?? "—"} ·{" "}
            {d.applies_to_all_branches ? "All branches" : `${d.branches.map((b) => b.name).join(", ")} only`}
          </p>
        </div>
        <Button variant="secondary" onClick={() => setUploadOpen(true)}>
          <Upload className="h-4 w-4" /> Upload new version
        </Button>
      </div>

      {d.supersessions_in.some((s) => s.confirmed) ? (
        <div className="mb-4 flex items-start gap-2 rounded-xl border border-amber-border bg-amber-soft px-3 py-2 text-sm">
          <GitMerge className="mt-0.5 h-4 w-4 text-amber" aria-hidden />
          <p>
            Amended by{" "}
            {d.supersessions_in
              .filter((s) => s.confirmed)
              .map(
                (s) =>
                  `${s.source_doc_code} v${s.source_version_label}${s.target_section_path ? ` (${sectionLabel(s.target_section_path)})` : ""}`,
              )
              .join(", ")}
            . Amended clauses are hidden from answers once the amendment is in force.
          </p>
        </div>
      ) : null}

      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted">Versions</h2>
      <div className="space-y-3">
        {d.versions.map((v) => (
          <VersionCard key={v.id} documentId={d.id} version={v} pendingLinks={pendingLinks(v.id)} />
        ))}
      </div>

      {d.supersessions_out.length ? (
        <>
          <h2 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-muted">
            Sections this document amends
          </h2>
          <LinkTable links={d.supersessions_out} documentId={d.id} />
        </>
      ) : null}

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        preset={{
          doc_code: d.doc_code,
          title: d.title,
          doc_type: d.doc_type,
          department_code: d.department?.code,
        }}
      />
    </AdminPage>
  );
}

function useDocAction(documentId: string) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  return useMutation({
    mutationFn: ({ url, body }: { url: string; body?: unknown }) => api.post<ActionResult>(url, body),
    onSuccess: (result) => {
      notify(result.message);
      void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
      void queryClient.invalidateQueries({ queryKey: ["supersessions"] });
    },
    onError: (err) => notify("Action failed", { description: errorMessage(err), tone: "error" }),
  });
}

function VersionCard({
  documentId,
  version: v,
  pendingLinks,
}: {
  documentId: string;
  version: Version;
  pendingLinks: Supersession[];
}) {
  const { session } = useAuth();
  const canApprove = hasRole(session?.user, "approver");
  const action = useDocAction(documentId);
  const [approveOpen, setApproveOpen] = useState(false);
  const [retireOpen, setRetireOpen] = useState(false);
  const [showChunks, setShowChunks] = useState(false);
  const base = `/documents/${documentId}/versions/${v.id}`;
  const processing = ["pending", "processing"].includes(v.ingest_status);
  const reviewDays = v.review_due ? daysUntil(v.review_due) : null;
  const warnings = (v.parse_warnings as { code?: string; message?: string }[]).filter((w) => w.message);

  return (
    <Card className={clsx("p-4", v.is_current && "border-success/40")}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="flex flex-wrap items-center gap-2 font-semibold">
            Version {v.version_label}
            <StatusBadge status={v.status} />
            {v.is_current ? <Badge tone="success">In force</Badge> : null}
            {processing ? (
              <Badge>
                <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> Processing
              </Badge>
            ) : v.ingest_status === "failed" ? (
              <Badge tone="danger">Processing failed</Badge>
            ) : null}
          </p>
          <p className="text-sm text-muted">
            Effective {formatDate(v.effective_from)} ·{" "}
            <span
              className={clsx(
                reviewDays !== null && reviewDays < 0 && v.status === "approved" && "font-medium text-danger",
              )}
            >
              review due {formatDate(v.review_due)}
            </span>{" "}
            · {v.original_filename}
            {v.approved_at ? ` · approved ${formatDateTime(v.approved_at)}` : ""}
          </p>
          <p className="text-xs text-muted">
            {v.chunk_count} clauses indexed{v.parser ? ` · parsed with ${v.parser}` : ""}
            {v.page_count ? ` · ${String(v.page_count)} page(s)` : ""}
            {v.ocr_min_confidence !== null ? (
              <span className="ml-1 inline-flex items-center gap-1">
                · <ScanText className="h-3 w-3" aria-hidden /> OCR confidence {percent(v.ocr_min_confidence)}
              </span>
            ) : null}
          </p>
          {v.change_summary ? <p className="text-sm">{v.change_summary}</p> : null}
        </div>
        <div className="flex flex-wrap gap-2">
          {v.status === "draft" && v.needs_ocr_acknowledgement ? (
            <Button
              variant="secondary"
              size="sm"
              loading={action.isPending}
              onClick={() => action.mutate({ url: `${base}/acknowledge-ocr` })}
            >
              <ScanText className="h-4 w-4" /> I've checked the OCR text
            </Button>
          ) : null}
          {v.status === "draft" && canApprove ? (
            <Button
              size="sm"
              disabled={processing || v.ingest_status === "failed" || v.needs_ocr_acknowledgement}
              onClick={() => setApproveOpen(true)}
            >
              <CheckCircle2 className="h-4 w-4" /> Approve
            </Button>
          ) : null}
          {v.status === "draft" && !processing ? (
            <Button variant="ghost" size="sm" onClick={() => action.mutate({ url: `${base}/reingest` })}>
              <RefreshCw className="h-4 w-4" /> Re-process
            </Button>
          ) : null}
          {v.status !== "retired" && v.status !== "draft" && canApprove ? (
            <Button variant="ghost" size="sm" onClick={() => setRetireOpen(true)}>
              <Archive className="h-4 w-4" /> Retire
            </Button>
          ) : null}
        </div>
      </div>

      {v.ingest_error ? (
        <div className="mt-3">
          <ErrorNotice title="Processing failed" message={v.ingest_error} />
        </div>
      ) : null}
      {warnings.length ? (
        <ul className="mt-3 space-y-1.5">
          {warnings.map((w, i) => (
            <li
              key={i}
              className={clsx(
                "flex items-start gap-2 rounded-lg border px-3 py-2 text-sm",
                w.code === "ocr_low_confidence"
                  ? "border-amber-border bg-amber-soft"
                  : "border-border bg-surface-2",
              )}
            >
              <FileWarning className="mt-0.5 h-4 w-4 shrink-0 text-amber" aria-hidden />
              {w.message}
            </li>
          ))}
        </ul>
      ) : null}

      {v.chunk_count > 0 ? (
        <button
          type="button"
          onClick={() => setShowChunks(!showChunks)}
          aria-expanded={showChunks}
          className="mt-3 inline-flex min-h-10 items-center gap-1 text-sm font-medium text-accent-text"
        >
          <ChevronDown
            className={clsx("h-4 w-4 transition-transform", showChunks && "rotate-180")}
            aria-hidden
          />
          {showChunks ? "Hide" : "Show"} indexed clauses
        </button>
      ) : null}
      {showChunks ? <ChunkList documentId={documentId} versionId={v.id} /> : null}

      <ApproveDialog
        open={approveOpen}
        onOpenChange={setApproveOpen}
        version={v}
        links={pendingLinks}
        pending={action.isPending}
        onApprove={(confirmLinks) =>
          action.mutate(
            { url: `${base}/approve`, body: { confirm_suggested_supersessions: confirmLinks } },
            { onSuccess: () => setApproveOpen(false) },
          )
        }
      />
      <Dialog
        open={retireOpen}
        onOpenChange={setRetireOpen}
        title={`Retire version ${v.version_label}?`}
        description="Retired versions are never used in answers and any amendments they made stop applying."
      >
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setRetireOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            loading={action.isPending}
            onClick={() =>
              action.mutate({ url: `${base}/retire` }, { onSuccess: () => setRetireOpen(false) })
            }
          >
            Retire version
          </Button>
        </div>
      </Dialog>
    </Card>
  );
}

function ApproveDialog({
  open,
  onOpenChange,
  version,
  links,
  pending,
  onApprove,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  version: Version;
  links: Supersession[];
  pending: boolean;
  onApprove: (confirmLinks: boolean) => void;
}) {
  const [confirmLinks, setConfirmLinks] = useState(true);
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title={`Approve version ${version.version_label}?`}
      description={`Clinicians will see it in answers from ${formatDate(version.effective_from)}. This is recorded in the audit log.`}
    >
      {links.length ? (
        <div className="mb-4 space-y-2">
          <p className="text-sm font-medium">Amendments detected in this document:</p>
          <ul className="space-y-1.5">
            {links.map((l) => (
              <li
                key={l.id}
                className="rounded-lg border border-amber-border bg-amber-soft px-3 py-2 text-sm"
              >
                Replaces <strong>{l.target_doc_code}</strong>
                {l.target_section_path ? ` ${sectionLabel(l.target_section_path)}` : " (whole document)"}
                {l.hides_sections.length ? (
                  <span className="block text-xs text-muted">
                    Will hide: {l.hides_sections.map(sectionLabel).join(", ")}
                  </span>
                ) : null}
                {l.evidence ? (
                  <span className="mt-1 block text-xs italic text-muted">“{l.evidence}”</span>
                ) : null}
              </li>
            ))}
          </ul>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={confirmLinks}
              onChange={(e) => setConfirmLinks(e.target.checked)}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            Also confirm these amendments (the amended clauses stop appearing in answers)
          </label>
        </div>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button loading={pending} onClick={() => onApprove(links.length > 0 && confirmLinks)}>
          <CheckCircle2 className="h-4 w-4" /> Approve
        </Button>
      </div>
    </Dialog>
  );
}

function ChunkList({ documentId, versionId }: { documentId: string; versionId: string }) {
  const chunks = useQuery({
    queryKey: ["chunks", versionId],
    queryFn: () => api.get<ChunkPreview[]>(`/documents/${documentId}/versions/${versionId}/chunks`),
  });
  if (chunks.isLoading) return <Skeleton className="mt-2 h-24 w-full" />;
  if (chunks.isError) return <ErrorNotice message={errorMessage(chunks.error)} />;
  return (
    <ol className="mt-2 max-h-96 space-y-2 overflow-y-auto rounded-xl border border-border p-2">
      {(chunks.data ?? [])
        .filter((c) => !c.heading.includes(" — row "))
        .map((c) => (
          <li key={c.id} className="rounded-lg bg-surface-2 px-3 py-2">
            <p className="text-sm font-semibold">
              <span className="text-accent-text">{sectionLabel(c.section_path)}</span> {c.heading}
              <span className="ml-2 text-xs font-normal text-muted">
                p.{c.page_start} · {c.token_count} tokens{c.is_table ? " · table" : ""}
              </span>
            </p>
            <div className="prose-source text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{c.text}</ReactMarkdown>
            </div>
          </li>
        ))}
    </ol>
  );
}

export function LinkTable({ links, documentId }: { links: Supersession[]; documentId?: string }) {
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
      void queryClient.invalidateQueries({ queryKey: ["supersessions"] });
      if (documentId) void queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    },
    onError: (err) => notify("Could not update the link", { description: errorMessage(err), tone: "error" }),
  });
  return (
    <Card className="divide-y divide-border">
      {links.map((l) => (
        <div key={l.id} className="flex flex-wrap items-start justify-between gap-3 p-4">
          <div className="min-w-0 space-y-1">
            <p className="flex flex-wrap items-center gap-2 font-medium">
              {l.source_doc_code} v{l.source_version_label}
              <span className="text-muted">amends</span>
              {l.target_doc_code}
              {l.target_section_path ? ` ${sectionLabel(l.target_section_path)}` : " (whole document)"}
              {l.confirmed ? (
                <Badge tone="success">Confirmed</Badge>
              ) : (
                <Badge tone="amber">Suggested — needs review</Badge>
              )}
              {l.source_status !== "approved" ? <Badge>{l.source_status} source</Badge> : null}
            </p>
            <p className="text-sm text-muted">
              From {formatDate(l.effective_from)}
              {l.hides_sections.length
                ? ` · hides ${l.hides_sections.map(sectionLabel).join(", ")}`
                : " · hides nothing yet"}
            </p>
            {l.evidence ? <p className="text-xs italic text-muted">“{l.evidence}”</p> : null}
          </div>
          {!l.confirmed && canApprove ? (
            <div className="flex gap-2">
              <Button
                size="sm"
                loading={change.isPending}
                onClick={() => change.mutate({ id: l.id, confirm: true })}
              >
                <CheckCircle2 className="h-4 w-4" /> Confirm
              </Button>
              <Button size="sm" variant="ghost" onClick={() => change.mutate({ id: l.id, confirm: false })}>
                <XCircle className="h-4 w-4" /> Reject
              </Button>
            </div>
          ) : null}
        </div>
      ))}
    </Card>
  );
}
