# API Reference — ProtoCite v1

Base URL: `/api/v1`

All endpoints except `/health` and `/auth/config` require an active session or `Authorization: Bearer <token>` header.

---

## 1. Authentication Endpoints

### `GET /auth/config`
Retrieves authentication provider configuration.
- **Response `200`**:
  ```json
  {
    "dev_auth": true,
    "oidc_enabled": false,
    "session_idle_minutes": 15
  }
  ```

### `GET /auth/dev-users`
Lists demo clinical personas (only when `DEV_AUTH=true`).
- **Response `200`**: Array of user profiles (Clinician, Author, Approver, Admin).

### `POST /auth/dev-login`
Issues a JWT token for the selected demo profile.
- **Body**: `{ "email": "kavya.rao@dhn.example" }`
- **Response `200`**: User object + session cookie.

---

## 2. Query Endpoints

### `POST /query`
Performs end-to-end question answering with safety classification and citation verification.

- **Request Body**:
  ```json
  {
    "question": "What is the heparin infusion rate adjustment when aPTT exceeds 100 seconds?",
    "branch_id": null
  }
  ```

- **Response `200` (Answered)**:
  ```json
  {
    "query_id": "e1472088-8c6f-4e8d-96a7-7889b941ffae",
    "route": "answer",
    "outcome": "answered",
    "answer": "Hold the infusion for 60 minutes, then decrease the rate by 3 units/kg/h [S1].",
    "citations": [
      {
        "marker": "S1",
        "chunk_id": "3196f7e8-469b-449e-b960-93a00a12e2e9",
        "doc_code": "C-2026-09",
        "title": "Heparin Nomogram Amendment",
        "version": "1",
        "section_path": "2.1",
        "page": 1,
        "effective_from": "2026-09-01",
        "supersedes": {
          "doc_code": "P-ICU-07",
          "section_path": "4.2"
        },
        "snippet": "For aPTT > 100 seconds: stop infusion for 1 hour, restart with rate reduced by 3 units/kg/hr.",
        "supported": true
      }
    ],
    "quick_values": [
      { "label": "Hold Infusion", "value": "1 hour", "source": "S1" },
      { "label": "Rate Reduction", "value": "-3 units/kg/h", "source": "S1" }
    ],
    "conflicts": [],
    "escalation": null,
    "latency_ms": 1420,
    "disclaimer": "ProtoCite retrieves approved documents. Supports, does not replace, clinical judgement."
  }
  ```

- **Response `200` (Abstained - High Risk / Patient-Specific)**:
  ```json
  {
    "query_id": "8432a901-bca2-48df-9e23-2894101e8271",
    "route": "high_risk",
    "outcome": "abstained",
    "answer": null,
    "citations": [],
    "escalation": {
      "reason": "high_risk",
      "message": "ProtoCite cannot calculate individual patient doses or make diagnostic decisions.",
      "contacts": [
        {
          "role_label": "Duty senior doctor (network on-call)",
          "phone_ext": "3000",
          "pager": "101",
          "notes": "24/7. Patient-specific decisions."
        },
        {
          "role_label": "On-call clinical pharmacist",
          "phone_ext": "2230",
          "pager": "220"
        }
      ]
    }
  }
  ```

### `GET /query/stream?q={question}&branch_id={uuid}`
Server-Sent Events (SSE) streaming endpoint. Emits events:
1. `event: route` (detected route: `answer`, `clarify`, `high_risk`, `out_of_scope`)
2. `event: sources` (top-k context passages displayed immediately)
3. `event: answer` (verified answer with citation markers)
4. `event: done`

---

## 3. Documents & Supersessions

| Method | Endpoint | Role | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/documents` | `clinician+` | List approved documents |
| `POST` | `/documents` | `author+` | Create document & upload version |
| `POST` | `/documents/{id}/versions/{vid}/approve` | `approver+` | Approve draft version |
| `POST` | `/documents/{id}/versions/{vid}/retire` | `approver+` | Retire outdated version |
| `GET` | `/sources/{chunk_id}` | `clinician+` | Fetch clause passage and adjacent clauses |
| `GET` | `/sources/{version_id}/file` | `clinician+` | Download approved source document file |
| `POST` | `/supersessions` | `approver+` | Link explicit clause amendment |

---

## 4. Admin & Compliance

- `GET /admin/stats`: Top questions, unanswered queries, abstention rates, p50/p95 latency metrics.
- `GET /admin/audit?from={date}&to={date}`: Cryptographically verified audit log stream (JSON/CSV).
- `GET /health`: Comprehensive system health (Postgres, pgvector, Redis, LLM, models).
