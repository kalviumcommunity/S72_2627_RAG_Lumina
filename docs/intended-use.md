# Intended Use Statement & Regulatory Considerations — ProtoCite

## 1. Intended Use Statement

> **"ProtoCite retrieves and displays approved institutional documents. It does not provide diagnoses or patient-specific treatment or dosing recommendations. It supports, and does not replace, clinical judgement and institutional escalation."**

This statement is mandatory and must be displayed prominently across all interfaces:
- In the persistent footer of the web application.
- On the initial sign-in and landing screen.
- In all API documentation and user-facing exports.

---

## 2. Intended User Profile
- Registered medical practitioners, hospital residents, specialist consultants.
- On-call clinical nurses and nurse supervisors.
- Clinical hospital pharmacists and antimicrobial stewardship officers.
- Hospital administrative leaders, quality assurance, and document authors.

---

## 3. Scope Boundaries & Explicit Non-Goals

| Feature / Request | Supported? | System Action |
| :--- | :---: | :--- |
| Look up hospital protocol steps | **YES** | Retrieves approved protocol with clause citation |
| View antimicrobial restriction criteria | **YES** | Retrieves drug monograph guidelines |
| Check emergency escalation extensions | **YES** | Displays hospital telephone/pager directory |
| Calculate patient dosage by weight/creatinine | **NO** | Rejects with `high_risk` route; escalates to pharmacist |
| Diagnose a patient from clinical symptoms | **NO** | Rejects with `high_risk` route; escalates to duty doctor |
| Query open internet medical literature | **NO** | Rejects; system restricted to institutional repository |
| Write back into patient EHR / EMR charts | **NO** | Out of scope; read-only reference tool |

---

## 4. Regulatory & Compliance Context (CDSCO / SaMD)

Under India's **Central Drugs Standard Control Organisation (CDSCO)** Medical Device Rules (2017) and Software as a Medical Device (SaMD) guidance:
- **Software Type:** Non-diagnostic administrative reference and retrieval tool.
- **Classification:** Because ProtoCite does not perform automated patient-specific diagnosis, triage scoring, or closed-loop dosing calculations, version 1.0 operates outside the definition of an active medical device.
- **Prerequisite for Future Expansion:** Any prospective evolution that accepts individual patient parameters (e.g., patient weight, creatinine clearance, lab values) to recommend automated therapy modifications must undergo clinical validation and formal CDSCO medical device classification review prior to deployment.
