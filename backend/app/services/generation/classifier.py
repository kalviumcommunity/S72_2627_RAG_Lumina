"""Question routing: answer / clarify / out_of_scope / high_risk.

Two layers (ADR 0003):
1. Deterministic rules run first. If they detect a patient-specific decision (weight-based dose
   calculation, a named/identified patient, "should I give/withhold…", diagnosis), the question is
   high_risk and the LLM is not consulted — the LLM can never downgrade a rule-detected risk.
2. The LLM classifier (prompts/classifier.md). "high_risk" from either layer wins. If the LLM is
   unavailable, the rule result is used (answer unless the rules say otherwise).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.models.enums import QueryRoute
from app.services.generation.prompts import PromptSet
from app.services.llm.base import LLMError, LLMProvider
from app.services.retrieval.terms import entity_lexicon
from app.services.safety.pii_redaction import clinical_vocabulary
from app.services.textutil import content_words, stemmed_words

# Words that make a question about clinical work even if it also mentions e.g. "news" or "code"
# ("code blue", "NEWS2"). Named medicines and conditions come from the retrieval entity lexicon.
_CLINICAL_HINTS = stemmed_words(
    "dose dosing infusion bolus protocol guideline circular policy sop patient patients ward icu "
    "emergency sepsis septic transfusion antibiotic antimicrobial medication medicine drug aptt "
    "nomogram escalation resuscitation cardiac arrest bleeding haemorrhage news2 pager extension "
    "blood mtp outreach ccot lactate oxygen fluid fluids"
)

CLASSIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "route": {"type": "string", "enum": [r.value for r in QueryRoute]},
        "clarifying_question": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["route", "clarifying_question", "reason"],
    "additionalProperties": False,
}

_I = re.IGNORECASE
_PATIENT_CUE = re.compile(
    r"\b(?:my|this|our|his|her)\s+(?:patient|pt|baby|infant|child|kid|mother|lady|gentleman|man|woman|"
    r"boy|girl)(?:['’]s)?\b|\bpatient['’]s\b|\b(?:he|she)\s+(?:is|has|was|weighs)\b|"
    r"\b(?:for|give|giving|to|on)\s+(?:him|her)\b|"
    r"\bin\s+bed\s*(?:no\.?\s*)?\d+|\bbed\s*(?:no\.?\s*)?\d+\b|\b\d{1,3}\s*[- ]?(?:year|yr|month|day)s?[- ]old\b|"
    r"<PERSON>|<MRN>|<ABHA>|<ID_NUMBER>|<DOB>",
    _I,
)
_DECISION_WORDS = re.compile(
    r"\b(?:dose|doses|dosing|rate|mg|mcg|units?|ml|mls|give|start|stop|withhold|hold|continue|increase|"
    r"decrease|titrate|adjust|prescribe|transfuse|intubate|discharge|treat|treatment|safe|okay|ok|"
    r"diagnos\w*|have)\b",
    _I,
)
_STRONG_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"(?<![/\w])\d+(?:\.\d+)?\s?(?:kg|kgs|kilos?|kilograms?)\b(?!\s*/)", _I),
        "Gives a patient's weight — individual dose calculation",
    ),
    (
        re.compile(r"\bweigh(?:s|ing)\b|\bweight\s+(?:is|of)\s+\d", _I),
        "Gives a patient's weight — individual dose calculation",
    ),
    (
        re.compile(r"\b(?:calculate|work\s+out|compute)\b.*\b(?:dose|rate|volume|infusion|bolus|ml|units|mg)\b", _I),
        "Asks for an individual dose calculation",
    ),
    (
        re.compile(
            r"\bhow\s+(?:much|many)\s+(?:mg|mcg|ml|mls|units|g|vials?|ampoules?|tablets?)\b[^?.]*"
            r"\b(?:should|shall|do|can|to)\s+(?:i|we|give|use|draw)\b",
            _I,
        ),
        "Asks for an individual dose calculation",
    ),
    (
        re.compile(r"\bwhat\s+(?:rate|dose)\s+should\s+(?:i|we)\s+(?:set|give|run|use|start)\b", _I),
        "Asks for an individual dosing decision",
    ),
    (
        re.compile(
            r"\bshould\s+(?:i|we)\s+(?:give|start|stop|withhold|hold|continue|restart|increase|decrease|"
            r"prescribe|transfuse|intubate|discharge|treat|switch|escalate|de-?escalate)\b",
            _I,
        ),
        "Asks for a treatment decision for a patient",
    ),
    (
        re.compile(
            r"\b(?:does|do)\s+(?:he|she|my\s+patient|this\s+patient|the\s+patient)\s+have\b|\bdiagnos(?:e|is)\b",
            _I,
        ),
        "Asks for a diagnosis",
    ),
    (
        re.compile(
            r"\b(?:creatinine|egfr|crcl|creatinine\s+clearance|urea|bilirubin)\s*(?:is|of|=|:|at|was)?\s*\d",
            _I,
        ),
        "Gives a patient's renal/hepatic result — individual dose adjustment",
    ),
)
_OUT_OF_SCOPE = re.compile(
    r"\b(?:weather|cricket|football|ipl|movie|film|song|lyrics|recipe|joke|poem|stock|share\s+price|bitcoin|"
    r"crypto|election|politic\w*|news|python|javascript|java|code|coding|program|sql|excel|translate|"
    r"horoscope|capital\s+of|who\s+won|write\s+(?:me\s+)?an?\s+(?:essay|story|email))\b",
    _I,
)
_GREETING = re.compile(
    r"^\s*(?:hi|hello|hey|thanks|thank\s+you|good\s+(?:morning|evening|night)|ok|okay)\b[\s!.?]*$", _I
)
# "How much fluid?" / "What dose?" with nothing else to go on: ask which situation is meant.
_VAGUE_QUANTITY = re.compile(r"^\s*(?:how\s+(?:much|many|long|often)|what\s+(?:dose|rate|amount))\b", _I)
_QUANTITY_WORDS = {"much", "many", "long", "often", "amount", "give", "use", "need"}
_GENERIC = {
    "dose",
    "doses",
    "dosing",
    "rate",
    "protocol",
    "policy",
    "guideline",
    "drug",
    "medicine",
    "number",
    "contact",
    "who",
    "call",
    "time",
    "rule",
    "rules",
}


@dataclass(frozen=True)
class Classification:
    route: QueryRoute
    reason: str
    clarifying_question: str | None = None
    source: str = "rules"


def rule_classify(question: str) -> Classification:
    for pattern, reason in _STRONG_RULES:
        if pattern.search(question):
            return Classification(QueryRoute.high_risk, reason)
    if _PATIENT_CUE.search(question) and _DECISION_WORDS.search(question):
        return Classification(QueryRoute.high_risk, "Asks about treatment of a specific patient")
    words = content_words(question)
    stems = stemmed_words(question)
    clinical = stems & (_CLINICAL_HINTS | entity_lexicon())
    if _GREETING.match(question) or (_OUT_OF_SCOPE.search(question) and not clinical):
        return Classification(QueryRoute.out_of_scope, "Not about hospital documents")
    specific = words - _GENERIC - _QUANTITY_WORDS
    if (words and words <= _GENERIC) or (
        _VAGUE_QUANTITY.match(question) and len(specific) <= 1 and not stems & entity_lexicon()
    ):
        return Classification(
            QueryRoute.clarify,
            "Too general to look up",
            "Which medicine, protocol or situation is this about?",
        )
    return Classification(QueryRoute.answer, "Document lookup")


async def classify(question: str, llm: LLMProvider | None, prompts: PromptSet) -> Classification:
    rules = rule_classify(question)
    if rules.route == QueryRoute.high_risk:
        return rules
    if llm is None:
        return rules
    try:
        data = await llm.complete_json(
            system=prompts.classifier.text,
            user=f"Question: {question}",
            schema=CLASSIFIER_SCHEMA,
            task="classify",
            max_tokens=200,
        )
    except LLMError:
        return rules
    try:
        route = QueryRoute(str(data.get("route", "")).strip())
    except ValueError:
        route = QueryRoute.high_risk  # unparseable route: be safe
    reason = str(data.get("reason") or "")[:300]
    clarifying = str(data.get("clarifying_question") or "").strip() or None
    if route == QueryRoute.high_risk:
        return Classification(QueryRoute.high_risk, reason or "Patient-specific decision", source="llm")
    if route == QueryRoute.clarify and clarifying:
        return Classification(QueryRoute.clarify, reason, clarifying[:300], source="llm")
    if route == QueryRoute.out_of_scope:
        # Clinical vocabulary present -> let retrieval decide (worst case: "not found").
        if content_words(question) & clinical_vocabulary():
            return Classification(QueryRoute.answer, "Clinical terms present; looked up anyway", source="llm+rules")
        return Classification(QueryRoute.out_of_scope, reason or "Not about hospital documents", source="llm")
    if rules.route == QueryRoute.out_of_scope:
        return Classification(QueryRoute.answer, reason, source="llm")
    return Classification(QueryRoute.answer, reason or "Document lookup", source="llm")
