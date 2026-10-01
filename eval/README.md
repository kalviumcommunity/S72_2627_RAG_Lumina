# Evaluation Harness & Safety Benchmarking — Lumina

This directory houses the safety, retrieval, and groundedness evaluation harness for Lumina.

---

## 1. Dataset Overview (`datasets/sample_questions.jsonl`)

The evaluation dataset comprises synthetic clinical questions mapped against the synthetic protocol corpus:
- **Answerable questions (~60%):** Clinical threshold lookups, protocol sequences, antimicrobial guidelines.
- **Unanswerable questions (~20%):** Topics absent from the institutional corpus (expected outcome: `abstained` via `not_found`).
- **Supersession questions (~10%):** Topics amended by recent circulars (verifying that the latest circular version overrides older protocol numbers).
- **Conflict questions (~5%):** Contradictory guidance across documents (verifying conflict banner surfacing).
- **High-Risk questions (~5%):** Patient-specific dosing calculations or diagnostic requests (verifying immediate refusal and escalation).

---

## 2. Evaluation Metrics & Threshold Targets

| Metric | Target | Description |
| :--- | :---: | :--- |
| **Retrieval Recall@5** | ≥ 0.90 | Proportion of queries where the gold clause is in top 5 retrieval results. |
| **Citation Precision** | ≥ 0.97 | Percentage of citations verified as factual by the verification gate. |
| **Groundedness** | ≥ 0.95 | Proportion of answer assertions directly entailed by the source texts. |
| **Current-Version Accuracy** | ≥ 0.99 | Verifies superseded clauses are never presented as current guidance. |
| **Correct Abstention** | ≥ 0.90 | Accuracy in abstaining on unanswerable and high-risk questions. |
| **Over-Abstention Rate** | ≤ 0.10 | Frequency of improperly refusing answerable clinical queries. |
| **Route Classification Accuracy** | ≥ 0.90 | Correct classification across `answer`, `clarify`, `out_of_scope`, and `high_risk`. |

---

## 3. Running Evaluations

From the project root:
```bash
make eval
# Or directly:
cd backend && uv run python -m eval.run_eval
```

Reports are automatically generated and written to `eval/reports/{timestamp}.md`.
