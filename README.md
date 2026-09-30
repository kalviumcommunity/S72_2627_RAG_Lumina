# ProtoCite 🏥

> **Source-Backed Clinical Protocol Assistant for Hospital On-Call Staff**  
> *Every clinical fact linked directly to the exact approved clause, version, and effective date.*

[![CI](https://github.com/kalviumcommunity/S72_2627_RAG_Lumina/actions/workflows/ci.yml/badge.svg)](https://github.com/kalviumcommunity/S72_2627_RAG_Lumina/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-green.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/Frontend-React_19_TypeScript-blue.svg)](https://react.dev/)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL_16_%2B_pgvector-blue.svg)](https://github.com/pgvector/pgvector)

---

## ⚠️ Intended Use Statement

> **"ProtoCite retrieves and displays approved institutional documents. It does not provide diagnoses or patient-specific treatment or dosing recommendations. It supports, and does not replace, clinical judgement and institutional escalation."**

*Synthetic Data Notice:* All protocols, clinical guidelines, hospital names, doctor names, extensions, and circulars included in this repository are **SYNTHETIC — FOR DEMO ONLY**. No real patient data or proprietary hospital protocols are contained herein.

---

## 1. Problem & Solution

### The Clinical Problem
Hospital networks maintain hundreds of emergency protocols, high-alert medication guidelines, and policy circulars. When an urgent decision arises on night shift or in the ICU, on-call residents and nurses face:
1. **Conflicting Versions:** Paper binders and stale intranet PDFs often retain outdated dosages.
2. **Unseen Supersessions:** An emergency circular (e.g., `C-2026-09`) amends a section of an older protocol (`P-ICU-07 §4.2`), but clinicians continue referring to the old rule.
3. **LLM Hallucination Hazards:** Standard AI chatbots produce plausible medical hallucinations without institutional grounding or audit trails.

### The ProtoCite Solution
- **Clause-Level Ingestion:** Ingests protocols down to leaf clauses (`§4.2.1`) with versioning, effective dates, and supersession links.
- **Authority-Ranked Hybrid Search:** Merges PostgreSQL full-text search with pgvector dense embeddings, filtered strictly by approval status and boosted by recency and branch jurisdiction.
- **Safety Gate & Citation Verification:** A deterministic classifier refuses patient-specific dosing/diagnosis requests and escalates immediately to duty contacts. Generated answers undergo sentence-by-sentence verification against cited clauses; uncited or unverified claims are pruned before the answer is delivered.
- **Cryptographic Audit Trail:** Append-only, hash-chained audit log guaranteeing non-repudiation of lookups and document approvals.

---

## 2. Architecture Overview

```mermaid
graph LR
    User["Clinician / Author"] --> Web["React 19 Frontend (PWA)"]
    Web --> API["FastAPI Backend (/api/v1)"]
    API --> PII["PII Redaction (Presidio)"]
    PII --> Classifier["Safety Router"]
    Classifier -->|high_risk| Escalate["Escalation Directory"]
    Classifier -->|answer| Retrieval["Hybrid Search (FTS + pgvector)"]
    Retrieval --> Rerank["Cross-Encoder Re-ranker"]
    Rerank --> Generator["LLM Generator (Gemini/Claude/Ollama)"]
    Generator --> Verifier["Citation Verification Gate"]
    Verifier --> Web
    API --> DB[("PostgreSQL 16 + pgvector")]
    API --> Audit[("Cryptographic Audit Log")]
```

For full details and sequence flows, see [docs/architecture.md](docs/architecture.md).

---

## 3. Technology Stack

| Layer | Technology |
|---|---|
| **Backend API** | Python 3.12, FastAPI, Uvicorn, Pydantic v2, `pydantic-settings` |
| **Database & Search** | PostgreSQL 16, `pgvector`, Full-Text Search (`tsvector`, `ts_rank_cd`), SQLAlchemy 2.x async, Alembic |
| **Embeddings & Re-ranking** | `sentence-transformers` (`intfloat/multilingual-e5-base`), CrossEncoder (`BAAI/bge-reranker-base`) |
| **LLM Providers** | Pluggable interface: Google Gemini (`gemini-3.5-flash-lite`, `gemini-3.6-flash`), Anthropic Claude, or local Ollama |
| **Safety & Verification** | Presidio Analyzer & Anonymizer, Independent LLM Judge Citation Verification Gate |
| **Frontend Web** | React 19, TypeScript, Vite, Tailwind CSS v4, Radix UI primitives, Motion, TanStack Query, React Router |
| **Mobile / PWA** | `vite-plugin-pwa` (offline shell, recent sources cached), `react-pdf` text-layer highlighting |
| **Audit & Testing** | Hash-chained append-only log, Pytest, Vitest, Playwright, Ruff, ESLint |

---

## 4. Quick Start & Setup

### Option A: Docker Compose (Recommended)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/kalviumcommunity/S72_2627_RAG_Lumina.git
   cd S72_2627_RAG_Lumina
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env and paste your GEMINI_API_KEY (or configure Ollama)
   ```

3. **Start all services:**
   ```bash
   docker compose up --build
   ```

4. **Access the application:**
   - **Frontend App:** [http://localhost:5173](http://localhost:5173)
   - **Backend API & Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
   - **Health Check:** [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

---

### Option B: Local Native Setup (Windows / Linux / macOS)

#### Prerequisites
- Python 3.12+ and `uv`
- Node.js 22+ and `npm` or `pnpm`
- PostgreSQL 16 with `pgvector`
- Tesseract OCR (with English and Hindi packages)

#### Steps
1. **Backend setup:**
   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run python -m scripts.seed
   uv run python -m scripts.ingest_sample
   uv run uvicorn app.main:app --port 8001
   ```

2. **Frontend setup (in a separate terminal):**
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

---

## 5. Live Interactive Demo Walkthrough

### Scenario 1: Supersession in Action ("Old Protocol vs New Circular")
1. Open [http://localhost:5173](http://localhost:5173).
2. Log in using the Demo Persona selector as **Dr. Kavya Rao (Clinician, Emergency Medicine)**.
3. Ask: `"What is the heparin infusion nomogram rate change for aPTT above 100 seconds?"`
4. **Result:**
   - ProtoCite answers: *"Hold the infusion for 1 hour, then decrease the rate by 3 units/kg/h [S1]."*
   - The citation chip links to **Circular C-2026-09 §2.1**, marked with the badge: **"Amends P-ICU-07 §4.2"**.
   - The older rule in `P-ICU-07` (-2 units/kg/h) was superseded on 2026-09-01 and is safely excluded from the clinical recommendation.

### Scenario 2: Refusal & Clinical Escalation (Safety Gate)
1. Ask: `"Patient weighs 74kg with creatinine 2.1, please calculate their enoxaparin dose."`
2. **Result:**
   - The safety classifier flags the question as `high_risk` (patient-specific calculation).
   - Answer generation is blocked.
   - The UI displays an **Abstention Card** with immediate tap-to-call institutional contacts:
     - **On-Call Clinical Pharmacist** (Ext. 2230 / Pager 220)
     - **Duty Senior Doctor** (Ext. 3000 / Pager 101)

### Scenario 3: PII Redaction
1. Ask: `"What antibiotic do I give for patient Ramesh Sharma, UHID 984729184 with sepsis?"`
2. **Result:**
   - The question is scrubbed before logging, vector search, or LLM prompting:
     `"What antibiotic do I give for patient [PATIENT_NAME], UHID [UHID] with sepsis?"`
   - Patient privacy is preserved in database logs and telemetry.

---

## 6. Testing & Quality Verification

Run the comprehensive test suites across both stacks:

```bash
# Run all backend unit & integration tests (252+ tests)
cd backend && uv run pytest

# Run frontend tests (Vitest - 41 tests)
cd frontend && npm test

# Verify cryptographic audit chain integrity
cd backend && uv run python -m scripts.verify_audit

# Run the safety and evaluation benchmark harness
cd backend && uv run python -m eval.run_eval
```

---

## 7. Project Documentation Index

- [PRD (Product Requirements Document)](docs/PRD.md)
- [System Architecture & Diagrams](docs/architecture.md)
- [Intended Use Statement & CDSCO Considerations](docs/intended-use.md)
- [API Reference & Schema Specification](docs/api.md)
- [Safety Case & Risk Mitigation Matrix](docs/safety-case.md)
- [Architecture Decision Records (ADRs)](docs/adr/)
- [Evaluation Harness Documentation](eval/README.md)

---

## 8. License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.
