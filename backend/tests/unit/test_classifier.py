"""Question routing (safety-critical): patient-specific questions must never be answered."""

from __future__ import annotations

import pytest

from app.models.enums import QueryRoute
from app.services.generation.classifier import classify, rule_classify
from app.services.generation.prompts import load_prompts
from app.services.llm.base import LLMError
from tests.fakes import ScriptedLLM

PROMPTS = load_prompts()

HIGH_RISK = [
    "What heparin bolus should I give <PERSON> who weighs 72 kg?",
    "Patient is 68kg, what is the heparin infusion rate?",
    "Calculate the heparin infusion rate for a 90 kg man",
    "Should I withhold heparin for the patient in bed 12?",
    "Should we give meropenem to my patient?",
    "My patient's creatinine is 3.2, what meropenem dose?",
    "eGFR 25 — adjust vancomycin?",
    "Does my patient have sepsis?",
    "Can you diagnose HIT in <PERSON>?",
    "How many ml of KCl should I give her?",
    "What rate should I set for the insulin infusion?",
    "Is it safe to give this patient's heparin bolus now?",
    "72 year old on warfarin, what dose tonight?",
]

SAFE = [
    "What is the heparin infusion nomogram rate change for aPTT above 100?",
    "What is the initial heparin bolus per kg in the protocol?",
    "How much fluid is given for septic shock per the bundle?",
    "Does piperacillin-tazobactam need AMS approval?",
    "Who do I call to activate the massive transfusion protocol?",
    "When should aPTT be repeated after a rate change?",
    "What does the protocol say about patients with a platelet count below 50?",
    "Max peripheral KCl infusion rate?",
]


@pytest.mark.parametrize("question", HIGH_RISK)
def test_rules_flag_patient_specific_questions(question: str) -> None:
    assert rule_classify(question).route == QueryRoute.high_risk


@pytest.mark.parametrize("question", SAFE)
def test_rules_let_document_lookups_through(question: str) -> None:
    assert rule_classify(question).route == QueryRoute.answer


@pytest.mark.parametrize("question", ["hi", "Who won the cricket match yesterday?", "Write me a python script"])
def test_rules_detect_out_of_scope(question: str) -> None:
    assert rule_classify(question).route == QueryRoute.out_of_scope


def test_rules_ask_to_clarify_overly_general_questions() -> None:
    result = rule_classify("dose?")
    assert result.route == QueryRoute.clarify and result.clarifying_question


async def test_llm_cannot_downgrade_a_rule_detected_risk() -> None:
    llm = ScriptedLLM(classify={"route": "answer", "clarifying_question": "", "reason": "looks fine"})
    result = await classify("Heparin dose for a 70 kg patient?", llm, PROMPTS)
    assert result.route == QueryRoute.high_risk
    assert llm.calls == []  # rules short-circuit before any LLM call


async def test_llm_high_risk_wins_over_rules() -> None:
    llm = ScriptedLLM(classify={"route": "high_risk", "clarifying_question": "", "reason": "individual decision"})
    result = await classify("Is heparin okay after the procedure?", llm, PROMPTS)
    assert result.route == QueryRoute.high_risk and result.source == "llm"


async def test_llm_clarify_with_question() -> None:
    llm = ScriptedLLM(classify={"route": "clarify", "clarifying_question": "Adult or paediatric?", "reason": "x"})
    result = await classify("What is the fluid bolus volume?", llm, PROMPTS)
    assert result.route == QueryRoute.clarify and result.clarifying_question == "Adult or paediatric?"


async def test_llm_clarify_without_question_falls_back_to_answer() -> None:
    llm = ScriptedLLM(classify={"route": "clarify", "clarifying_question": "", "reason": "x"})
    result = await classify("What is the fluid bolus volume?", llm, PROMPTS)
    assert result.route == QueryRoute.answer


async def test_llm_out_of_scope_is_overridden_when_clinical_terms_are_present() -> None:
    llm = ScriptedLLM(classify={"route": "out_of_scope", "clarifying_question": "", "reason": "x"})
    assert (await classify("heparin nomogram", llm, PROMPTS)).route == QueryRoute.answer
    assert (await classify("tell me a joke", llm, PROMPTS)).route == QueryRoute.out_of_scope


async def test_unknown_llm_route_is_treated_as_high_risk() -> None:
    llm = ScriptedLLM(classify={"route": "banana", "clarifying_question": "", "reason": "x"})
    assert (await classify("What is the nomogram?", llm, PROMPTS)).route == QueryRoute.high_risk


async def test_llm_failure_falls_back_to_rules() -> None:
    llm = ScriptedLLM(classify=LLMError("timeout"))
    assert (await classify("What is the heparin nomogram?", llm, PROMPTS)).route == QueryRoute.answer


async def test_classifier_prompt_is_the_spec_prompt() -> None:
    llm = ScriptedLLM()
    await classify("What is the nomogram?", llm, PROMPTS)
    assert 'If unsure between "answer" and "high_risk", choose "high_risk".' in llm.calls[0]["system"]
