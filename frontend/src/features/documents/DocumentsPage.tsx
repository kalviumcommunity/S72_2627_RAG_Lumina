import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Search, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";

import { Page, PageHeader } from "../../app/layout/Page";
import { paths } from "../../app/paths";
import { Badge, TaxonomyChip } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { EmptyState, ErrorNotice } from "../../components/ui/EmptyState";
import { Input } from "../../components/ui/Field";
import { Segmented } from "../../components/ui/Segmented";
import { Skeleton } from "../../components/ui/Skeleton";
import { errorMessage } from "../../lib/api";
import { daysUntil, formatDate } from "../../lib/format";
import { queries } from "../../lib/queries";
import type { DocType, DocumentSummary } from "../../lib/types";
import { DOC_TYPE_LABEL } from "./labels";
import { UploadDialog } from "./UploadDialog";

type Filter = "all" | "pending" | "overdue";
const isProcessing = (d: DocumentSummary) =>
  d.versions.some((v) => ["pending", "processing"].includes(v.ingest_status));

/** Every protocol, guideline and circular with its versions and review state; upload new ones. */
export function DocumentsPage() {
  const [search, setSearch] = useState("");
  const [type, setType] = useState<DocType | "all">("all");
  const [params, setParams] = useSearchParams();
  const initial = params.get("filter");
  const [filter, setFilterState] = useState<Filter>(
    initial === "pending" || initial === "overdue" ? initial : "all",
  );
  const setFilter = (next: Filter) => {
    setFilterState(next);
    setParams(next === "all" ? {} : { filter: next }, { replace: true });
  };
  const [uploadOpen, setUploadOpen] = useState(false);
  const docs = useQuery({
    ...queries.documents(),
    // Keep polling while any version is still being processed.
    refetchInterval: (query) => (query.state.data?.some(isProcessing) ? 2000 : false),
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

  const all = docs.data ?? [];
  const pendingCount = all.filter((d) => d.versions.some((v) => v.status === "draft")).length;
  const overdueCount = all.filter((d) => d.review_overdue).length;

  return (
    <Page title="Library">
      <PageHeader
        eyebrow="Library"
        title="Documents"
        description="Every protocol, drug guideline and circular with its versions and review dates. Only the approved version in force is ever used in answers."
        actions={
          <Button onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4" /> Upload document
          </Button>
        }
      />

      <div className="mb-8 space-y-4">
        <div className="relative max-w-xl">
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
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <Segmented
            label="Status"
            value={filter}
            onChange={setFilter}
            options={[
              ["all", `All (${String(all.length)})`],
              ["pending", `Awaiting approval (${String(pendingCount)})`],
              ["overdue", `Review overdue (${String(overdueCount)})`],
            ]}
          />
          <Segmented
            label="Document type"
            value={type}
            onChange={setType}
            options={[["all", "All types"], ...(Object.entries(DOC_TYPE_LABEL) as [DocType, string][])]}
          />
        </div>
      </div>

      {docs.isLoading ? (
        <div className="space-y-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : docs.isError ? (
        <ErrorNotice message={errorMessage(docs.error)} />
      ) : rows.length === 0 ? (
        <EmptyState title="No documents match">Change the filters, or upload a document.</EmptyState>
      ) : (
        <div className="border-t border-primary">
          <div className="mono-label hidden grid-cols-[minmax(0,2.4fr)_1fr_1fr_1fr_1.25rem] gap-6 border-b border-hairline py-3 text-muted lg:grid">
            <span>Document</span>
            <span>In force</span>
            <span>Status</span>
            <span>Review due</span>
            <span />
          </div>
          <ul className="divide-y divide-hairline border-b border-hairline">
            {rows.map((doc) => (
              <DocumentRow key={doc.id} doc={doc} />
            ))}
          </ul>
        </div>
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
    </Page>
  );
}

function DocumentRow({ doc }: { doc: DocumentSummary }) {
  const current = doc.versions.find((v) => v.id === doc.current_version_id);
  const drafts = doc.versions.filter((v) => v.status === "draft").length;
  const days = doc.next_review_due ? daysUntil(doc.next_review_due) : null;
  return (
    <li>
      <Link
        to={paths.document(doc.id)}
        className="group grid gap-x-6 gap-y-3 py-5 text-ink no-underline lg:grid-cols-[minmax(0,2.4fr)_1fr_1fr_1fr_1.25rem] lg:items-center"
      >
        <span className="min-w-0">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm">{doc.doc_code}</span>
            <TaxonomyChip>{DOC_TYPE_LABEL[doc.doc_type]}</TaxonomyChip>
          </span>
          <span className="mt-1 block text-lg leading-snug group-hover:underline">{doc.title}</span>
          <span className="mt-0.5 block text-micro text-muted">
            {doc.department?.name ?? "No department"} ·{" "}
            {doc.applies_to_all_branches
              ? "all branches"
              : `${doc.branches.map((b) => b.name).join(", ")} only`}
            {doc.owner ? ` · owner ${doc.owner.display_name}` : ""}
          </span>
        </span>
        <span className="text-sm">
          {current ? (
            <>
              v{current.version_label}
              <span className="block text-micro text-muted">since {formatDate(current.effective_from)}</span>
            </>
          ) : (
            <span className="text-muted">None in force</span>
          )}
        </span>
        <span className="flex flex-wrap gap-1.5">
          {current ? <Badge tone="success">Approved</Badge> : null}
          {drafts ? <Badge tone="amber">{drafts} awaiting approval</Badge> : null}
          {isProcessing(doc) ? <Badge>Processing</Badge> : null}
        </span>
        <span className="text-sm">
          {doc.next_review_due ? (
            <>
              {formatDate(doc.next_review_due)}
              {days !== null && days < 0 ? (
                <span className="block text-micro text-error">{-days} days overdue</span>
              ) : null}
            </>
          ) : (
            <span className="text-muted">—</span>
          )}
        </span>
        <ArrowRight
          className="hidden h-4 w-4 text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-ink lg:block"
          aria-hidden
        />
      </Link>
    </li>
  );
}
