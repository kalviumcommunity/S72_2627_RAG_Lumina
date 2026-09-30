"""SQL form of the effective-version rule (see ingestion/supersession.py for the Python form).

`ELIGIBLE_CTE` defines `eligible(id)`: chunks of the current approved version of each document
that apply to the user's branch and are not superseded by a confirmed, effective amendment.
Parameters: :as_of (date), :branch_id (uuid or NULL).
"""

from __future__ import annotations

CURRENT_VERSIONS_CTE = """
current_versions AS (
    SELECT DISTINCT ON (dv.document_id) dv.id, dv.document_id
    FROM document_versions dv
    WHERE dv.status = 'approved' AND dv.effective_from <= :as_of
    ORDER BY dv.document_id, dv.effective_from DESC, dv.approved_at DESC NULLS LAST
),
active_links AS (
    SELECT s.target_document_id, s.target_section_path
    FROM supersessions s
    JOIN document_versions sv ON sv.id = s.source_version_id
    WHERE s.confirmed AND s.effective_from <= :as_of AND sv.status IN ('approved', 'superseded')
)"""

SUPERSEDED_PREDICATE = """
EXISTS (
    SELECT 1 FROM active_links a
    WHERE a.target_document_id = d.id
      AND (a.target_section_path IS NULL OR EXISTS (
            SELECT 1 FROM unnest(c.covered_paths) AS p(path)
            WHERE p.path = a.target_section_path
               OR p.path LIKE a.target_section_path || '.%'
               OR p.path LIKE a.target_section_path || '#%'
               OR p.path LIKE a.target_section_path || '(%'))
)"""

BRANCH_PREDICATE = """
(d.applies_to_all_branches OR (CAST(:branch_id AS uuid) IS NOT NULL AND EXISTS (
    SELECT 1 FROM document_branches db
    WHERE db.document_id = d.id AND db.branch_id = CAST(:branch_id AS uuid))))"""


def eligible_cte(*, branch_filter: bool = True) -> str:
    """WITH clause defining `eligible(id)`; without the branch filter it spans every branch."""
    branch = f"AND {BRANCH_PREDICATE}" if branch_filter else ""
    return f"""
WITH {CURRENT_VERSIONS_CTE},
eligible AS (
    SELECT c.id
    FROM chunks c
    JOIN document_versions v ON v.id = c.version_id
    JOIN documents d ON d.id = v.document_id
    WHERE c.version_id IN (SELECT id FROM current_versions)
      {branch}
      AND NOT {SUPERSEDED_PREDICATE}
)"""  # noqa: S608  static SQL assembled from constants


ELIGIBLE_CTE = eligible_cte()
