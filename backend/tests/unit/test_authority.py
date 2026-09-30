"""Authority filter and boosts (safety-critical): drafts / superseded / other-branch never pass."""

from __future__ import annotations

import uuid
from datetime import date

from app.models.enums import VersionStatus
from app.services.ingestion.supersession import SupersessionInfo, VersionInfo
from app.services.retrieval.authority import (
    BoostConfig,
    apply_boosts,
    build_context,
    drop_reason,
    filter_eligible,
)
from app.services.retrieval.types import Candidate

TODAY = date(2026, 9, 30)
CENTRAL, RIVERSIDE = uuid.uuid4(), uuid.uuid4()


def cand(
    *,
    doc: uuid.UUID | None = None,
    version: uuid.UUID | None = None,
    status: str = "approved",
    section: str = "1",
    covered: list[str] | None = None,
    all_branches: bool = True,
    branches: list[uuid.UUID] | None = None,
    doc_type: str = "protocol",
    effective: date = date(2025, 1, 1),
    rerank: float = 0.5,
    supersedes: list[dict[str, str]] | None = None,
) -> Candidate:
    return Candidate(
        chunk_id=uuid.uuid4(),
        version_id=version or uuid.uuid4(),
        document_id=doc or uuid.uuid4(),
        doc_code="X-01",
        title="Title",
        doc_type=doc_type,
        department_id=None,
        version_label="1",
        status=status,
        effective_from=effective,
        approved_at=None,
        section_path=section,
        covered_paths=covered or [section],
        heading="H",
        text="text",
        page_start=1,
        page_end=1,
        is_table=False,
        applies_to_all_branches=all_branches,
        branch_ids=branches or [],
        rerank_score=rerank,
        supersedes=supersedes or [],
    )


def ctx_for(
    candidates: list[Candidate],
    *,
    links: list[SupersessionInfo] | None = None,
    extra_versions: list[VersionInfo] | None = None,
    branch: uuid.UUID | None = CENTRAL,
):
    versions = [
        VersionInfo(c.version_id, c.document_id, VersionStatus(c.status), c.effective_from, None) for c in candidates
    ] + (extra_versions or [])
    return build_context(TODAY, branch, versions, links or [])


def test_current_approved_network_wide_chunk_passes() -> None:
    c = cand()
    kept, dropped = filter_eligible([c], ctx_for([c]))
    assert kept == [c] and dropped == 0


def test_draft_chunks_never_pass() -> None:
    c = cand(status="draft")
    assert drop_reason(c, ctx_for([c])) == "version status is draft"
    assert filter_eligible([c], ctx_for([c]))[0] == []


def test_retired_and_superseded_status_never_pass() -> None:
    for status in ("retired", "superseded"):
        c = cand(status=status)
        assert filter_eligible([c], ctx_for([c]))[0] == []


def test_older_approved_version_is_not_current() -> None:
    doc = uuid.uuid4()
    old = cand(doc=doc, effective=date(2024, 1, 1))
    new = cand(doc=doc, effective=date(2025, 11, 1))
    kept, _ = filter_eligible([old, new], ctx_for([old, new]))
    assert kept == [new]
    assert drop_reason(old, ctx_for([old, new])) == "not the current version"


def test_future_version_is_not_yet_current() -> None:
    doc = uuid.uuid4()
    now = cand(doc=doc, effective=date(2025, 1, 1))
    future = cand(doc=doc, effective=date(2026, 12, 1))
    kept, _ = filter_eligible([now, future], ctx_for([now, future]))
    assert kept == [now]


def test_superseded_section_never_passes_but_siblings_do() -> None:
    doc = uuid.uuid4()
    version = uuid.uuid4()
    s42 = cand(doc=doc, version=version, section="4.2")
    s43 = cand(doc=doc, version=version, section="4.3")
    link = SupersessionInfo(uuid.uuid4(), VersionStatus.approved, doc, "4.2", date(2026, 9, 1), True)
    kept, dropped = filter_eligible([s42, s43], ctx_for([s42, s43], links=[link]))
    assert kept == [s43] and dropped == 1
    assert s42.is_superseded and not s43.is_superseded


def test_unconfirmed_amendment_does_not_hide_the_section() -> None:
    doc = uuid.uuid4()
    s42 = cand(doc=doc, section="4.2")
    link = SupersessionInfo(uuid.uuid4(), VersionStatus.approved, doc, "4.2", date(2026, 9, 1), False)
    assert filter_eligible([s42], ctx_for([s42], links=[link]))[0] == [s42]


def test_branch_specific_document_only_for_its_branch() -> None:
    local = cand(all_branches=False, branches=[RIVERSIDE])
    assert filter_eligible([local], ctx_for([local], branch=RIVERSIDE))[0] == [local]
    assert filter_eligible([local], ctx_for([local], branch=CENTRAL))[0] == []
    assert filter_eligible([local], ctx_for([local], branch=None))[0] == []


def test_branch_override_beats_network_wide_at_equal_relevance() -> None:
    network = cand(rerank=0.80)
    local = cand(all_branches=False, branches=[RIVERSIDE], rerank=0.80)
    ranked = apply_boosts([network, local], ctx_for([network, local], branch=RIVERSIDE), BoostConfig(recency=0))
    assert ranked[0] is local
    assert local.boosts["branch"] == 0.10 and "branch" not in network.boosts


def test_branch_boost_does_not_rescue_much_less_relevant_text() -> None:
    network = cand(rerank=0.90)
    local = cand(all_branches=False, branches=[RIVERSIDE], rerank=0.40)
    ranked = apply_boosts([network, local], ctx_for([network, local], branch=RIVERSIDE), BoostConfig(recency=0))
    assert ranked[0] is network


def test_amending_circular_is_boosted_over_plain_document() -> None:
    protocol = cand(rerank=0.70)
    circular = cand(doc_type="circular", rerank=0.70, supersedes=[{"doc_code": "P-ICU-07", "section_path": "4.2"}])
    ranked = apply_boosts([protocol, circular], ctx_for([protocol, circular]), BoostConfig(recency=0))
    assert ranked[0] is circular and circular.boosts["circular"] == 0.05


def test_circular_without_amendments_gets_no_circular_boost() -> None:
    circular = cand(doc_type="circular")
    apply_boosts([circular], ctx_for([circular]), BoostConfig(recency=0))
    assert "circular" not in circular.boosts


def test_recency_prefers_newer_effective_date() -> None:
    old = cand(rerank=0.60, effective=date(2023, 1, 1))
    new = cand(rerank=0.60, effective=date(2026, 9, 1))
    ranked = apply_boosts([old, new], ctx_for([old, new]), BoostConfig(branch=0, circular=0, recency=0.02))
    assert ranked[0] is new
    assert "recency" not in old.boosts  # older than the 2-year horizon


def test_boosts_never_change_the_raw_relevance_score() -> None:
    local = cand(all_branches=False, branches=[RIVERSIDE], rerank=0.30)
    apply_boosts([local], ctx_for([local], branch=RIVERSIDE), BoostConfig())
    assert local.rerank_score == 0.30 and local.final_score > 0.30
