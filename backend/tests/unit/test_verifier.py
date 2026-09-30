"""Citation verifier (safety-critical): unsupported or uncited clinical text never survives."""

from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.services.generation.generator import Draft, Passage
from app.services.generation.prompts import load_prompts
from app.services.generation.verifier import lexical_judge, numeric_guard, verify
from app.services.llm.base import LLMError
from app.services.retrieval.types import Candidate
from tests.fakes import ScriptedLLM

PROMPTS = load_prompts()


def passage(
    marker: str, text: str, *, doc_code: str = "C-2026-09", section: str = "2", heading: str = "Nomogram"
) -> Passage:
    c = Candidate(
        chunk_id=uuid.uuid4(),
        version_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        doc_code=doc_code,
        title="Heparin Nomogram Amendment",
        doc_type="circular",
        department_id=None,
        version_label="1",
        status="approved",
        effective_from=date(2026, 9, 1),
        approved_at=None,
        section_path=section,
        covered_paths=[section],
        heading=heading,
        text=text,
        page_start=1,
        page_end=1,
        is_table=False,
        applies_to_all_branches=True,
        branch_ids=[],
    )
    return Passage(marker, c)


S1 = passage(
    "S1",
    "For an aPTT above 100 seconds, stop the infusion for 1 hour, then restart at a rate reduced by "
    "3 units/kg/h and inform the ICU pharmacist.",
)
S2 = passage(
    "S2",
    "Repeat the aPTT 6 hours after every rate change.",
    doc_code="P-ICU-07",
    section="4.3",
    heading="Monitoring",
)


async def run(
    answer: str,
    *,
    llm: ScriptedLLM | None = None,
    quick: list[dict[str, str]] | None = None,
    passages: list[Passage] | None = None,
    mode: str = "batch",
):
    draft = Draft(answer=answer, quick_values=quick or [], mode="llm" if llm else "extractive")
    return await verify(draft, passages or [S1, S2], llm=llm, prompts=PROMPTS, threshold=0.8, mode=mode)


MODES = pytest.mark.parametrize("mode", ["batch", "per_claim"])


async def test_supported_claim_is_kept() -> None:
    result = await run("Stop the infusion for 1 hour, then reduce the rate by 3 units/kg/h [S1].")
    assert result.supported_ratio == 1.0
    assert result.answer == "Stop the infusion for 1 hour, then reduce the rate by 3 units/kg/h [S1]."
    assert result.used_markers == ["S1"]


async def test_uncited_sentence_is_removed() -> None:
    result = await run("Stop the infusion for 1 hour [S1]. Heparin is generally very safe.")
    assert "generally very safe" not in result.answer
    assert result.claims[1].issue == "uncited"
    assert 0 < result.supported_ratio < 1


@MODES
async def test_fabricated_number_is_removed_even_if_the_llm_judge_says_supported(mode: str) -> None:
    # The mocked LLM judge approves everything; the deterministic numeric guard must still catch this.
    llm = ScriptedLLM(verify={"supported": True, "score": 0.99, "issue": ""})
    result = await run(
        "Stop the infusion for 1 hour [S1]. Then give a 5000 unit bolus of heparin [S1].", llm=llm, mode=mode
    )
    assert "5000" not in result.answer
    assert result.answer == "Stop the infusion for 1 hour [S1]."
    dropped = [c for c in result.claims if not c.supported]
    assert dropped and "5000" in (dropped[0].issue or "")


@MODES
async def test_llm_judge_rejection_removes_the_claim(mode: str) -> None:
    def judge(system: str, user: str) -> dict[str, object]:
        ok = "inform the ICU pharmacist" in user.split("Claim:")[1]
        return {"supported": not ok, "score": 0.9, "issue": "" if not ok else "qualifier added"}

    llm = ScriptedLLM(verify=judge)
    result = await run("Stop the infusion for 1 hour [S1]. Always inform the ICU pharmacist [S1].", llm=llm, mode=mode)
    assert "inform the ICU pharmacist" not in result.answer


@MODES
async def test_low_llm_score_is_not_enough(mode: str) -> None:
    llm = ScriptedLLM(verify={"supported": True, "score": 0.5, "issue": ""})
    result = await run("Stop the infusion for 1 hour [S1].", llm=llm, mode=mode)
    assert not result.has_supported_claims


