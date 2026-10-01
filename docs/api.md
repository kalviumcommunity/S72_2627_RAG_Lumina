# Lumina API Reference (v1)

Base URL: `/api/v1`. Interactive documentation with request/response schemas: **`/docs`** (not served
when `APP_ENV=prod`). The machine-readable schema is `/api/v1/openapi.json` (also committed as
`frontend/src/lib/openapi.json`, from which the web app's types are generated).

**Authentication.** Every endpoint except `/health`, `/auth/config`, `/auth/dev-users`,
`/auth/dev-login` and the OIDC redirects needs `Authorization: Bearer <token>`. Tokens last
`SESSION_IDLE_MINUTES` (15) and are refreshed with `POST /auth/refresh`.

**Roles** are ordered `clinician < author < approver < admin`; "author+" means author, approver or admin.

**Errors** always look like `{"error": {"code": "...", "message": "...", "details": ...}}` with 401
(sign in), 403 (role), 404, 409 (conflict / duplicate), 422 (validation), 429 (rate limit, with
`Retry-After`), 500.

Every endpoint below is exercised by `backend/tests/integration/test_api_endpoints.py`, which also
fails if an endpoint is added without a test.

---

## Health and sign-in

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | public | Database + pgvector, job mode, LLM reachability (cached 60 s), model ids, PII engine. `status`: ok / degraded / down |
| GET | `/auth/config` | public | `dev_auth`, `oidc_enabled`, `session_idle_minutes`, answer model |
| GET | `/auth/dev-users` | public (demo only) | Seeded demo users; 404 when `DEV_AUTH=false` |
| POST | `/auth/dev-login` | public (demo only) | `{email}` → token + user |
| POST | `/auth/refresh` | any | New token for the current user |
| GET | `/auth/me` | any | Current user |
| GET | `/auth/oidc/login` | public | Redirect to the hospital identity provider (404 when not configured) |
| GET | `/auth/oidc/callback` | public | Completes SSO and redirects to `/auth/callback#token=…` (the web app exchanges it) |

## Questions

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/query` | any | `{question, branch_id?}` → full `QueryResponse` (below). Rate-limited per user |
| POST | `/query/stream` | any | Same, as server-sent events: `route` → `sources` → `answer` → `done` (or `error`). Preferred: the question stays out of URLs |
| GET | `/query/stream?q=` | any | SSE over GET for EventSource clients (access logs never record the query string) |
| GET | `/query/history?limit=` | any | Your recent questions (redacted), 1–50 |

`QueryResponse` (abridged):

```json
{
  "query_id": "…", "route": "answer", "outcome": "answered",
  "answer": "Stop the infusion for 1 hour, then restart at a rate reduced by 3 units/kg/h [S1].",
  "citations": [{"marker": "S1", "chunk_id": "…", "doc_code": "C-2026-09", "section_path": "2",
                 "version": "1", "effective_from": "2026-09-01",
                 "amends": [{"doc_code": "P-ICU-07", "section_path": "4.2"}], "supported": true}],
  "quick_values": [{"label": "Hold", "value": "1 hour", "source": "S1"}],
  "conflicts": [], "escalation": null, "sources": ["…"],
  "generation_mode": "llm", "verification": {"claims": 2, "supported": 1, "judge": "llm"},
  "redacted_question": "…", "pii_redacted": false,
  "latency_ms": 2140, "timings_ms": {"route": 310, "retrieve": 420, "generate": 900, "verify": 480, "total": 2140},
  "disclaimer": "Supports, does not replace, clinical judgement."
}
```

`route` is `answer | clarify | out_of_scope | high_risk`; `outcome` is `answered | partial | abstained`.
When abstaining, `escalation` has `reason` (`not_found | high_risk | out_of_scope | clarify | unavailable`),
a `message`, `contacts` to call and, for clarify, a `clarifying_question`.

## Sources and contacts

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/sources/{chunk_id}` | any (drafts: author+) | The clause with its whole document outline, version status, superseded-by / newer-version / amends information |
| GET | `/sources/{version_id}/file` | any (drafts and retired files: author+) | The original approved file |
| GET | `/contacts?branch_id=` | any | Escalation directory for your branch plus network-wide contacts |

## Documents and amendments

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/documents?status=&doc_type=&department_id=&review_overdue=&q=` | author+ | Documents with versions, current version, next review date |
| GET | `/documents/{id}` | author+ | One document plus the amendment links it makes and receives |
| POST | `/documents/extract-metadata` | author+ | Multipart `file` → code, version, dates, title read from its header (nothing stored) |
| POST | `/documents` | author+ | Multipart upload of a new document or version (always a draft); 409 for a duplicate file or version |
| GET | `/documents/{id}/versions/{vid}/chunks` | author+ | The indexed clauses of a version |
| POST | `/documents/{id}/versions/{vid}/acknowledge-ocr` | author+ | Confirm low-confidence OCR text was checked |
| POST | `/documents/{id}/versions/{vid}/reingest` | author+ | Re-process a draft (409 while it is already being processed) |
| POST | `/documents/{id}/versions/{vid}/approve` | approver+ | `{confirm_suggested_supersessions}` — make a draft visible to clinicians |
| POST | `/documents/{id}/versions/{vid}/retire` | approver+ | Withdraw a version from answers |
| GET | `/supersessions?confirmed=` | author+ | Amendment links with the clauses each one hides |
| POST | `/supersessions` | approver+ | Add a link: source version → target document (+ section), effective date |
| PATCH | `/supersessions/{id}` | approver+ | Confirm / edit a link |
| DELETE | `/supersessions/{id}` | approver+ | Reject (remove) a link |

## Feedback and conflicts

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/feedback` | any (own answers) | `{query_id, kind: wrong\|outdated\|unhelpful\|helpful, comment?}`; routed to the cited document's owner |
| GET | `/feedback/inbox?include_resolved=` | author+ | Reports routed to you (admins: all) |
| PATCH | `/feedback/{id}` | routed owner or admin | `{status: acknowledged\|resolved, resolution_note}` |
| GET | `/conflicts?status=` | author+ | Disagreements between current documents, both sides |
| PATCH | `/conflicts/{id}` | author+ | `{status: open\|resolved\|dismissed, resolution_note}` |

## Administration

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/admin/stats?days=` | admin | Usage, abstention, latency percentiles, top/unanswered questions, cited documents, overdue reviews, work queues, daily counts |
| GET | `/admin/overview?days=` | admin | Admin page data: **AI usage** (configuration, generation modes, deciding layer, verifier results, stage timings, LLM calls per stage since start, recent decisions with full trace), **usage per user**, and all documents, amendments, conflicts and feedback |
| GET | `/admin/audit?from=&to=&action=&format=json\|csv&limit=` | admin | Audit events, newest first; CSV download |
| GET | `/admin/audit/verify` | admin | Re-compute the hash chain; reports the first broken entry |
| GET | `/admin/reference-data` | author+ | Branches, departments, users, document types (upload form) |
