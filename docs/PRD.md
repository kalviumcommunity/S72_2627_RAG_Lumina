# Product Requirements Document (PRD) — ProtoCite

**Project:** ProtoCite  
**Role:** Source-Backed Clinical Protocol Assistant  
**Status:** MVP Implemented & Validated  

---

## 1. Executive Summary & Problem Statement

Hospital networks manage hundreds of clinical protocols, antimicrobial stewardship guidelines, high-alert drug monographs, and emergency policy circulars. These documents are updated frequently (e.g., dosage adjustments, protocol revisions, superseding circulars).

During time-critical patient care decisions, on-call clinical staff (residents, nurses, emergency physicians) face significant hurdles:
1. **Information Fragmentation:** Multiple PDF files, intranet portals, and physical binders with differing revision dates.
2. **Supersession Ambiguity:** A newly issued circular amends §4.2 of an ICU protocol, but older printouts or digital copies remain in circulation.
3. **General LLM Hallucination Risk:** Off-the-shelf generative models hallucinate plausible clinical dosages and cannot verify against specific institutional policies.

**ProtoCite** solves this by delivering an authoritative, source-backed retrieval and question-answering assistant restricted strictly to approved institutional documents.

---

## 2. Core Functional Requirements

### 2.1 Ingestion & Document Lifecycle
- **Clause-Level Chunking:** Break documents into fine-grained clauses retaining full hierarchical section paths (e.g., `4.2.1`).
- **OCR with Confidence Tracking:** Extract text using layout-aware parsers and Tesseract OCR; flag low-confidence pages (< 0.80) for author acknowledgment prior to approval.
- **Supersession Graph:** Track explicit amendments where new circulars supersede specific clauses of existing protocols.
- **Role-Based Access Control (RBAC):** Clinicians only ever retrieve approved, current versions. Authors and approvers manage drafts and revisions.

### 2.2 Authority-Weighted Hybrid Search
- PostgreSQL Full-Text Search (`tsvector`) + Dense Vector Search (`pgvector` with `multilingual-e5-base`).
- Reciprocal Rank Fusion (RRF) with CrossEncoder re-ranking (`bge-reranker-base`).
- Strict authority filtering: exclude drafts, retired versions, and superseded clauses.
- Soft boosts for branch-specific guidance and recent amending circulars.

### 2.3 Safety Gates & Orchestration
- **PII Redaction:** Presidio-based redactor scrubbing patient identifiers (UHID/MRN, phone numbers, ABHA, Aadhaar) prior to query logging or LLM dispatch.
- **Query Classification:** Deterministic rule gate + LLM classifier routing questions into:
  - `answer`: Document lookup.
  - `clarify`: Ambiguous question requiring branch or unit detail.
  - `out_of_scope`: Non-institutional inquiries.
  - `high_risk`: Patient-specific diagnosis or dosing calculation requests (immediate refusal + escalation).
- **Independent Citation Verification Gate:** Every claim in a generated answer must be explicitly supported by cited source clauses. Unsupported claims are dropped; if no clinical claims remain supported, the system abstains.
- **Escalation Directory:** For high-risk or abstained queries, provide immediate, tap-to-call institutional escalation contacts (Duty Senior Doctor, CCOT, On-Call Pharmacist).

### 2.4 Audit & Accountability
- Cryptographically chained, append-only audit trail for all queries, answers, ratings, and document modifications.
- User feedback loop routing flags to document owners.

---

## 3. Non-Functional Requirements & Performance
- **Retrieval Latency:** ≤ 800 ms p95 for hybrid search.
- **Citation Precision:** ≥ 97% verified claim support in evaluation benchmarks.
- **Correct Abstention:** ≥ 90% refusal of out-of-scope and patient-specific queries.
- **Accessibility:** WCAG 2.2 AA compliant, mobile-first design, calm clinical aesthetic, dark/light theme support.