async def test_unknown_marker_is_unsupported() -> None:
    result = await run("Stop the infusion for 1 hour [S9].")
    assert not result.has_supported_claims
    assert result.claims[0].issue == "cites an unknown source"


async def test_claim_is_checked_against_each_cited_passage() -> None:
    result = await run("Repeat the aPTT 6 hours after every rate change [S1][S2].")
    assert result.claims[0].supported and result.claims[0].supported_by == "S2"


async def test_claim_joining_two_sources_is_checked_against_them_together() -> None:
    result = await run(
        "P-ICU-07 repeats the aPTT after 6 hours while C-2026-09 stops the infusion for 1 hour [S1][S2]."
    )
    assert result.claims[0].supported


@MODES
async def test_llm_failure_falls_back_to_lexical_judge(mode: str) -> None:
    llm = ScriptedLLM(verify=LLMError("down"))
    result = await run("Stop the infusion for 1 hour [S1]. Give aspirin 300 mg daily [S1].", llm=llm, mode=mode)
    assert result.answer == "Stop the infusion for 1 hour [S1]."
    assert "llm unavailable" in result.judge


async def test_bullets_and_line_structure_survive_filtering() -> None:
    answer = "- Stop the infusion for 1 hour [S1].\n- Give 40 mg enoxaparin [S1].\n- Repeat the aPTT 6 hours after every rate change [S2]."
    result = await run(answer)
    assert (
        result.answer == "- Stop the infusion for 1 hour [S1].\n- Repeat the aPTT 6 hours after every rate change [S2]."
    )


async def test_quick_values_must_appear_in_their_source() -> None:
    quick = [
        {"label": "Hold", "value": "1 hour", "source": "S1"},
        {"label": "Reduce", "value": "5 units/kg/h", "source": "S1"},
        {"label": "Recheck", "value": "6 hours", "source": "S9"},
    ]
    result = await run("Stop the infusion for 1 hour [S1].", quick=quick)
    assert result.quick_values == [{"label": "Hold", "value": "1 hour", "source": "S1"}]
    assert result.dropped_quick_values == 2


async def test_everything_unsupported_means_no_supported_claims() -> None:
    result = await run("Give 2 g of magnesium [S1]. Call extension 9999 [S2].")
    assert not result.has_supported_claims and result.answer == ""


def test_numeric_guard_allows_citation_metadata_numbers() -> None:
    assert numeric_guard("Per C-2026-09 §2, stop for 1 hour [S1].", [S1]) is None
    assert numeric_guard("Stop for 5 hours [S1].", [S1]) is not None


def test_lexical_judge_requires_high_coverage() -> None:
    ok, score, _ = lexical_judge("Stop the infusion for 1 hour and inform the ICU pharmacist [S1].", S1)
    assert ok and score >= 0.75
    ok, _, issue = lexical_judge("Start warfarin and check the INR tomorrow [S1].", S1)
    assert not ok and issue


async def test_batch_mode_makes_one_llm_call_for_all_claims() -> None:
    llm = ScriptedLLM(verify={"supported": True, "score": 0.95, "issue": ""})
    result = await run(
        "Stop the infusion for 1 hour [S1]. Repeat the aPTT 6 hours after every rate change [S2].", llm=llm
    )
    assert result.supported_ratio == 1.0
    assert llm.tasks() == ["verify"]


async def test_batch_mode_missing_verdict_means_unsupported() -> None:
    llm = ScriptedLLM(verify=lambda s, u: {"supported": True, "score": 0.95, "issue": ""})
    llm.complete_json = _returns({"verdicts": [{"claim": 1, "supported": True, "score": 0.95, "issue": ""}]})
    result = await run(
        "Stop the infusion for 1 hour [S1]. Repeat the aPTT 6 hours after every rate change [S2].", llm=llm
    )
    assert result.claims[0].supported and not result.claims[1].supported
    assert result.claims[1].issue == "no verdict returned"


def _returns(value: dict[str, object]):
    async def fake(**_: object) -> dict[str, object]:
        return value

    return fake
