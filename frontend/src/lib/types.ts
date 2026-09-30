/**
 * API types, generated from the backend's OpenAPI schema (src/lib/openapi.json → api-schema.d.ts).
 * Regenerate with `python -m scripts.export_openapi` (backend) then `pnpm gen:types`; a backend
 * test fails if the committed schema drifts from the API.
 */
import type { components } from "./api-schema";

type S = components["schemas"];

export type QueryRoute = S["QueryResponse"]["route"];
export type AnswerOutcome = S["QueryResponse"]["outcome"];
export type QueryResponse = S["QueryResponse"];
export type Citation = S["CitationOut"];
export type QuickValue = S["QuickValue"];
export type SourceCard = S["SourceCard"];
export type ConflictInfo = S["ConflictOut"];
export type ConflictSide = S["ConflictSide"];
export type Escalation = S["EscalationOut"];
export type Contact = S["ContactOut"];
export interface RouteEvent {
  route: QueryRoute;
  reason: string;
  redacted_question: string;
  pii_redacted: boolean;
}
export type HistoryItem = S["HistoryItem"];
export type DocRef = S["DocRef"];

export type Source = S["SourceOut"];
export type OutlineItem = S["OutlineItem"];
export type SupersededByRef = S["SupersededByRef"];

export type User = S["UserOut"];
export type Branch = S["BranchOut"];
export type Department = S["DepartmentOut"];
export type AuthConfig = S["AuthConfig"];
export type TokenResponse = S["TokenResponse"];

export type DocumentSummary = S["DocumentOut"];
export type DocumentDetail = S["DocumentDetail"];
export type Version = S["VersionOut"];
export type Supersession = S["SupersessionOut"];
export type ChunkPreview = S["ChunkOut"];
export type UploadResult = S["UploadResult"];
export type ActionResult = S["ActionResult"];
export type ExtractedMetadata = S["ExtractedMetadataOut"];
export type DocType = S["DocumentOut"]["doc_type"];
export type VersionStatus = S["VersionOut"]["status"];

export type Feedback = S["FeedbackOut"];
export type FeedbackKind = S["FeedbackCreate"]["kind"];
export type Stats = S["StatsOut"];
export type AdminConflict = S["ConflictAdminOut"];
export type AuditEvent = S["AuditEventOut"];
export type AuditVerify = S["AuditVerifyOut"];
export type ReferenceData = S["ReferenceData"];
export type ContactEntry = S["ContactAdminOut"];

export type Role = User["role"];

/** Events of the answer stream, in order: route → sources → answer → done (or error). */
export type StreamEvent =
  | { event: "route"; data: RouteEvent }
  | { event: "sources"; data: { sources: SourceCard[]; timings_ms: Record<string, number> } }
  | { event: "answer"; data: QueryResponse }
  | { event: "done"; data: { query_id: string } }
  | { event: "error"; data: { code: string; message: string } };
