/** Response fixtures shaped exactly like the API (types generated from the OpenAPI schema). */
import type { Citation, Contact, QueryResponse, User } from "../lib/types";

export function citation(overrides: Partial<Citation> = {}): Citation {
  return {
    marker: "S1",
    chunk_id: "chunk-1",
    version_id: "ver-1",
    document_id: "doc-1",
    doc_code: "C-2026-09",
    title: "Heparin nomogram revision",
    doc_type: "circular",
    version: "1",
    section_path: "2",
    heading: "Revised step",
    snippet: "If aPTT > 100 s, hold the infusion for 1 hour.",
    page: 1,
    effective_from: "2026-09-01",
    branch_specific: false,
    supported: true,
    support_score: 0.93,
    supersedes: null,
    amends: [{ doc_code: "P-ICU-07", section_path: "4.2" }],
    ...overrides,
  };
}

export function contact(overrides: Partial<Contact> = {}): Contact {
  return {
    id: "contact-1",
    role_label: "ICU consultant on call",
    phone_ext: "2201",
    phone: "+91 80 4000 2201",
    pager: "455",
    notes: null,
    ...overrides,
  };
}

export function answered(overrides: Partial<QueryResponse> = {}): QueryResponse {
  return {
    query_id: "q-1",
    route: "answer",
    outcome: "answered",
    answer: "Hold the heparin infusion for 1 hour. [S1]\nThen reduce the rate by 3 units/kg/h. [S1]",
    citations: [citation()],
    quick_values: [{ label: "Hold", value: "1 hour", source: "S1" }],
    sources: [],
    conflicts: [],
    escalation: null,
    disclaimer: "Supports, does not replace, clinical judgement.",
    generation_mode: "llm",
    verification: { claims: 2, supported: 2, judge: "llm" },
    redacted_question: "What is the heparin step for aPTT above 100?",
    pii_redacted: false,
    latency_ms: 2400,
    timings_ms: {},
    ...overrides,
  };
}

export function abstained(
  reason: "high_risk" | "not_found" | "clarify",
  overrides: Partial<QueryResponse> = {},
): QueryResponse {
  return answered({
    route: reason === "not_found" ? "answer" : reason,
    outcome: "abstained",
    answer: null,
    citations: [],
    quick_values: [],
    verification: null,
    escalation: {
      reason,
      message: "Lumina cannot recommend a patient-specific dose.",
      clarifying_question: reason === "clarify" ? "Which patient group — adult or paediatric?" : null,
      contacts: [contact()],
    },
    ...overrides,
  });
}

export function user(role: User["role"]): User {
  return {
    id: `user-${role}`,
    email: `${role}@demo.protocite.test`,
    display_name: `Demo ${role}`,
    role,
    branch: { id: "branch-1", code: "BLR", name: "Bengaluru" },
    department: null,
  };
}
