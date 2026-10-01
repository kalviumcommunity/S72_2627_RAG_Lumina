/** Response fixtures shaped exactly like the API (types generated from the OpenAPI schema). */
import type {
  AdminConflict,
  Citation,
  Contact,
  AuditEvent,
  DocumentDetail,
  DocumentSummary,
  Feedback,
  HistoryItem,
  Overview,
  QueryResponse,
  ReferenceData,
  Source,
  Stats,
  Supersession,
  User,
  Version,
} from "../lib/types";

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

// ---- admin-side fixtures (documents, amendments, conflicts, feedback, audit, stats, overview) ----------

export function version(overrides: Partial<Version> = {}): Version {
  return {
    id: "ver-3",
    document_id: "doc-icu",
    version_label: "3",
    status: "approved",
    effective_from: "2025-11-01",
    review_due: "2027-11-01",
    approved_by: "user-approver",
    approved_at: "2025-11-01T09:00:00Z",
    retired_at: null,
    change_summary: null,
    original_filename: "P-ICU-07_v3.md",
    mime_type: "text/markdown",
    file_sha256: "a".repeat(64),
    ingest_status: "ready",
    ingest_error: null,
    parser: "markdown",
    page_count: 1,
    ocr_min_confidence: null,
    ocr_page_confidence: null,
    ocr_acknowledged_at: null,
    parse_warnings: [],
    needs_ocr_acknowledgement: false,
    is_current: true,
    chunk_count: 11,
    created_at: "2025-10-20T09:00:00Z",
    ...overrides,
  };
}

export function documentSummary(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  return {
    id: "doc-icu",
    doc_code: "P-ICU-07",
    title: "Heparin Infusion Protocol (Adult ICU)",
    doc_type: "protocol",
    department: { id: "dep-icu", name: "Intensive Care", code: "ICU" },
    owner: user("author"),
    applies_to_all_branches: true,
    branches: [],
    versions: [version()],
    current_version_id: "ver-3",
    review_overdue: false,
    next_review_due: "2027-11-01",
    ...overrides,
  };
}

export function supersession(overrides: Partial<Supersession> = {}): Supersession {
  return {
    id: "link-1",
    source_version_id: "ver-circ",
    source_doc_code: "C-2026-09",
    source_version_label: "1",
    source_status: "approved",
    target_document_id: "doc-icu",
    target_doc_code: "P-ICU-07",
    target_section_path: "4.2",
    effective_from: "2026-09-01",
    note: null,
    evidence: "Amends: P-ICU-07 §4.2",
    suggested: true,
    confirmed: true,
    confirmed_at: "2026-09-01T09:00:00Z",
    hides_sections: ["4.2"],
    ...overrides,
  };
}

export function documentDetail(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    ...documentSummary(),
    versions: [
      version(),
      version({ id: "ver-4", version_label: "4", status: "draft", is_current: false, approved_at: null }),
    ],
    supersessions_out: [],
    supersessions_in: [supersession()],
    ...overrides,
  };
}

export function adminConflict(overrides: Partial<AdminConflict> = {}): AdminConflict {
  const side = {
    chunk_id: "chunk-a",
    doc_code: "P-ICU-07",
    title: "Heparin Infusion Protocol",
    version: "3",
    section_path: "4.3",
    text: "Repeat the aPTT 6 hours after every rate change.",
    effective_from: "2025-11-01",
  };
  return {
    id: "conflict-1",
    description: "aPTT recheck: 6 h vs 4 h",
    detected_by: "query",
    status: "open",
    confidence: 0.81,
    created_at: "2026-09-30T08:00:00Z",
    owner: "Dr Meera Nair",
    resolution_note: null,
    a: side,
    b: {
      ...side,
      chunk_id: "chunk-b",
      doc_code: "DG-02",
      section_path: "4.2",
      text: "Check the aPTT 4 hours after any rate change.",
    },
    ...overrides,
  };
}

export function feedbackItem(overrides: Partial<Feedback> = {}): Feedback {
  return {
    id: "fb-1",
    query_id: "q-1",
    kind: "outdated",
    comment: "A newer circular applies",
    status: "open",
    created_at: "2026-09-30T08:00:00Z",
    question: "What is the heparin step for aPTT above 100?",
    answer: "Hold the infusion for 1 hour. [S1]",
    outcome: "answered",
    cited: ["C-2026-09 §2"],
    reporter: "Dr Kavya Rao",
    routed_to: "Dr Meera Nair",
    resolution_note: null,
    ...overrides,
  };
}

