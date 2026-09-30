# Architecture & System Design — ProtoCite

ProtoCite is built with a decoupled architecture ensuring clinical safety, deterministic citation verification, and high performance.

---

## 1. System Overview

```mermaid
graph TB
    subgraph Client["Frontend (React 19 + Vite + TypeScript)"]
        UI["Clinician / Author UI"]
        Ask["Ask Flow & Source Sheet"]
        Admin["Admin & Supersession Graph"]
    end

    subgraph API["Backend API (FastAPI)"]
        Router["API Gateway / Router (/api/v1)"]
        Redactor["PII Redaction Engine (Presidio)"]
        Classifier["Deterministic Rules + LLM Classifier"]
        Orchestrator["Query Orchestration Engine"]
        Verifier["Citation Verification Gate"]
        Ingest["Ingestion & OCR Pipeline"]
    end

    subgraph Storage["Data Tier"]
        PG[("PostgreSQL 16 + pgvector<br/>(Full-text + Dense vectors + RBAC)")]
        Redis[("Redis 7<br/>(Cache & Job Queue)")]
        FS[("Document Storage<br/>(Original PDF / DOCX / MD)")]
    end

    subgraph Models["Inference Providers"]
        ST["Sentence-Transformers (E5 / BGE Re-ranker)"]
        LLM["LLM Provider (Gemini / Anthropic / Ollama)"]
    end

    UI --> Router
    Router --> Redactor
    Redactor --> Classifier
    Classifier --> Orchestrator
    Orchestrator --> PG
    Orchestrator --> ST
    Orchestrator --> LLM
    LLM --> Verifier
    Verifier --> Router
    Ingest --> PG
    Ingest --> FS
```

---

## 2. Ingestion Pipeline

```mermaid
flowchart TD
    A["Uploaded Document (PDF / DOCX / MD / HTML)"] --> B["Compute SHA-256 & Store Original"]
    B --> C{"Format Type"}
    C -->|PDF / Scanned| D["Layout Parser + OCR Engine (Tesseract)"]
    C -->|Docx / MD| E["Direct Block Parser"]
    D --> F["Calculate OCR Confidence"]
    F -->|Confidence < 0.80| G["Mark Warning: Require Author Approval"]
    F -->|Confidence >= 0.80| H["Clause-Level Chunker"]
    E --> H
    H --> I["Build Section Hierarchy (e.g., 4.2.1)"]
    I --> J["Generate Embeddings (multilingual-e5-base)"]
    J --> K["Store Chunks in PostgreSQL (tsvector + pgvector)"]
    K --> L["Detect Supersession References (e.g., Circular amends P-ICU-07)"]
    L --> M["Detect Pre-Ingest Semantic Contradictions"]
    M --> N["Append Audit Event (Cryptographic Chain)"]
```

---

## 3. Query Orchestration Pipeline

```mermaid
flowchart TD
    Q["User Clinical Question"] --> PII["PII Scrubbing (Presidio + Indian ID Recognizers)"]
    PII --> CR{"Route Classification"}
    
    CR -->|high_risk| HR["Abstain + Offer Escalation Directory (Duty Senior / CCOT)"]
    CR -->|out_of_scope| OOS["Abstain (Out of Scope Message)"]
    CR -->|clarify| CLR["Prompt for Clarification (Branch / Unit)"]
    
    CR -->|answer| HYB["Hybrid Retrieval: Keyword FTS (ts_rank_cd) + Vector (Cosine)"]
    HYB --> RRF["Reciprocal Rank Fusion (k=60)"]
    RRF --> AF["Authority Filter (Approved & Active only; Exclude Superseded)"]
    AF --> RR["Cross-Encoder Re-ranker (bge-reranker-base)"]
    RR --> AB["Authority Boosts (Branch recency, Superseding Circulars)"]
    AB --> TOP["Top-K Context Clauses"]
    
    TOP --> DRAFT["Generate Grounded Answer with [S1] Markers"]
    DRAFT --> VERIFY{"Citation Verifier Gate"}
    VERIFY -->|Score >= 0.8| PASS["Retain Claim"]
    VERIFY -->|Score < 0.8| DROP["Drop Unsupported Claim"]
    
    DROP --> CHK{"Any Clinical Claims Left?"}
    PASS --> CHK
    CHK -->|No| NF["Abstain (Document Not Found)"]
    CHK -->|Yes| STREAM["Emit Verified Answer + Source Citations + QuickCard"]
    STREAM --> AUDIT["Log Query, Outcome & Cryptographic Audit Event"]
```
