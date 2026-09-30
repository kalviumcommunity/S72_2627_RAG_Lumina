# ADR 0001: PostgreSQL for Hybrid Search (Full-Text + pgvector)

## Status
Accepted

## Context
ProtoCite requires fast, reliable retrieval over clinical protocols. Search must handle exact drug names, abbreviations (e.g., "aPTT", "TDS", "OD"), and protocol codes (e.g., "P-ICU-07"), as well as semantic similarity for colloquial queries. Operating a separate vector database (e.g., Pinecone, Qdrant, Milvus) alongside an operational database introduces dual-write anomalies, migration overhead, and complex transactional consistency issues.

## Decision
We utilize PostgreSQL 16 as both the transactional datastore and search engine:
1. Built-in PostgreSQL Full-Text Search (`tsvector` + `websearch_to_tsquery('english', q)`) indexed with GIN for keyword precision.
2. `pgvector` extension for 768-dimensional dense vector embeddings with cosine distance (`<=>`).
3. Reciprocal Rank Fusion (RRF with $k=60$) in Python to fuse keyword and vector rankings.
4. CrossEncoder re-ranking (`BAAI/bge-reranker-base`) for top candidates.

## Consequences
- **Positive:** Atomic transactions, single database backup, unified RBAC filters on branch and version status.
- **Positive:** Zero dual-write sync issues during document ingestion or supersession invalidation.
- **Negative:** Vector index performance requires sufficient database RAM; mitigated by chunk-level granularity and local dataset scaling.
