import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { useQuery } from "@tanstack/react-query";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { Button } from "../../components/ui/Button";
import { ErrorNotice } from "../../components/ui/EmptyState";
import { Skeleton } from "../../components/ui/Skeleton";
import { api, errorMessage } from "../../lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

export interface HighlightBox {
  page: number;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (ch) => `&#${String(ch.charCodeAt(0))};`);
}

/** Loads the original PDF with the session token and highlights the cited clause.
 *  Scanned pages: OCR bounding boxes are drawn over the page image.
 *  Text PDFs: text-layer items that belong to the clause are marked. */
export function PdfViewer({
  fileUrl,
  initialPage,
  boxes,
  clauseText,
}: {
  fileUrl: string;
  initialPage: number;
  boxes: HighlightBox[];
  clauseText: string;
}) {
  const path = fileUrl.replace(/^\/api\/v1/, "");
  const file = useQuery({
    queryKey: ["source-file", path],
    queryFn: () => api.blob(path),
    staleTime: Infinity,
  });
  const container = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(600);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(initialPage);
  // Jump to the cited page when a different clause is opened (state adjusted during render, not in an effect).
  const [shownInitial, setShownInitial] = useState(initialPage);
  if (shownInitial !== initialPage) {
    setShownInitial(initialPage);
    setPage(initialPage);
  }
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(280, Math.floor(entry.contentRect.width)));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const normalisedClause = clauseText.replace(/\s+/g, " ").toLowerCase();
  const textRenderer = useCallback(
    ({ str }: { str: string }) => {
      const s = str.trim();
      const hit = s.length > 3 && normalisedClause.includes(s.replace(/\s+/g, " ").toLowerCase());
      return hit ? `<mark>${escapeHtml(str)}</mark>` : escapeHtml(str);
    },
    [normalisedClause],
  );

  if (file.isError)
    return <ErrorNotice title="Could not open the original file" message={errorMessage(file.error)} />;

  return (
    <div ref={container} className="w-full">
      {file.data ? (
        <Document
          file={file.data}
          onLoadSuccess={({ numPages }) => setPages(numPages)}
          loading={<Skeleton className="aspect-[1/1.41] w-full" />}
          error={<ErrorNotice title="Could not render the PDF" message="The file may be damaged." />}
        >
          <div className="relative overflow-hidden rounded-xl border border-border bg-white shadow-card">
            <Page
              pageNumber={page}
              width={width}
              renderAnnotationLayer={false}
              customTextRenderer={boxes.length ? undefined : textRenderer}
            />
            {boxes
              .filter((b) => b.page === page)
              .map((b, i) => (
                <div
                  key={i}
                  aria-hidden
                  className="pointer-events-none absolute rounded-md border-2 border-highlight-border bg-[rgb(255_214_10/0.28)]"
                  style={{
                    left: `${String(b.x0 * 100)}%`,
                    top: `${String(b.y0 * 100)}%`,
                    width: `${String((b.x1 - b.x0) * 100)}%`,
                    height: `${String((b.y1 - b.y0) * 100)}%`,
                  }}
                />
              ))}
          </div>
        </Document>
      ) : (
        <Skeleton className="aspect-[1/1.41] w-full" />
      )}
      {pages > 1 ? (
        <div className="mt-2 flex items-center justify-center gap-2 text-sm">
          <Button
            size="icon"
            variant="secondary"
            aria-label="Previous page"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span>
            Page {page} of {pages}
          </span>
          <Button
            size="icon"
            variant="secondary"
            aria-label="Next page"
            disabled={page >= pages}
            onClick={() => setPage(page + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
    </div>
  );
}