export function auditEvent(overrides: Partial<AuditEvent> = {}): AuditEvent {
  return {
    seq: 42,
    created_at: "2026-09-30T08:00:00Z",
    actor: "Dr Kavya Rao",
    action: "query.answered",
    entity_type: "query",
    entity_id: "q-1",
    payload: { route: "answer", outcome: "answered" },
    hash: "b".repeat(64),
    prev_hash: "c".repeat(64),
    ...overrides,
  };
}

export function historyItem(overrides: Partial<HistoryItem> = {}): HistoryItem {
  return {
    query_id: "q-1",
    question: "Does Tazocin need AMS approval?",
    route: "answer",
    outcome: "answered",
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

export function stats(overrides: Partial<Stats> = {}): Stats {
  return {
    window_days: 30,
    total_questions: 12,
    answered: 8,
    partial: 1,
    abstained: 3,
    abstention_rate: 0.25,
    route_counts: { answer: 9, high_risk: 2, out_of_scope: 1 },
    abstain_reasons: { high_risk: 2, not_found: 1 },
    latency_p50_ms: 1200,
    latency_p95_ms: 2400,
    top_questions: [{ label: "does tazocin need ams approval?", count: 3 }],
    unanswered_questions: [{ label: "visiting hours for maternity?", count: 1 }],
    top_documents: [{ label: "P-ICU-07", count: 5 }],
    stale_documents: [
      {
        document_id: "doc-dg02",
        doc_code: "DG-02",
        title: "High-Alert Medications",
        version: "2",
        review_due: "2026-09-01",
        days_overdue: 29,
      },
    ],
    open_conflicts: 1,
    open_feedback: 1,
    pending_supersessions: 2,
    documents_awaiting_approval: 1,
    daily: [{ day: new Date().toISOString().slice(0, 10), questions: 12, abstained: 3 }],
    ...overrides,
  };
}

export function overview(overrides: Partial<Overview> = {}): Overview {
  return {
    window_days: 30,
    ai: {
      config: {
        llm_provider: "gemini",
        llm_model: "gemini-3.6-flash",
        reasoning_level: "minimal",
        embedding_model: "intfloat/multilingual-e5-base",
        reranker_model: "BAAI/bge-reranker-base",
        pii_engine: "presidio",
        verifier_mode: "batch",
        verifier_threshold: 0.8,
        min_relevance: 0.35,
        prompt_versions: { classifier: "d4dc9422", generator: "fcd3a2fc", verifier: "ee720259" },
      },
      questions: 12,
      pii_redacted: 2,
      generation_modes: { llm: 8, "not drafted": 4 },
      route_sources: { rules: 3, llm: 9 },
      judges: { "llm-batch": 8 },
      claims_checked: 20,
      claims_supported: 18,
      avg_stage_ms: { route: 300, retrieve: 400, generate: 900, verify: 500, total: 2100 },
      llm_calls: [{ task: "generate", calls: 8, failures: 1, timeouts: 1, avg_ms: 900 }],
      recent: [
        {
          query_id: "q-9",
          created_at: "2026-09-30T08:00:00Z",
          user: "Dr Kavya Rao",
          question: "What heparin bolus should I give <PERSON>, 72 kg?",
          pii_redacted: true,
          route: "high_risk",
          route_reason: "Gives a patient's weight",
          route_source: "rules",
          outcome: "abstained",
          abstain_reason: "high_risk",
          generation_mode: null,
          judge: null,
          claims: 0,
          supported: 0,
          dropped: [],
          cited: [],
          key_terms: [],
          expansions: [],
          latency_ms: 20,
          timings_ms: { route: 1, total: 20 },
        },
        {
          query_id: "q-8",
          created_at: "2026-09-30T07:59:00Z",
          user: "Dr Kavya Rao",
          question: "Does Tazocin need AMS approval?",
          pii_redacted: false,
          route: "answer",
          route_reason: "Document lookup",
          route_source: "llm",
          outcome: "partial",
          abstain_reason: null,
          generation_mode: "llm",
          judge: "llm-batch",
          claims: 3,
          supported: 2,
          dropped: [{ claim: "It is always safe.", issue: "uncited" }],
          cited: ["DG-01 §3.1"],
          key_terms: ["piperacillin-tazobactam"],
          expansions: ["Tazocin = piperacillin-tazobactam"],
          latency_ms: 2100,
          timings_ms: { route: 300, retrieve: 400, generate: 900, verify: 500, total: 2100 },
        },
      ],
    },
    users: [
      {
        user_id: "user-clinician",
        name: "Dr Kavya Rao",
        email: "kavya.rao@dhn.example",
        role: "clinician",
        branch: "DHN Central Campus",
        questions: 12,
        answered: 8,
        partial: 1,
        abstained: 3,
        refused_high_risk: 2,
        feedback_given: 1,
        uploads: 0,
        approvals: 0,
        reviews: 0,
        last_active: "2026-09-30T08:00:00Z",
      },
    ],
    documents: [
      {
        id: "doc-icu",
        doc_code: "P-ICU-07",
        title: "Heparin Infusion Protocol (Adult ICU)",
        doc_type: "protocol",
        department: "Intensive Care",
        owner: "Dr Meera Nair",
        current_version: "3",
        effective_from: "2025-11-01",
        versions: 2,
        drafts: 0,
        review_due: "2027-11-01",
        review_overdue: false,
      },
    ],
    amendments: [
      {
        id: "link-1",
        source: "C-2026-09 v1",
        source_status: "approved",
        target: "P-ICU-07 §4.2",
        effective_from: "2026-09-01",
        confirmed: true,
        suggested: true,
        evidence: "Amends: P-ICU-07 §4.2",
      },
    ],
    conflicts: [
      {
        id: "conflict-1",
        a: "P-ICU-07 v3 §4.3",
        b: "DG-02 v2 §4.2",
        description: "aPTT recheck: 6 h vs 4 h",
        status: "open",
        detected_by: "query",
        owner: "Dr Meera Nair",
        created_at: "2026-09-30T08:00:00Z",
      },
    ],
    feedback: [
      {
        id: "fb-1",
        created_at: "2026-09-30T08:00:00Z",
        kind: "outdated",
        status: "open",
        reporter: "Dr Kavya Rao",
        routed_to: "Dr Meera Nair",
        question: "What is the heparin step for aPTT above 100?",
        comment: "A newer circular applies",
      },
    ],
    ...overrides,
  };
}

export function referenceData(): ReferenceData {
  return {
    branches: [{ id: "branch-1", code: "CEN", name: "DHN Central Campus" }],
    departments: [{ id: "dep-icu", code: "ICU", name: "Intensive Care" }],
    users: [user("author")],
    doc_types: ["protocol", "drug_guideline", "circular", "sop", "external_reference"],
  };
}

export function source(overrides: Partial<Source> = {}): Source {
  return {
    chunk_id: "chunk-1",
    version_id: "ver-circ",
    document_id: "doc-circ",
    doc_code: "C-2026-09",
    title: "Heparin Nomogram Amendment",
    doc_type: "circular",
    version: "1",
    status: "approved",
    is_current: true,
    effective_from: "2026-09-01",
    review_due: "2027-09-01",
    section_path: "2",
    covered_paths: ["2"],
    heading: "Revised step",
    text: "Above 100: hold the infusion for 1 hour.",
    page_start: 1,
    page_end: 1,
    char_start: 0,
    char_end: 40,
    bbox: null,
    is_table: false,
    mime_type: "text/markdown",
    file_url: "/api/v1/sources/ver-circ/file",
    ocr_min_confidence: null,
    neighbours: { previous: null, next: null },
    outline: [
      {
        chunk_id: "chunk-0",
        section_path: "1",
        heading: "Background",
        text: "Why it changed.",
        is_table: false,
        page_start: 1,
      },
      {
        chunk_id: "chunk-1",
        section_path: "2",
        heading: "Revised step",
        text: "Above 100: hold the infusion for 1 hour.",
        is_table: false,
        page_start: 1,
      },
    ],
    superseded_by: [],
    amends: [{ doc_code: "P-ICU-07", section_path: "4.2" }],
    newer_version: null,
    ...overrides,
  };
}
