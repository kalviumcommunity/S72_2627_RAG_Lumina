import { useQuery } from "@tanstack/react-query";
import { clsx } from "clsx";
import { ExternalLink } from "lucide-react";
import { lazy, Suspense, useEffect, useRef, type ReactNode } from "react";
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
import { queries } from "../../lib/queries";
import type { Source } from "../../lib/types";
import { DOC_TYPE_LABEL } from "../documents/labels";
import type { HighlightBox } from "./PdfViewer";
import { VersionBadge } from "./VersionBadge";

// pdf.js is large and only needed once someone opens "Original page", so it loads on demand.
const PdfViewer = lazy(() => import("./PdfViewer").then((m) => ({ default: m.PdfViewer })));

/** Opens the cited clause inside its whole document, highlighted and scrolled into view.
 *  Bottom sheet on phones, side panel on desktop. */
export function SourceSheet({ chunkId, onClose }: { chunkId: string | null; onClose: () => void }) {
  const source = useQuery(queries.source(chunkId));
  const data = source.data;

  return (
    <Sheet
      open={chunkId !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      eyebrow={data ? `Source · ${DOC_TYPE_LABEL[data.doc_type]}` : "Source"}
      title={data ? `${data.doc_code} ${sectionLabel(data.section_path)}` : "Loading source"}
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
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <VersionBadge
          version={source.version}
          effectiveFrom={source.effective_from}
          status={source.status}
          current={source.is_current}
        />
        {reviewDays !== null ? (
          <Badge tone={reviewDays < 0 ? "danger" : "neutral"}>
            {reviewDays < 0
              ? `Review overdue by ${String(-reviewDays)} days`
              : `Review due ${formatDate(source.review_due)}`}
          </Badge>
        ) : null}
        {source.ocr_min_confidence !== null ? (
          <Badge tone={source.ocr_min_confidence < 0.8 ? "amber" : "neutral"}>
            Scanned · OCR {percent(source.ocr_min_confidence)}
          </Badge>
        ) : null}
      </div>

      {source.superseded_by.length ? (
        <Notice tone="coral" label="Superseded">
          This clause has been superseded by{" "}
          {source.superseded_by.map((s, i) => (
            <span key={s.version_id}>
              {i > 0 ? ", " : ""}
              <strong className="font-medium">
                {s.doc_code} v{s.version}
              </strong>{" "}
              (effective {formatDate(s.effective_from)})
            </span>
          ))}
          . Lumina never cites superseded text in answers.
        </Notice>
      ) : null}
      {source.newer_version && !source.is_current ? (
        <Notice tone="coral" label="Newer version">
          A newer version is in force:{" "}
          <strong className="font-medium">v{source.newer_version.version}</strong>, effective{" "}
          {formatDate(source.newer_version.effective_from)}.
        </Notice>
      ) : null}
      {source.amends.length ? (
        <Notice tone="blue" label="Amendment">
          This document amends{" "}
          {source.amends
            .map((a) => `${a.doc_code}${a.section_path ? ` ${sectionLabel(a.section_path)}` : ""}`)
            .join(", ")}
          .
        </Notice>
      ) : null}

      {isPdf ? (
        <Tabs defaultValue="text">
          <TabsList>
            <TabsTrigger value="text">Clause text</TabsTrigger>
            <TabsTrigger value="pdf">Original page</TabsTrigger>
          </TabsList>
          <TabsContent value="text" className="mt-5">
            <Outline source={source} />
          </TabsContent>
          <TabsContent value="pdf" className="mt-5">
            <Suspense fallback={<Skeleton className="h-[28rem] w-full" />}>
              <PdfViewer
                fileUrl={source.file_url}
                initialPage={source.page_start}
                boxes={boxes}
                clauseText={source.text}
              />
            </Suspense>
          </TabsContent>
        </Tabs>
      ) : (
        <Outline source={source} />
      )}
    </div>
  );
}

function Notice({ tone, label, children }: { tone: "coral" | "blue"; label: string; children: ReactNode }) {
  return (
    <div
      className={clsx(
        "rounded-sm border px-4 py-3 text-sm",
        tone === "coral" ? "border-coral-soft bg-coral-wash" : "border-blue/20 bg-blue-wash",
      )}
    >
      <p className={clsx("mono-label mb-1", tone === "coral" ? "text-coral-ink" : "text-blue")}>{label}</p>
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
    <div className="space-y-1">
      {items.map((item) => {
        const isCited = item.chunk_id === source.chunk_id;
        return (
          <section
            key={item.chunk_id}
            ref={isCited ? cited : undefined}
            aria-current={isCited ? "true" : undefined}
            className={clsx(
              "scroll-mt-4 rounded-sm px-4 py-3",
              isCited ? "border-l-4 border-green bg-green-wash" : "border-l-4 border-transparent",
            )}
          >
            <h4 className="flex flex-wrap items-center gap-2">
              <span className="mono-label text-muted">{sectionLabel(item.section_path)}</span>
              <span className="font-medium">{item.heading}</span>
              {isCited ? <Badge tone="success">Cited clause</Badge> : null}
            </h4>
            <div className="prose-source mt-1">
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
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-micro text-muted">Approved institutional document · synthetic demo corpus</span>
      <Button size="sm" variant="outline" onClick={() => void open()}>
        <ExternalLink className="h-4 w-4" /> Open original
      </Button>
    </div>
  );
}
