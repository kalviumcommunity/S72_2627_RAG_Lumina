# Codebase Audit — Bugs Found and Fixed

**Scope:** the whole repository — backend API and pipeline, frontend, Docker, CI, tests and docs.
**Method:** read every module; ran the existing suites (252 backend, 41 frontend tests — all passing,
but CI lint/format checks failing); booted the real stack (PostgreSQL + pgvector, sample corpus, API
serving the built UI); called every endpoint as every role; drove every page in a headless browser;
compared what the docs promise with what the code does.

Every fix below has a regression test unless marked otherwise.

---

## Summary

| Severity | Found | Examples |
|---|---:|---|
| Security | 1 | Production would start with the demo secret key and password-less demo sign-in |
| Breaks the demo / deployment | 8 | `docker compose up` gave an empty, erroring app; CI could never pass |
| Functional bugs | 13 | A request that froze the whole server; false "version mismatch" warnings; SSO sign-in could never finish |
| Documentation | 1 | Safety case promised a log purge that does not exist |

---

## 1. Security

| # | Bug | Impact | Fix |
|---|---|---|---|
| 1 | `.env.example` and the settings say production "refuses the default SECRET_KEY and dev sign-in", but nothing enforced it. | With `APP_ENV=prod` and defaults, anyone could forge an administrator token (the signing key is public) or sign in as any user with one click. | Settings now refuse to start in production with a short/default secret or `DEV_AUTH=true` (`core/config.py`). Test: `test_production_refuses_the_demo_secret_and_demo_sign_in`. |

## 2. Deployment and CI

| # | Bug | Impact | Fix |
|---|---|---|---|
| 2 | The API container never ran migrations, seeding or the sample-corpus load (the bootstrap script said it did). | `docker compose up` — the README's recommended start — produced an app with no tables: every page failed. | Container runs `scripts.bootstrap` (idempotent) before starting the API. |
| 3 | The container started with `uv run`, which re-syncs dependencies including dev tools at every start. | Slow start, and fails without internet. | `UV_NO_SYNC=1` and the virtualenv on `PATH`. |
| 4 | The "API documentation" link (`/docs`) was not proxied by nginx (Docker) or Vite (dev). | The link opened "Page not found". | Both proxy `/docs`; nginx also streams answers unbuffered. |
| 5 | CI installed the frontend with `npm ci`, but the repo ships `pnpm-lock.yaml` only. | The frontend CI job could never pass. | CI uses pnpm with the lockfile. |
| 6 | Ruff failures: an unused `noqa` (RUF100) and an unformatted script. | Backend CI lint step failed. | Fixed. |
| 7 | The generated `api-schema.d.ts` was not Prettier-formatted. | Frontend CI format step failed. | `pnpm gen:types` now formats its output. |
| 8 | CI ran only `tests/unit`, and the integration tests' database URL pointed at a port CI does not use — the API tests would have been skipped anyway. No e2e job. | Endpoint, ingestion and pipeline tests never ran in CI. | CI runs the full backend suite against its PostgreSQL service, then a new Playwright job against the running app. |
| 9 | Playwright was hard-wired to Microsoft Edge. | E2E tests could not run on Linux/CI. | Bundled Chromium by default; `E2E_CHANNEL` / `E2E_CHROMIUM_PATH` to override. |

## 3. Backend

