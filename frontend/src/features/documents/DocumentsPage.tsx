import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ChevronRight, FileStack, Loader2, Search, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { AdminPage, PageHeader } from "../../app/layout/AppShell";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Input, Select } from "../../components/ui/Field";
import { Skeleton } from "../../components/ui/Skeleton";
import { api, errorMessage } from "../../lib/api";
import { daysUntil, formatDate } from "../../lib/format";
import type { DocumentSummary, Version } from "../../lib/types";
import { DOC_TYPE_LABEL } from "./labels";
import { StatusBadge } from "./shared";
import { UploadDialog } from "./UploadDialog";

type Filter = "all" | "pending" | "overdue";

export function DocumentsPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [type, setType] = useState("all");
  const [params] = useSearchParams();
  const initial = params.get("filter");
  const [filter, setFilter] = useState<Filter>(
    initial === "pending" || initial === "overdue" ? initial : "all",
  );
  const [uploadOpen, setUploadOpen] = useState(false);
  const docs = useQuery({
    queryKey: ["documents"],
    queryFn: () => api.get<DocumentSummary[]>("/documents"),
    // Keep polling while any version is still being processed.
    refetchInterval: (query) =>
      query.state.data?.some((d) =>
        d.versions.some((v) => ["pending", "processing"].includes(v.ingest_status)),
      )
        ? 2000
        : false,
  });

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (docs.data ?? []).filter((d) => {
      if (type !== "all" && d.doc_type !== type) return false;
      if (q && !`${d.doc_code} ${d.title}`.toLowerCase().includes(q)) return false;
      if (filter === "pending" && !d.versions.some((v) => v.status === "draft")) return false;
      if (filter === "overdue" && !d.review_overdue) return false;
      return true;
    });
  }, [docs.data, search, type, filter]);

  const pendingCount = (docs.data ?? []).filter((d) => d.versions.some((v) => v.status === "draft")).length;
  const overdueCount = (docs.data ?? []).filter((d) => d.review_overdue).length;

  return (
    <AdminPage>
      <PageHeader
        title="Documents"
        description="Every protocol, drug guideline and circular, with its versions, effective dates and review status. Only approved, current versions are ever used in answers."
        actions={
          <Button onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" /> Upload document
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
            aria-hidden
          />
          <Input
            aria-label="Search documents"
            placeholder="Search by code or title"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
          />
        </div>
        <Select
          aria-label="Document type"
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="w-48"
        >
          <option value="all">All types</option>
          {Object.entries(DOC_TYPE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <div
          className="flex gap-1 rounded-xl border border-border bg-surface-2 p-1"
          role="group"
          aria-label="Filter"
        >
          {(
            [
              ["all", "All"],
              ["pending", `Awaiting approval (${String(pendingCount)})`],
              ["overdue", `Review overdue (${String(overdueCount)})`],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={filter === value}
              onClick={() => setFilter(value)}
              className={clsx(
                "min-h-9 rounded-lg px-3 text-sm",
                filter === value ? "bg-surface font-medium shadow-card" : "text-muted hover:text-text",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {docs.isLoading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : docs.isError ? (
        <ErrorNotice message={errorMessage(docs.error)} />
      ) : rows.length === 0 ? (
        <EmptyState icon={<FileStack className="h-8 w-8" />} title="No documents match">
          Change the filters, or upload a document.
        </EmptyState>
      ) : (
        <Card className="overflow-hidden">
          <table className="w-full text-left text-sm">
            <thead className="hidden border-b border-border bg-surface-2 text-xs uppercase tracking-wide text-muted md:table-header-group">
              <tr>
                <th className="px-4 py-2.5 font-medium">Document</th>
                <th className="px-4 py-2.5 font-medium">In force</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
                <th className="px-4 py-2.5 font-medium">Review due</th>
                <th className="px-4 py-2.5 font-medium">Owner</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {rows.map((doc) => (
                <DocumentRow
                  key={doc.id}
                  doc={doc}
                  onOpen={() => void navigate(`/admin/documents/${doc.id}`)}
                />
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </AdminPage>
  );
}

function DocumentRow({ doc, onOpen }: { doc: DocumentSummary; onOpen: () => void }) {
  const current: Version | undefined = doc.versions.find((v) => v.id === doc.current_version_id);
  const drafts = doc.versions.filter((v) => v.status === "draft");
  const processing = doc.versions.some((v) => ["pending", "processing"].includes(v.ingest_status));
  const days = doc.next_review_due ? daysUntil(doc.next_review_due) : null;
  return (
    <tr className="cursor-pointer hover:bg-surface-2" onClick={onOpen}>
      <td className="px-4 py-3">
        <Link
          to={`/admin/documents/${doc.id}`}
          onClick={(e) => e.stopPropagation()}
          className="font-mono text-sm font-semibold text-accent-text"
        >
          {doc.doc_code}
        </Link>
        <p className="font-medium text-text">{doc.title}</p>
        <p className="text-xs text-muted">
          {DOC_TYPE_LABEL[doc.doc_type]}
          {doc.department ? ` · ${doc.department.name}` : ""}
          {doc.applies_to_all_branches
            ? " · all branches"
            : ` · ${doc.branches.map((b) => b.name).join(", ")} only`}
        </p>
      </td>
      <td className="px-4 py-3 align-top md:align-middle">
        {current ? (
          <span>
            v{current.version_label}
            <span className="block text-xs text-muted">since {formatDate(current.effective_from)}</span>
          </span>
        ) : (
          <span className="text-muted">None yet</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap gap-1">
          {current ? <StatusBadge status="approved" /> : null}
          {drafts.length ? <Badge tone="accent">{drafts.length} awaiting approval</Badge> : null}
          {processing ? (
            <Badge>
              <Loader2 className="h-3 w-3 animate-spin" aria-hidden /> Processing
            </Badge>
          ) : null}
        </div>
      </td>
      <td className="px-4 py-3">
        {doc.next_review_due ? (
          <span className={clsx(days !== null && days < 0 && "font-medium text-danger")}>
            {formatDate(doc.next_review_due)}
            {days !== null && days < 0 ? <span className="block text-xs">{-days} days overdue</span> : null}
          </span>
        ) : (
          <span className="text-muted">—</span>
        )}
      </td>
      <td className="px-4 py-3 text-muted">{doc.owner?.display_name ?? "—"}</td>
      <td className="pr-3">
        <ChevronRight className="h-4 w-4 text-muted" aria-hidden />
      </td>
    </tr>
  );
}
