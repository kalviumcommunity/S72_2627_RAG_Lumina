import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ArrowLeft, Archive, Check, ChevronDown, RefreshCw, ScanText, Upload } from "lucide-react";
import { useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router";
import remarkGfm from "remark-gfm";

import { Page, SectionTitle } from "../../app/layout/Page";
import { paths } from "../../app/paths";
import { useAuth } from "../../app/providers";
import { Badge, TaxonomyChip } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Dialog } from "../../components/ui/Dialog";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { RuleList } from "../../components/ui/Table";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { hasRole } from "../../lib/auth";
import { daysUntil, formatDate, formatDateTime, percent, sectionLabel } from "../../lib/format";
import { queries, queryKeys } from "../../lib/queries";
import type { ActionResult, Supersession, Version } from "../../lib/types";
import { AmendmentList } from "../supersessions/AmendmentList";
import { DOC_TYPE_LABEL } from "./labels";
import { StatusBadge } from "./shared";
import { UploadDialog } from "./UploadDialog";

/** One document: its versions, warnings, approval and the amendments it makes or receives. */
export function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const [uploadOpen, setUploadOpen] = useState(false);
  const doc = useQuery({
    ...queries.document(documentId),
    refetchInterval: (q) =>
      q.state.data?.versions.some((v) => ["pending", "processing"].includes(v.ingest_status)) ? 1500 : false,
  });

  if (doc.isLoading) {
    return (
      <Page title="Document">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-4 h-16 w-2/3" />
        <Skeleton className="mt-10 h-48 w-full" />
      </Page>
    );
  }
  if (doc.isError || !doc.data) {
    return (
      <Page title="Document">
        <ErrorNotice message={errorMessage(doc.error)} />
      </Page>
    );
  }
  const d = doc.data;
  const pendingLinks = (versionId: string) =>
    d.supersessions_out.filter((s) => s.source_version_id === versionId && !s.confirmed);
  const amendedBy = d.supersessions_in.filter((s) => s.confirmed);

  return (
    <Page title={d.doc_code}>
      <Link
        to={paths.library}
        className="inline-flex items-center gap-1.5 text-sm text-ink no-underline hover:underline"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden /> Library
      </Link>

      <header className="mb-10 mt-6 flex flex-wrap items-end justify-between gap-6">
        <div className="max-w-4xl">
          <p className="flex flex-wrap items-center gap-3">
            <span className="font-mono text-sm">{d.doc_code}</span>
            <TaxonomyChip>{DOC_TYPE_LABEL[d.doc_type]}</TaxonomyChip>
          </p>
          <h1 className="mt-4 text-display">{d.title}</h1>
          <p className="mt-4 text-caption text-muted">
            {d.department?.name ?? "No department"} · Owner {d.owner?.display_name ?? "—"} ·{" "}
            {d.applies_to_all_branches ? "All branches" : `${d.branches.map((b) => b.name).join(", ")} only`}
          </p>
        </div>
        <Button variant="outline" onClick={() => setUploadOpen(true)}>
          <Upload className="h-4 w-4" /> Upload new version
        </Button>
      </header>

      {amendedBy.length ? (
        <div className="mb-10 rounded-sm border border-blue/20 bg-blue-wash px-5 py-4 text-sm">
          <p className="mono-label mb-1 text-blue">Amended</p>
          <p>
            Amended by{" "}
            {amendedBy
              .map(
                (s) =>
                  `${s.source_doc_code} v${s.source_version_label}${s.target_section_path ? ` (${sectionLabel(s.target_section_path)})` : ""}`,
              )
              .join(", ")}
            . Amended clauses are hidden from answers once the amendment is in force.
          </p>
        </div>
      ) : null}

      <section aria-label="Versions">
        <SectionTitle>Versions ({d.versions.length})</SectionTitle>
        <div className="space-y-4">
          {d.versions.map((v) => (
            <VersionCard key={v.id} documentId={d.id} version={v} pendingLinks={pendingLinks(v.id)} />
          ))}
        </div>
      </section>

      {d.supersessions_out.length ? (
        <section aria-label="Sections this document amends" className="mt-14">
          <SectionTitle>Sections this document amends</SectionTitle>
          <AmendmentList links={d.supersessions_out} documentId={d.id} />
        </section>
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
    </Page>
  );
}

function useDocAction(documentId: string) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  return useMutation({
    mutationFn: ({ url, body }: { url: string; body?: unknown }) => api.post<ActionResult>(url, body),
    onSuccess: (result) => {
      notify(result.message);
      void queryClient.invalidateQueries({ queryKey: queryKeys.document(documentId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.documents });
      void queryClient.invalidateQueries({ queryKey: queryKeys.supersessions });
    },
    onError: (err) => notify("Action failed", { description: errorMessage(err), tone: "error" }),
  });
}

function Meta({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="mono-label text-muted">{label}</dt>
      <dd className="mt-1 text-sm">{children}</dd>
    </div>
  );
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
    <Card className={clsx("p-6", v.is_current && "border-green")}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <h3 className="text-feature">Version {v.version_label}</h3>
          <StatusBadge status={v.status} />
          {v.is_current ? <Badge tone="success">In force</Badge> : null}
          {processing ? (
            <Badge>Processing…</Badge>
          ) : v.ingest_status === "failed" ? (
            <Badge tone="danger">Processing failed</Badge>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {v.status === "draft" && v.needs_ocr_acknowledgement ? (
            <Button
              variant="outline"
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
              <Check className="h-4 w-4" /> Approve
            </Button>
          ) : null}
          {v.status === "draft" && !processing ? (
            <Button variant="link" size="sm" onClick={() => action.mutate({ url: `${base}/reingest` })}>
              <RefreshCw className="h-4 w-4" /> Re-process
            </Button>
          ) : null}
          {v.status !== "retired" && v.status !== "draft" && canApprove ? (
            <Button variant="link" size="sm" onClick={() => setRetireOpen(true)}>
              <Archive className="h-4 w-4" /> Retire
            </Button>
          ) : null}
        </div>
      </div>

      <dl className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-6">
        <Meta label="Effective">{formatDate(v.effective_from)}</Meta>
        <Meta label="Review due">
          <span
            className={clsx(reviewDays !== null && reviewDays < 0 && v.status === "approved" && "text-error")}
          >
            {formatDate(v.review_due)}
          </span>
        </Meta>
        <Meta label="Approved">{v.approved_at ? formatDateTime(v.approved_at) : "—"}</Meta>
        <Meta label="Clauses">{v.chunk_count}</Meta>
        <Meta label="Parsed with">
          {v.parser ?? "—"}
          {v.page_count ? ` · ${String(v.page_count)} p.` : ""}
        </Meta>
        <Meta label="OCR">
          {v.ocr_min_confidence !== null ? percent(v.ocr_min_confidence) : "not scanned"}
        </Meta>
      </dl>
      <p className="mt-4 truncate font-mono text-xs text-muted">{v.original_filename}</p>
      {v.change_summary ? <p className="mt-3 text-sm">{v.change_summary}</p> : null}

      {v.ingest_error ? (
        <div className="mt-4">
          <ErrorNotice title="Processing failed" message={v.ingest_error} />
        </div>
      ) : null}
      {warnings.length ? (
        <ul className="mt-4 space-y-2">
          {warnings.map((w, i) => (
            <li key={i} className="rounded-sm border border-coral-soft bg-coral-wash px-4 py-3 text-sm">
              <span className="mono-label mr-2 text-coral-ink">
                {w.code === "ocr_low_confidence" ? "Check OCR" : "Warning"}
              </span>
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
          className="mt-5 inline-flex min-h-9 items-center gap-1.5 text-sm underline decoration-hairline underline-offset-4 hover:decoration-ink"
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
        <div className="flex items-center justify-end gap-4">
          <Button variant="link" onClick={() => setRetireOpen(false)}>
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
        <div className="mb-6 space-y-3">
          <p className="mono-label text-ink">Amendments found in this document</p>
          <ul className="space-y-2">
            {links.map((l) => (
              <li key={l.id} className="rounded-sm border border-coral-soft bg-coral-wash px-4 py-3 text-sm">
                Replaces <span className="font-medium">{l.target_doc_code}</span>
                {l.target_section_path ? ` ${sectionLabel(l.target_section_path)}` : " (whole document)"}
                {l.hides_sections.length ? (
                  <span className="block text-micro text-muted">
                    Will hide: {l.hides_sections.map(sectionLabel).join(", ")}
                  </span>
                ) : null}
                {l.evidence ? (
                  <span className="mt-1 block text-micro italic text-muted">“{l.evidence}”</span>
                ) : null}
              </li>
            ))}
          </ul>
          <label className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="checkbox"
              checked={confirmLinks}
              onChange={(e) => setConfirmLinks(e.target.checked)}
              className="h-4 w-4 accent-black"
            />
            Also confirm these amendments (the amended clauses stop appearing in answers)
          </label>
        </div>
      ) : null}
      <div className="flex items-center justify-end gap-4">
        <Button variant="link" onClick={() => onOpenChange(false)}>
          Cancel
        </Button>
        <Button loading={pending} onClick={() => onApprove(links.length > 0 && confirmLinks)}>
          <Check className="h-4 w-4" /> Approve
        </Button>
      </div>
    </Dialog>
  );
}

function ChunkList({ documentId, versionId }: { documentId: string; versionId: string }) {
  const chunks = useQuery(queries.chunks(documentId, versionId));
  if (chunks.isLoading) return <Skeleton className="mt-3 h-24 w-full" />;
  if (chunks.isError) return <ErrorNotice message={errorMessage(chunks.error)} />;
  return (
    <RuleList className="mt-3 max-h-[28rem] overflow-y-auto">
      {(chunks.data ?? [])
        .filter((c) => !c.heading.includes(" — row "))
        .map((c) => (
          <li key={c.id} className="py-3">
            <p className="flex flex-wrap items-baseline gap-x-3">
              <span className="mono-label text-muted">{sectionLabel(c.section_path)}</span>
              <span className="font-medium">{c.heading}</span>
              <span className="mono-label text-muted">
                p.{c.page_start} · {c.token_count} tokens{c.is_table ? " · table" : ""}
              </span>
            </p>
            <div className="prose-source mt-1 text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{c.text}</ReactMarkdown>
            </div>
          </li>
        ))}
    </RuleList>
  );
}
