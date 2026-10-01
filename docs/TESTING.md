# Testing Lumina

Three layers, all runnable locally and in CI (`.github/workflows/ci.yml`).

| Layer | What it proves | Count | Command |
|---|---|---:|---|
| Backend unit | Pipeline logic without a database: routing rules, PII redaction, chunking, authority and supersession rules, verifier, extractive answers, metadata extraction, LLM budgets and fallbacks, audit hashing | 222 | `cd backend && uv run pytest tests/unit` |
| Backend API / integration | **Every `/api/v1` endpoint** against a real PostgreSQL + pgvector with the sample corpus ingested through the real pipeline (OCR included): allowed roles succeed, other roles get 401/403, validation errors, the full question pipeline, approvals changing answers, audit chain | 54 | `cd backend && uv run pytest tests/integration` |
| Frontend | **Every page and every component rendered on its own** against a mocked API (Vitest + Testing Library): it loads, shows its content, calls only the endpoints it should, and its main action works; the app frame, routes, redirects and design-system primitives | 121 | `cd frontend && pnpm test` |
| End-to-end | The built web app and the API running together in Chromium: every page as every role, section navigation, old-address redirects, the Ask flow, refusal, source viewer, Admin tabs, phone layout, installable PWA | 19 | `cd frontend && pnpm e2e` |

`make test` runs the backend and frontend suites; `make e2e` builds the UI and runs Playwright.

---

## Backend

Tests run with deterministic stand-ins so they need no downloads and no API key: hash embeddings,
a word-overlap re-ranker, no LLM (a scripted fake LLM is injected where a test needs one), inline
background jobs, and "today" pinned to 2026-09-30 (`tests/conftest.py`).

The API tests need PostgreSQL 16 with pgvector. Point `TEST_DATABASE_URL` at an empty database the
tests may wipe:

```bash
# e.g. with Docker
docker run -d --name lumina-test-db -p 5433:5432 \
  -e POSTGRES_USER=protocite -e POSTGRES_PASSWORD=protocite -e POSTGRES_DB=protocite_test pgvector/pgvector:pg16

cd backend
TEST_DATABASE_URL=postgresql+asyncpg://protocite:protocite@127.0.0.1:5433/protocite_test uv run pytest
```

Without a database the integration tests are skipped (not failed). Tesseract is needed for the
scanned-PDF circular (`sudo apt-get install tesseract-ocr tesseract-ocr-hin`).

### Every endpoint is covered

`tests/integration/test_api_endpoints.py` reads the list of operations from the OpenAPI schema and
fails if any endpoint is missing from its `COVERED` list — so a new endpoint cannot ship without a test.
It also holds the regression tests for the bugs fixed in the audit (search for `regression:`).

| Test | Endpoints |
|---|---|
| `test_health_reports_every_dependency` | `GET /health` |
| `test_auth_endpoints` | `/auth/config`, `/auth/dev-users`, `/auth/dev-login`, `/auth/refresh`, `/auth/me`, `/auth/oidc/*` |
| `test_query_routes_answer_refuse_clarify_and_out_of_scope` | `POST /query` (all four routes, validation, sign-in required) |
| `test_query_streams_route_sources_answer_done` | `POST /query/stream`, `GET /query/stream` |
| `test_history_lists_own_redacted_questions` | `GET /query/history` |
| `test_sources_open_cited_clause_and_file`, `test_drafts_are_invisible_to_clinicians` | `GET /sources/{chunk_id}`, `GET /sources/{version_id}/file` |
| `test_contacts_are_network_wide_plus_own_branch` | `GET /contacts` |
| `test_document_list_detail_and_chunks` | `GET /documents` (all filters), `GET /documents/{id}`, `GET …/chunks` |
| `test_extract_metadata_reads_header_tables` | `POST /documents/extract-metadata` |
| `test_upload_validation`, `test_version_lifecycle_upload_approve_retire` | `POST /documents`, `…/acknowledge-ocr`, `…/reingest`, `…/approve`, `…/retire` |
| `test_supersession_create_confirm_edit_delete` | `GET/POST /supersessions`, `PATCH/DELETE /supersessions/{id}` |
| `test_feedback_create_route_and_resolve` | `POST /feedback`, `GET /feedback/inbox`, `PATCH /feedback/{id}` |
| `test_conflicts_resolve_and_reopen` | `GET /conflicts`, `PATCH /conflicts/{id}` |
| `test_admin_stats_audit_and_reference_data` | `/admin/stats`, `/admin/audit` (JSON + CSV), `/admin/audit/verify`, `/admin/reference-data` |
| `test_admin_overview_shows_ai_trace_users_and_records` | `GET /admin/overview` |

