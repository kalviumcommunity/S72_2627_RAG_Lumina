"""Pure logic: text utilities, RRF, audit hash chain, conflict heuristic, key terms."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.models.audit import AuditEvent
from app.services.audit import GENESIS_HASH, compute_hash, event_record, verify_events
from app.services.ingestion.conflict import heuristic_conflict
from app.services.retrieval.hybrid import reciprocal_rank_fusion
from app.services.retrieval.terms import TermStats
from app.services.textutil import extract_numbers, extract_quantities, split_lines, split_sentences

# ---- text utilities -------------------------------------------------------------------------------


def test_quantities_are_normalised() -> None:
    qs = {(q.value, q.unit) for q in extract_quantities("Give 25,000 units in 50 mL over 6 hours; 60–85 seconds")}
    assert ("25000", "units") in qs and ("50", "ml") in qs and ("6", "h") in qs and ("60-85", "s") in qs


def test_numbers_ignore_citation_markers() -> None:
    assert extract_numbers("Stop for 1 hour [S3].") == {"1"}


def test_sentence_split_keeps_markers_with_their_sentence() -> None:
    assert split_sentences("Stop for 1 hour. [S1] Then reduce by 3 units/kg/h [S2].") == [
        "Stop for 1 hour. [S1]",
        "Then reduce by 3 units/kg/h [S2].",
    ]


def test_split_lines_keeps_bullets() -> None:
    assert split_lines("- one\n\n2. two\nthree") == [("- ", "one"), ("2. ", "two"), ("", "three")]


# ---- RRF ------------------------------------------------------------------------------------------


def test_rrf_rewards_agreement_between_lists() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    fused = reciprocal_rank_fusion([[a, b, c], [b, a]], k=60)
    assert [x for x, _ in fused][:2] in ([a, b], [b, a])
    assert fused[-1][0] == c
    assert abs(dict(fused)[a] - (1 / 61 + 1 / 62)) < 1e-12


def test_rrf_limit() -> None:
    ids = [uuid.uuid4() for _ in range(10)]
    assert len(reciprocal_rank_fusion([ids], limit=4)) == 4


# ---- audit chain ----------------------------------------------------------------------------------


def _chain(n: int) -> list[AuditEvent]:
    events: list[AuditEvent] = []
    prev = GENESIS_HASH
    for i in range(n):
        created = datetime(2026, 9, 30, 10, 0, i, tzinfo=UTC)
        rec = event_record(
            actor_user_id=None,
            action=f"a{i}",
            entity_type="t",
            entity_id=str(i),
            payload={"i": i},
            created_at=created,
        )
        h = compute_hash(prev, rec)
        events.append(
            AuditEvent(
                seq=i + 1,
                created_at=created,
                actor_user_id=None,
                action=f"a{i}",
                entity_type="t",
                entity_id=str(i),
                payload={"i": i},
                prev_hash=prev,
                hash=h,
            )
        )
        prev = h
    return events


def test_intact_chain_verifies() -> None:
    result = verify_events(_chain(5))
    assert result.ok and result.events_checked == 5


def test_tampered_payload_is_detected() -> None:
    events = _chain(5)
    events[2].payload = {"i": 999}
    result = verify_events(events)
    assert not result.ok and result.first_bad_seq == 3


def test_deleted_event_is_detected() -> None:
    events = _chain(5)
    del events[1]
    result = verify_events(events)
    assert not result.ok and result.first_bad_seq == 3


# ---- conflict heuristic ---------------------------------------------------------------------------


def test_same_step_different_value_is_a_conflict() -> None:
    a = "Repeat the aPTT 6 hours after starting the infusion and 6 hours after every rate change."
    b = "For heparin infusions, check the aPTT 4 hours after any rate change."
    finding = heuristic_conflict(a, b)
    assert finding.contradicts and finding.confidence >= 0.7
    assert "6 hours" in finding.value_a and "4 hours" in finding.value_b


def test_different_drugs_with_shared_diluent_are_not_a_conflict() -> None:
    a = "Standard concentration: 25,000 units in 50 mL sodium chloride 0.9% (heparin)."
    b = "Intravenous insulin infusions use 50 units of soluble insulin in 50 mL sodium chloride 0.9%."
    assert not heuristic_conflict(a, b).contradicts


def test_same_values_are_not_a_conflict() -> None:
    a = "Check the aPTT 6 hours after a rate change."
    b = "Repeat the aPTT 6 hours after any rate change."
    assert not heuristic_conflict(a, b).contradicts


def test_lists_mentioning_both_values_are_not_a_conflict() -> None:
    a = "Peripheral potassium up to 10 mmol/h; central line up to 20 mmol/h in ICU."
    b = "Potassium chloride may run at 20 mmol/h through a central line, 10 mmol/h peripherally."
    assert not heuristic_conflict(a, b).contradicts


# ---- key terms ------------------------------------------------------------------------------------


def test_entity_terms_take_priority_over_rare_words() -> None:
    stats = TermStats()
    stats.fit(
        ["Piperacillin-tazobactam is unrestricted.", "Restricted agents need AMS approval within 24 hours."]
        + [f"General clause {i} about infusion monitoring and charts." for i in range(40)]
    )
    assert stats.key_terms("Does Tazocin need AMS approval? (piperacillin-tazobactam)") == {"piperacillin-tazobactam"}


def test_rare_words_are_key_terms_without_entities() -> None:
    stats = TermStats()
    stats.fit(["The transfusion runner collects packs."] + [f"Generic clause {i} about charts." for i in range(40)])
    assert "runner" in stats.key_terms("Who is the transfusion runner?")
    assert "chart" not in stats.key_terms("Where are the charts?")  # common word


def test_words_absent_from_the_corpus_are_not_key_terms() -> None:
    stats = TermStats()
    stats.fit(["Heparin infusion protocol."])
    assert stats.key_terms("maternity visiting policy") == set()