| # | Bug | Impact | Fix |
|---|---|---|---|
| 10 | `GET /query/history?limit=-1` (or 0) sent a negative `LIMIT` to PostgreSQL. | HTTP 500. | Limit clamped to 1–50. |
| 11 | `POST /documents/extract-metadata` parsed (and OCR'd) the upload **on the event loop**, with no size limit; an unreadable file raised an unhandled error. | While one scan was being read, every other request froze (measured: a trivial request took 1.2 s instead of milliseconds); oversized files accepted; empty file → 500. | Parsing runs in a worker thread; `MAX_UPLOAD_MB` enforced; unreadable files → 422. |
| 12 | Metadata extraction ignored the header tables every document uses (`\| Version \| 2 \|`) and read prose instead ("superseded by **version 3**", "amends P-ICU-07 version 3"). | "Read details from the file" filled nothing for the sample documents, and approvers saw **false "version mismatch" warnings** (e.g. on P-ICU-07 v2). | Header tables are flattened and labels must start a line. All 10 sample documents now extract correctly; no false warnings. |
| 13 | Re-opening a resolved conflict kept `resolved_by` / `resolved_at`. | An open conflict still recorded a resolver and time. | Cleared on re-open. |
| 14 | "Re-process" could start while the same version was still processing. | Two jobs racing to delete and re-insert the same chunks. | 409 while processing; a job older than the worker timeout is treated as dead and may be restarted. |
| 15 | `/health` reported the PII engine as `regex` whenever Presidio was configured but not yet loaded (lazy load, `WARMUP_MODELS=false`). | Health check misreported the privacy safeguard. | Reports `presidio (loads on first question)` until loaded. |
| 16 | In verbatim (no-LLM) mode the same key value appeared twice with a meaningless label ("the infusion and — 6 hours"). | Confusing "Key values" box. | Duplicate values removed, keeping the first (best) label. |

## 4. Frontend

| # | Bug | Impact | Fix |
|---|---|---|---|
| 17 | Hospital SSO could never complete: the API redirects to `/auth/callback#token=…`, but the web app ignored the token and had no route for that address. | OIDC sign-in (the production sign-in) left the user on the login page. | The token is exchanged for a session and removed from the address bar; `/auth/callback` redirects to Ask. Tests: `src/app/sso.test.ts`. |
| 18 | The Ask page scrolled to the bottom on first load. | On phones the title and first examples were hidden. | Only scrolls once a conversation exists. E2E test on a phone viewport. |
| 19 | The dashboard's "why declined" labels had keys that never occur and missed `unavailable`. | Raw key shown. | Fixed in the new Admin page. |
| 20 | The daily chart used the browser's date while the server groups by UTC day. | Around midnight in India (00:00–05:30 IST) the newest bar was misplaced or missing. | The chart ends at the later of today and the newest day in the data. |
| 21 | The document-type filter stretched to full width (conflicting width classes). | Broken filter bar layout. | Fixed; all filter toggles now share one component. |
| 22 | Leftover "ProtoCite" branding after the rename: audit CSV file names, the favicon/app icons (teal "P"), the text of every sample document (visible in the source viewer), the Makefile and the docs. | Inconsistent product name in the demo. | Renamed everything users see. Internal identifiers (token issuer, database and storage names) were kept on purpose: changing them would sign everyone out and orphan existing Docker volumes. |

## 5. Documentation

| # | Issue | Fix |
|---|---|---|
| 23 | The safety case said query logs are purged automatically after 180 days. Only the setting (`LOG_RETENTION_DAYS`) exists; no purge job runs. | Corrected; listed below as a known gap. |

---

## Known limitations (not changed)

- **Log retention is not enforced** — add a scheduled purge of `query_logs`/`answer_logs` older than
  `LOG_RETENTION_DAYS` (the audit table is append-only by design and is kept).
- **Answer quality needs the real models.** With the built-in test doubles (hash embeddings and a
  word-overlap re-ranker, used when models cannot be downloaded) an off-topic question can be
  answered with a loosely related verbatim quote. Always demo with the real embedding and re-ranker
  models (the default) — ideally with an LLM key too.
- The documents list issues a few queries per document; fine at hospital-network scale, worth batching
  for thousands of documents.
- Retiring the version in force does not bring back the previous one; the document simply stops
  appearing in answers until a new version is approved (the safe default).

---

## What was added

| Area | Addition |
|---|---|
| Admin page | `/admin/overview` + `GET /api/v1/admin/overview`: overview, AI usage (configuration, generation modes, deciding layer, verifier results, stage timings, live LLM call counters, per-question decision trace), usage per user, all documents, amendments, conflicts and feedback. Migration `0002` stores a trace per question. |
| UI | One black-and-white theme, Montserrat (self-hosted), no colour or gradients; simpler header (role-based text links + Sign out, no navigation for clinicians); Ask page reduced to what a clinician needs; clearer page descriptions. |
| Tests | Backend: 276 tests (was 252), incl. `test_api_endpoints.py` covering **all 38 endpoints** with allowed and refused roles and a guard that fails when an endpoint has no test. Frontend: 86 tests (was 41) rendering **every page and component** on its own. E2E: 17 Playwright tests walking every page as every role on desktop and phone. See [TESTING.md](TESTING.md). |
| Docs | [USER_GUIDE.md](USER_GUIDE.md) (page-by-page flow), [architecture.md](architecture.md), [api.md](api.md), [TESTING.md](TESTING.md), [PITCH_GUIDE.md](PITCH_GUIDE.md), this report. |

---

## Redesign and restructure (second pass)

The UI was rebuilt on the design system in [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) (white canvas,
near-black pills, deep-green bands, coral taxonomy chips, Space Grotesk / Inter / Space Mono). Every
API call, permission, safety behaviour and test-visible text stayed the same. What changed and why:

### Information architecture

| Before | After | Why |
|---|---|---|
| Seven flat header links (Ask, Documents, Amendments, Conflicts, Feedback, Admin, Audit log) | Four sections — **Ask**, **Library**, **Review**, **Admin** — with pill tabs inside Review and Admin | One entry per job; the header no longer grows with every page |
| Authors worked under `/admin/documents`, `/admin/supersessions`, … | `/library`, `/review/amendments`, `/review/conflicts`, `/review/feedback`; `/admin` is administrator-only | Addresses match who uses them; old addresses redirect, so bookmarks keep working |
| Queues gave no hint of pending work until opened | Review tabs show how many items wait in each queue | Authors see where work is at a glance |
| Library status filter reset on every visit | Kept in the address (`/library?filter=pending`); Admin's work-queue tiles deep-link into it | Shareable, and "Versions awaiting approval →" lands on exactly those |
| API reference only reachable by typing `/docs` | Admin → **API reference** tab | Discoverable for the demo |

### Engineering

| Area | Change |
|---|---|
| Routing | Routes, addresses and navigation each live in one module (`app/routes.tsx`, `app/paths.ts`, `app/navigation.ts`); pages never hard-code URLs. |
| Server data | Every query key and fetcher declared once in `lib/queries.ts`; pages and mutations use it, so identical requests share one cache entry and invalidation cannot drift. |
| Stale data fix | Resolving feedback refreshed the admin stats but not the Admin page's record lists; it now refreshes both. |
| Shared component placement | The amendment list used by the document page and the Amendments queue moved out of the document page into `features/supersessions/AmendmentList.tsx`. |
| Resilience | An error boundary per page ("This page could not be shown" + Reload) instead of a blank screen; a proper 404 page. |
| Accessibility | Skip-to-content link; browser-tab title per page; focus rings; 36 px+ hit areas; the chart is keyboard-readable and has a table view. |
| Performance | The PDF viewer (pdf.js) now loads only when "Original page" is opened: the first download fell from 1.15 MB to 514 kB (351 → 161 kB gzipped). The Admin page keeps the previous numbers on screen while a new time window loads. |
| Chart | The daily chart was an SVG stretched with `preserveAspectRatio="none"` (distorted text); it is now measured to its container, uses a validated two-colour palette, and has legend, read-out and table view. |
| Tooling | `e2e/` is now covered by `pnpm format`; generated files are listed in `.prettierignore`. |
| Tests | Frontend 86 → **121** (new `layout.test.tsx`: paths, navigation, redirects, frame, primitives, amendment list, admin charts); E2E 17 → **19** (section navigation and every old address). Backend unchanged at 276, all passing. |