The other integration modules test the behaviour in depth: `test_query_endpoint.py` (a fabricated
claim never reaches the client, superseded text is never cited, conflicts, branch rules, PII never
logged) and `test_documents_endpoint.py` (approving a circular changes the answer, OCR gate, audit
chain and database triggers), `test_ingestion_pipeline.py` (the real corpus, OCR and chunking).

---

## Frontend

```bash
cd frontend
pnpm install
pnpm test          # Vitest: 121 tests
pnpm lint && pnpm typecheck && pnpm format:check
```

| File | Covers |
|---|---|
| `src/tests/pages.test.tsx` | Each page on its own: Sign-in, Ask (example → streamed verified answer; typed question → error), Admin (every tab, trace, time window), Documents (search, upload dialog), Document page (approve as approver; no approve for authors), Amendments, Conflicts (resolve), Feedback, Audit log (check chain); the app shell per role (Ask / Library / Review / Admin), the Review queue tabs with counts, the Admin tabs, 404 and role gates, and every old `/admin/*` address redirecting to its new home |
| `src/tests/components.test.tsx` | Every shared component (Badge, Button, Card, Dialog, Sheet, Tabs, Table, Segmented, Field, Toast, Tooltip, Skeleton, Spinner, footer) and feature component (progress line, question box, citation chip, key values, conflict banner, feedback buttons and dialog, recent questions, version/status badges, source viewer, PDF viewer, upload dialog) |
| `src/tests/layout.test.tsx` | Paths, navigation per role and the redirect map; `Page` (browser tab title) and `PageHeader`; announcement bar (dismiss for the session); error boundary; 404 page; `ButtonLink`, `TaxonomyChip`, `MonoLabel`, `Band`, `RuleList`; `AmendmentList` (confirm / reject as approver, read-only for authors); admin stat band, bar list, count list and the daily chart (keyboard read-out and table view) |
| `src/features/ask/*.test.tsx`, `src/lib/*.test.ts`, `src/app/*.test.ts(x)` | Answer and abstain cards, streaming hook, SSE parser, API client, session handling, formatting, role gate, SSO callback |

`src/tests/mockApi.ts` stubs `fetch` per endpoint; `src/tests/fixtures.ts` holds responses typed
with the types generated from the API schema, so a fixture that no longer matches the API fails to
compile.

---

## End-to-end (Playwright)

Runs against the real API serving the built UI on one origin.

```bash
# 1. backend: database with the sample corpus, API on :8001 serving frontend/dist
cd backend && uv run python -m scripts.bootstrap && uv run uvicorn app.main:app --port 8001
# 2. frontend (another terminal)
cd frontend && pnpm build && pnpm e2e
```

| Spec | Covers |
|---|---|
| `e2e/pages.spec.ts` | Sign-in page lists every role; for each of the four demo users every page either loads with its title or shows "Not available for your role", and there are no browser errors; old addresses redirect; top navigation and section tabs; Admin tabs; document detail and indexed clauses; phone layout keeps the Ask title and input visible |
| `e2e/ask.spec.ts` | Verified, cited answer → opens the highlighted clause (desktop and phone); patient-specific dosing refused with identifiers removed and call links; "not found" instead of a guess; clinicians kept out of admin pages; audit chain check; approver sees suggested amendments; installable PWA |

Options: `E2E_BASE_URL` (default `http://localhost:8001`), `E2E_CHANNEL=msedge` (Windows),
`E2E_CHROMIUM_PATH=/path/to/chrome`, and `E2E_FULL_MODELS=1` to enable the checks that need the real
embedding/re-ranker models (exact answer wording, relevance-based "not found"). CI runs with the
deterministic stand-ins, so those two checks are skipped there.

---

## Last run (after the redesign)

| Suite | Result |
|---|---|
| Ruff lint + format, mypy (changed modules) | clean |
| Backend (unit + API/integration, PostgreSQL 16 + pgvector 0.6) | **276 passed** |
| ESLint, TypeScript, Prettier | clean |
| Frontend (Vitest) | **121 passed** |
| Frontend production build | clean; first download 514 kB (161 kB gzipped) — the PDF viewer and staff pages load on demand |
| End-to-end (Playwright, Chromium, desktop + phone) | **18 passed, 1 skipped** (needs the real re-ranker — run with `E2E_FULL_MODELS=1` and the default models) |
