/**
 * Server data, declared once: every query key and fetcher the app uses. Pages call
 * `useQuery(queries.documents())`; mutations invalidate with `queryKeys.*`. Sharing the same
 * definitions means two components asking for the same data share one request and one cache entry.
 */
import { queryOptions } from "@tanstack/react-query";

import { api } from "./api";
import type {
  AdminConflict,
  AuditEvent,
  AuthConfig,
  ChunkPreview,
  DocumentDetail,
  DocumentSummary,
  Feedback,
  HistoryItem,
  Overview,
  ReferenceData,
  Source,
  Stats,
  Supersession,
  User,
} from "./types";

export interface AuditFilters {
  from: string;
  to: string;
  action: string;
}

export const queryKeys = {
  authConfig: ["auth-config"] as const,
  devUsers: ["dev-users"] as const,
  history: ["query-history"] as const,
  documents: ["documents"] as const,
  document: (id: string) => ["document", id] as const,
  chunks: (versionId: string) => ["chunks", versionId] as const,
  referenceData: ["reference-data"] as const,
  supersessions: ["supersessions"] as const,
  conflicts: ["conflicts"] as const,
  feedback: ["feedback-inbox"] as const,
  source: (chunkId: string | null) => ["source", chunkId] as const,
  sourceFile: (path: string) => ["source-file", path] as const,
  stats: ["admin-stats"] as const,
  overview: ["admin-overview"] as const,
  audit: ["audit-events"] as const,
};

export const queries = {
  authConfig: () =>
    queryOptions({
      queryKey: queryKeys.authConfig,
      queryFn: () => api.get<AuthConfig>("/auth/config"),
      staleTime: 5 * 60_000,
    }),
  devUsers: () =>
    queryOptions({ queryKey: queryKeys.devUsers, queryFn: () => api.get<User[]>("/auth/dev-users") }),
  history: (limit = 5) =>
    queryOptions({
      queryKey: [...queryKeys.history, limit],
      queryFn: () => api.get<HistoryItem[]>("/query/history", { limit }),
    }),
  documents: () =>
    queryOptions({ queryKey: queryKeys.documents, queryFn: () => api.get<DocumentSummary[]>("/documents") }),
  document: (id: string) =>
    queryOptions({
      queryKey: queryKeys.document(id),
      queryFn: () => api.get<DocumentDetail>(`/documents/${id}`),
    }),
  chunks: (documentId: string, versionId: string) =>
    queryOptions({
      queryKey: queryKeys.chunks(versionId),
      queryFn: () => api.get<ChunkPreview[]>(`/documents/${documentId}/versions/${versionId}/chunks`),
    }),
  referenceData: () =>
    queryOptions({
      queryKey: queryKeys.referenceData,
      queryFn: () => api.get<ReferenceData>("/admin/reference-data"),
      staleTime: 5 * 60_000,
    }),
  supersessions: () =>
    queryOptions({
      queryKey: queryKeys.supersessions,
      queryFn: () => api.get<Supersession[]>("/supersessions"),
    }),
  conflicts: (show: "open" | "all") =>
    queryOptions({
      queryKey: [...queryKeys.conflicts, show],
      queryFn: () => api.get<AdminConflict[]>("/conflicts", show === "open" ? { status: "open" } : undefined),
    }),
  feedback: (includeResolved: boolean) =>
    queryOptions({
      queryKey: [...queryKeys.feedback, includeResolved],
      queryFn: () => api.get<Feedback[]>("/feedback/inbox", { include_resolved: includeResolved }),
    }),
  source: (chunkId: string | null) =>
    queryOptions({
      queryKey: queryKeys.source(chunkId),
      queryFn: () => api.get<Source>(`/sources/${chunkId ?? ""}`),
      enabled: chunkId !== null,
    }),
  sourceFile: (path: string) =>
    queryOptions({
      queryKey: queryKeys.sourceFile(path),
      queryFn: () => api.blob(path),
      staleTime: Infinity,
    }),
  stats: (days: number) =>
    queryOptions({
      queryKey: [...queryKeys.stats, days],
      queryFn: () => api.get<Stats>("/admin/stats", { days }),
      refetchInterval: 60_000,
    }),
  overview: (days: number) =>
    queryOptions({
      queryKey: [...queryKeys.overview, days],
      queryFn: () => api.get<Overview>("/admin/overview", { days }),
      refetchInterval: 60_000,
    }),
  audit: (filters: AuditFilters) =>
    queryOptions({
      queryKey: [...queryKeys.audit, filters],
      queryFn: () => api.get<AuditEvent[]>("/admin/audit", { ...filters, limit: 200 }),
    }),
};
