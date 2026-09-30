# ADR 0002: Clause-Level Hierarchical Document Chunking

## Status
Accepted

## Context
Standard RAG pipelines chunk text using fixed token windows (e.g., 500 tokens with 50-token overlap). In clinical protocols and hospital policies, fixed windows frequently sever dosage rules from contraindications or split table cells across chunks. Furthermore, citations must point to specific clauses (e.g., "§4.2.1") rather than arbitrary document page fragments.

## Decision
We implement semantic, clause-level chunking based on document structure:
1. Detect numbered headings (`1`, `1.2`, `1.2.3`, `A.`, `(b)`) to construct an explicit `section_path`.
2. Extract leaf clauses as discrete chunks with their ancestor breadcrumbs prepended to embedding context: `[{doc_code} v{version} §{section_path}] {heading}`.
3. Merge tiny clauses (< 40 tokens) with sibling nodes; split long clauses (> 400 tokens) strictly at sentence boundaries with indexed suffixes (`#1`, `#2`).
4. Represent tables as structured Markdown chunks (`is_table=true`), generating row-level chunks with headers for large tables.

## Consequences
- **Positive:** Precise clause-level citations in user answers.
- **Positive:** Enables surgical supersession links (e.g., "Circular C-2026-09 supersedes only §4.2 of Protocol P-ICU-07").
- **Negative:** Parsing requires layout-aware inspection (Docling / PyPDF).
