"""Deterministic extractive answers (no-LLM mode and LLM-failure fallback)."""

from __future__ import annotations

import uuid
from datetime import date

from app.services.generation.generator import ConflictNote, Passage, extractive_answer
from app.services.retrieval.types import Candidate


def passage(
    marker: str,
    text: str,
    *,
    heading: str,
    title: str = "Protocol",
    doc_code: str = "P-1",
    effective: date = date(2025, 1, 1),
    rerank: float = 0.8,
) -> Passage:
    return Passage(
        marker,
        Candidate(
            chunk_id=uuid.uuid4(),
            version_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            doc_code=doc_code,
            title=title,
            doc_type="protocol",
            department_id=None,
            version_label="1",
            status="approved",
            effective_from=effective,
            approved_at=None,
            section_path="1",
            covered_paths=["1"],
            heading=heading,
            text=text,
            page_start=1,
            page_end=1,
            is_table=False,
            applies_to_all_branches=True,
            branch_ids=[],
            rerank_score=rerank,
        ),
    )


NOMOGRAM = passage(
    "S1",
    "Adjust the infusion according to the table.\n\n| aPTT (seconds) | Infusion action |\n|---|---|\n"
    "| 60–85 | No change |\n| Above 100 | Stop the infusion for 1 hour |",
    heading="aPTT adjustment nomogram",
    title="Heparin Infusion Protocol",
)


def test_matching_table_row_is_quoted_with_its_heading() -> None:
    draft = extractive_answer("heparin nomogram for aPTT above 100", [NOMOGRAM], [])
    assert not draft.not_found and draft.mode == "extractive"
    assert "Above 100" in draft.answer and "Stop the infusion for 1 hour" in draft.answer
    assert "60–85" not in draft.answer  # rows without the asked-for value are left out
    assert draft.answer.startswith("aPTT adjustment nomogram — ")
    assert draft.answer.endswith("[S1]")


def test_wrapped_ocr_lines_are_rejoined_into_sentences() -> None:
    p = passage(
        "S1",
        "(b) Possible sepsis without shock: give antibiotics\nwithin 3 hours of recognition.",
        heading="Amendment",
    )
    draft = extractive_answer("antibiotics for possible sepsis without shock", [p], [])
    assert "give antibiotics within 3 hours of recognition" in draft.answer


def test_key_term_must_appear_in_the_quote() -> None:
    generic = passage(
        "S1",
        "Restricted agents need AMS approval within 24 hours of the first dose.",
        heading="Restricted antimicrobials",
    )
    specific = passage(
        "S2",
        "| Agent | Route |\n|---|---|\n| Piperacillin-tazobactam | IV |",
        heading="Unrestricted antimicrobials",
        rerank=0.05,
    )
    draft = extractive_answer(
        "Does Tazocin need AMS approval?", [generic, specific], [], key_terms={"piperacillin-tazobactam"}
    )
    assert "Piperacillin-tazobactam" in draft.answer and "Unrestricted antimicrobials" in draft.answer
    assert "[S2]" in draft.answer


def test_abstains_when_no_sentence_names_the_key_term() -> None:
    generic = passage("S1", "Restricted agents need AMS approval within 24 hours.", heading="Restricted")
    assert extractive_answer("Is colistin restricted?", [generic], [], key_terms={"colistin"}).not_found


def test_abstains_without_passages() -> None:
    assert extractive_answer("anything", [], []).not_found


def test_conflict_quotes_both_sides_and_the_newer_date() -> None:
    a = passage(
        "S1",
        "Repeat the aPTT 6 hours after every rate change.",
        heading="Monitoring",
        doc_code="P-ICU-07",
        effective=date(2025, 11, 1),
    )
    b = passage(
        "S2",
        "For heparin infusions, check the aPTT 4 hours after any rate change.",
        heading="Heparin",
        doc_code="DG-02",
        effective=date(2025, 9, 1),
    )
    draft = extractive_answer("When to repeat aPTT after a rate change?", [a, b], [ConflictNote("S1", "S2", "x")])
    assert "6 hours" in draft.answer and "4 hours" in draft.answer
    assert "P-ICU-07 has the later effective date (2025-11-01)" in draft.answer
