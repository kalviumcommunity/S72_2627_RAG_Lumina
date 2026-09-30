# Safety Case & Clinical Risk Management — ProtoCite

**Document Version:** 1.0  
**Target Standard Alignment:** ISO 14971 (Application of risk management to medical devices) & India DPDP Act 2023.

---

## 1. Hazard Analysis & Mitigation Matrix

| Hazard ID | Clinical Hazard | Failure Mode | Mitigation Strategy | Verification Evidence |
| :--- | :--- | :--- | :--- | :--- |
| **HAZ-01** | LLM Hallucination | LLM fabricates a plausible dosage, drug name, or unit. | **Citation Verification Gate:** Every claim is split and verified against cited passages. Uncited or unsupported claims are discarded; answer withholds if unsupported. | `test_verifier.py` (100% detection of injected false claims). |
| **HAZ-02** | Stale / Superseded Guidance | Clinician acts on an outdated protocol when an active circular amended the rule. | **Supersession Resolution:** The query engine filters out superseded clauses and prioritizes active amendments. | `test_supersession.py`, `test_authority.py`. |
| **HAZ-03** | Inappropriate Automation of Diagnosis/Dose | Resident requests automated patient dosing calculation or diagnosis. | **Deterministic Rule + LLM Classifier:** Immediate refusal (`high_risk` route) + immediate tap-to-call escalation directory. | `test_classifier.py` (patient-specific queries strictly refused). |
| **HAZ-04** | PII Leakage | Clinician pastes patient identifiers (UHID, phone, name) into prompt. | **Presidio Redaction Engine:** Scrubbing runs before logging, before vector search, and before any LLM prompt. | `test_pii_redaction.py` (Aadhaar, UHID, ABHA, phone numbers redacted). |
| **HAZ-05** | Audit Tampering | Hostile or erroneous modification of audit trail to conceal misguidance. | **Cryptographic Hash Chain + DB Triggers:** Each audit entry is hashed with the previous record's SHA-256; `UPDATE` and `DELETE` privileges revoked. | `verify_audit.py` CLI and database triggers. |

---

## 2. Independent Citation Verification Gate

Unlike traditional RAG systems that display LLM outputs directly:
1. ProtoCite enforces that every sentence asserting a clinical fact must carry an explicit marker `[S1]`, `[S2]`.
2. An independent verification judge tests each claim sentence against the exact snippet cited.
3. If the support score falls below threshold (`0.80`), the claim is pruned from the answer.
4. If no valid clinical claims remain, the system automatically falls back to an abstention (`not_found`), preventing ungrounded prose from reaching the clinician.

---

## 3. Data Privacy & DPDP Act 2023 Compliance

Under India's **Digital Personal Data Protection Act (DPDP Act 2023)** and Digital Personal Data Protection Rules:
- **Zero Raw PII Storage:** Queries containing patient identifiable data are sanitized in-memory prior to database persistence.
- **Data Residency Mode:** When `LLM_PROVIDER=ollama` is configured, all model inference executes entirely on-premises with zero network egress. Cloud LLM modes require an India-region enterprise endpoint with a signed Business Associate / Data Processing Agreement.
- **Configurable Retention:** Query logs default to 180 days retention, after which automated cleanup purging applies.
