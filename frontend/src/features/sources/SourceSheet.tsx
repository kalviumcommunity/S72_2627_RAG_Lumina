import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ExternalLink, FileText, GitMerge, History, ScanText, TriangleAlert } from "lucide-react";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Sheet } from "../../components/ui/Sheet";
import { Skeleton } from "../../components/ui/Skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/Tabs";
import { useToast } from "../../components/ui/Toast";
import { api, errorMessage } from "../../lib/api";
import { daysUntil, formatDate, percent, sectionLabel } from "../../lib/format";
import type { Source } from "../../lib/types";
import { PdfViewer, type HighlightBox } from "./PdfViewer";
import { VersionBadge } from "./VersionBadge";

/** Opens the cited clause inside its whole document, highlighted and scrolled into view.
 *  Bottom sheet on phones, side panel on desktop. */
export function SourceSheet({ chunkId, onClose }: { chunkId: string | null; onClose: () => void }) {
  const source = useQuery({
    queryKey: ["source", chunkId],
    queryFn: () => api.get<Source>(`/sources/${chunkId ?? ""}`),
    enabled: chunkId !== null,
  });
  const data = source.data;

  return (
    <Sheet
      open={chunkId !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={
        data ? (
          <span className="flex items-center gap-2">
            <FileText className="h-5 w-5 shrink-0 text-accent" aria-hidden />
            {data.doc_code} {sectionLabel(data.section_path)}
          </span>
        ) : (
          "Source"
        )
      }
      description={data?.title}
      footer={data ? <OpenOriginal source={data} /> : undefined}
    >
      {source.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : source.isError ? (
        <ErrorNotice title="Could not open this source" message={errorMessage(source.error)} />
      ) : data ? (
        <SourceBody source={data} />
      ) : null}
    </Sheet>
  );
}

function SourceBody({ source }: { source: Source }) {
  const reviewDays = source.review_due ? daysUntil(source.review_due) : null;
  const boxes: HighlightBox[] = ((source.bbox?.boxes as HighlightBox[] | undefined) ?? []).filter(
    (b) => typeof b.page === "number",
  );
  const isPdf = source.mime_type === "application/pdf";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <VersionBadge
          version={source.version}
          effectiveFrom={source.effective_from}
          status={source.status}
          current={source.is_current}
        />
        <Badge>{source.doc_type.replace("_", " ")}</Badge>
        {reviewDays !== null ? (
          <Badge tone={reviewDays < 0 ? "danger" : "neutral"}>
            {reviewDays < 0
              ? `Review overdue by ${String(-reviewDays)} days`
              : `Review due ${formatDate(source.review_due)}`}
          </Badge>
        ) : null}
        {source.ocr_min_confidence !== null ? (
          <Badge tone={source.ocr_min_confidence < 0.8 ? "amber" : "neutral"}>
            <ScanText className="h-3 w-3" aria-hidden /> Scanned · OCR {percent(source.ocr_min_confidence)}
          </Badge>
        ) : null}
      </div>

      {source.superseded_by.length ? (
        <Banner tone="amber" icon={<History className="h-4 w-4" aria-hidden />}>
          This clause has been superseded by{" "}
          {source.superseded_by.map((s, i) => (
            <span key={s.version_id}>
              {i > 0 ? ", " : ""}
              <strong>
                {s.doc_code} v{s.version}
              </strong>{" "}
              (effective {formatDate(s.effective_from)})
            </span>
          ))}
          . ProtoCite never cites superseded text in answers.
        </Banner>
      ) : null}
      {source.newer_version && !source.is_current ? (
        <Banner tone="amber" icon={<TriangleAlert className="h-4 w-4" aria-hidden />}>
          A newer version is in force: <strong>v{source.newer_version.version}</strong>, effective{" "}
          {formatDate(source.newer_version.effective_from)}.
        </Banner>
      ) : null}
      {source.amends.length ? (
        <Banner tone="accent" icon={<GitMerge className="h-4 w-4" aria-hidden />}>
          This document amends{" "}
          {source.amends
            .map((a) => `${a.doc_code}${a.section_path ? ` ${sectionLabel(a.section_path)}` : ""}`)
            .join(", ")}
          .
        </Banner>
      ) : null}

      {isPdf ? (
        <Tabs defaultValue="text">
          <TabsList>
            <TabsTrigger value="text">Clause text</TabsTrigger>
            <TabsTrigger value="pdf">Original page</TabsTrigger>
          </TabsList>
          <TabsContent value="text" className="mt-3">
            <Outline source={source} />
          </TabsContent>
          <TabsContent value="pdf" className="mt-3">
            <PdfViewer
              fileUrl={source.file_url}
              initialPage={source.page_start}
              boxes={boxes}
              clauseText={source.text}
            />
          </TabsContent>
        </Tabs>
      ) : (
        <Outline source={source} />
      )}
    </div>
  );
}

function Banner({
  tone,
  icon,
  children,
}: {
  tone: "amber" | "accent";
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div
      className={clsx(
        "flex items-start gap-2 rounded-xl border px-3 py-2 text-sm",
        tone === "amber" ? "border-amber-border bg-amber-soft" : "border-accent/30 bg-accent-soft",
      )}
    >
      <span className={clsx("mt-0.5", tone === "amber" ? "text-amber" : "text-accent-text")}>{icon}</span>
      <p>{children}</p>
    </div>
  );
}

/** The whole document, clause by clause; the cited clause is highlighted and scrolled into view. */
function Outline({ source }: { source: Source }) {
  const cited = useRef<HTMLElement>(null);
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    cited.current?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  }, [source.chunk_id]);

  const items = source.outline.length
    ? source.outline
    : [
        {
          chunk_id: source.chunk_id,
          section_path: source.section_path,
          heading: source.heading,
          text: source.text,
          is_table: source.is_table,
          page_start: source.page_start,
        },
      ];
  return (
    <div className="space-y-2">
      {items.map((item) => {
        const isCited = item.chunk_id === source.chunk_id;
        return (
          <section
            key={item.chunk_id}
            ref={isCited ? cited : undefined}
            aria-current={isCited ? "true" : undefined}
            className={clsx(
              "scroll-mt-4 rounded-xl border px-3 py-2",
              isCited ? "border-highlight-border bg-highlight" : "border-transparent",
            )}
          >
            <h4 className="flex flex-wrap items-center gap-2 text-sm font-semibold">
              <span className="text-accent-text">{sectionLabel(item.section_path)}</span>
              {item.heading}
              {isCited ? <Badge tone="amber">Cited clause</Badge> : null}
            </h4>
            <div className="prose-source">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.text}</ReactMarkdown>
            </div>
          </section>
        );
      })}
    </div>
  );
}

function OpenOriginal({ source }: { source: Source }) {
  const { notify } = useToast();
  const open = async () => {
    try {
      const blob = await api.blob(source.file_url.replace(/^\/api\/v1/, ""));
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      notify("Could not open the original file", { description: errorMessage(err), tone: "error" });
    }
  };
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-xs text-muted">Approved institutional document · synthetic demo corpus</span>
      <Button size="sm" variant="secondary" onClick={() => void open()}>
        <ExternalLink className="h-4 w-4" /> Open original
      </Button>
    </div>
  );
}
