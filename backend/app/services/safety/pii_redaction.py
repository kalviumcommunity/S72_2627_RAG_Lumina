"""PII redaction for staff questions.

Runs before logging, before embedding the query and before any LLM call. Only the redacted text
ever leaves this module; detected values are never stored or logged.

Engine: Presidio (spaCy NER for names + custom pattern recognisers for Indian identifiers:
UHID/MRN labels, ABHA number/address, Aadhaar-like 12-digit IDs, Indian mobile/landline numbers,
DOB). A clinical-vocabulary guard stops NER from redacting drug names that look like proper nouns.
If Presidio or the spaCy model is unavailable, the same patterns run as a regex-only fallback.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.logging import get_logger

log = get_logger(__name__)

PLACEHOLDERS: dict[str, str] = {
    "PERSON": "<PERSON>",
    "PHONE_NUMBER": "<PHONE>",
    "IN_PHONE": "<PHONE>",
    "IN_UHID_MRN": "<MRN>",
    "IN_ABHA_NUMBER": "<ABHA>",
    "IN_ABHA_ADDRESS": "<ABHA>",
    "IN_AADHAAR_LIKE": "<ID_NUMBER>",
    "IN_AADHAAR": "<ID_NUMBER>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "DATE_OF_BIRTH": "<DOB>",
}
REQUESTED_ENTITIES = sorted(set(PLACEHOLDERS) - {"IN_AADHAAR"})

_HONORIFIC = r"(?:Mr|Mrs|Ms|Miss|Mstr|Master|Dr|Shri|Shree|Sri|Smt|Kumari|Kum|Baby|Sh)"
_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}"


@dataclass(frozen=True)
class PatternSpec:
    entity: str
    regex: str
    score: float
    flags: int = 0
    group: int = 0  # capture group holding the identifier (0 = whole match)
    name_like: bool = False  # filter through the clinical/corpus vocabulary before redacting


PATTERNS: tuple[PatternSpec, ...] = (
    PatternSpec(
        "IN_UHID_MRN",
        r"\b(?:UHID|MRN|IPD?\s?No\.?|OPD?\s?No\.?|CR\s?No\.?|Hosp(?:ital)?\s?(?:No\.?|ID)|"
        r"Reg(?:istration)?\s?No\.?|Patient\s?ID|Bed\s?Head\s?Ticket)\s*[:#.\-]?\s*[A-Za-z0-9][A-Za-z0-9/\-]{3,19}\b",
        0.95,
        re.IGNORECASE,
    ),
    PatternSpec("IN_UHID_MRN", r"\b[A-Z]{2,5}\d{6,12}\b", 0.6),
    PatternSpec("IN_ABHA_NUMBER", r"(?<!\d)\d{2}[\s-]\d{4}[\s-]\d{4}[\s-]\d{4}(?![\d])|(?<!\d)\d{14}(?!\d)", 0.9),
    PatternSpec("IN_ABHA_ADDRESS", r"\b[A-Za-z0-9._]{3,32}@(?:abdm|sbx|ndhm)\b", 0.95, re.IGNORECASE),
    PatternSpec("IN_AADHAAR_LIKE", r"(?<!\d[\s-])(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?![\s-]?\d)", 0.85),
    PatternSpec("IN_PHONE", r"(?<![\d+])(?:(?:\+|00)91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?![\s-]?\d)", 0.85),
    PatternSpec("IN_PHONE", r"(?<!\d)0\d{2,4}[\s-]\d{6,8}(?!\d)", 0.7),
    PatternSpec("EMAIL_ADDRESS", r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b", 0.95),
    PatternSpec(
        "DATE_OF_BIRTH",
        r"\b(?:DOB|D\.O\.B\.?|date\s+of\s+birth|born\s+on)\s*[:\-]?\s*\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}",
        0.95,
        re.IGNORECASE,
    ),
    PatternSpec("PERSON", rf"\b{_HONORIFIC}\.?\s+{_NAME}", 0.9),
    # "patient named X", "pt called X Y", "patient X Y", "name: X"
    PatternSpec(
        "PERSON",
        rf"\b(?:[Pp]atient|[Pp]t\.?|[Nn]ame)(?:\s+(?:named|called|name\s*is|is)|\s*:)?\s+({_NAME})",
        0.85,
        group=1,
        name_like=True,
    ),
    # Capitalised unknown word(s) right after a person-directed preposition/verb: "give X to Anil".
    PatternSpec(
        "PERSON",
        r"\b(?:to|for|give|gave|with|on|about|of)\s+([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b",
        0.6,
        group=1,
        name_like=True,
    ),
)

_VOCAB_FILE = Path(__file__).with_name("clinical_terms.txt")


@lru_cache
def clinical_vocabulary() -> frozenset[str]:
    words: set[str] = set()
    if _VOCAB_FILE.exists():
        for line in _VOCAB_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip().lower()
            if line and not line.startswith("#"):
                words.update(re.findall(r"[a-z][a-z0-9-]+", line))
    return frozenset(words)


@dataclass(frozen=True)
class RedactedEntity:
    entity_type: str
    start: int
    end: int


@dataclass
class RedactionResult:
    text: str
    entities: list[RedactedEntity] = field(default_factory=list)
    engine: str = "regex"

    @property
    def changed(self) -> bool:
        return bool(self.entities)

    @property
    def entity_types(self) -> list[str]:
        return sorted({e.entity_type for e in self.entities})


@dataclass
class _Span:
    entity: str
    start: int
    end: int
    score: float
    from_ner: bool = False


_extra_vocabulary: set[str] = set()


def add_vocabulary(words: set[str] | list[str]) -> None:
    """Register non-name words (e.g. every word in the approved corpus, branch names)."""
    _extra_vocabulary.update(w.lower() for w in words if w)


def _regex_spans(text: str) -> list[_Span]:
    spans: list[_Span] = []
    for spec in PATTERNS:
        for match in re.finditer(spec.regex, text, spec.flags):
            start, end = match.span(spec.group)
            if spec.name_like:
                sub = _person_subspan(text, start, end)
                if sub is None:
                    continue
                start, end = sub
            if end > start:
                spans.append(_Span(spec.entity, start, end, spec.score))
    return spans


def _person_subspan(text: str, start: int, end: int) -> tuple[int, int] | None:
    """Shrink an NER PERSON span to its non-clinical tokens (None if nothing name-like remains)."""
    vocab = clinical_vocabulary() | _extra_vocabulary
    keep: list[tuple[int, int]] = []
    for match in re.finditer(r"[A-Za-z][A-Za-z'-]*", text[start:end]):
        token = match.group()
        if token.lower() in vocab or (token.isupper() and len(token) <= 6) or not token[0].isupper():
            continue
        keep.append((start + match.start(), start + match.end()))
    if not keep:
        return None
    return keep[0][0], keep[-1][1]


def _resolve_overlaps(spans: list[_Span]) -> list[_Span]:
    """Merge overlapping spans; the merged span keeps the higher-scoring entity type."""
    merged: list[_Span] = []
    for span in sorted(spans, key=lambda s: (s.start, -(s.end - s.start))):
        if merged and span.start < merged[-1].end:
            last = merged[-1]
            winner = last if last.score >= span.score else span
            merged[-1] = _Span(winner.entity, last.start, max(last.end, span.end), max(last.score, span.score))
        else:
            merged.append(span)
    return merged


def _apply(text: str, spans: list[_Span]) -> str:
    out: list[str] = []
    cursor = 0
    for span in spans:
        out.append(text[cursor : span.start])
        out.append(PLACEHOLDERS.get(span.entity, "<PII>"))
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)


class PIIRedactor:
    def __init__(self, engine: str = "presidio") -> None:
        self._requested_engine = engine
        self._analyzer: Any = None
        self._anonymizer: Any = None
        self._lock = threading.Lock()
        self._ready = False
        self.engine = "regex"

    def _init_presidio(self) -> None:
        if self._ready:
            return
        with self._lock:
            if self._ready:
                return
            self._ready = True
            if self._requested_engine != "presidio":
                return
            try:
                from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer, RecognizerRegistry
                from presidio_analyzer.nlp_engine import NlpEngineProvider
                from presidio_anonymizer import AnonymizerEngine

                provider = NlpEngineProvider(
                    nlp_configuration={
                        "nlp_engine_name": "spacy",
                        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
                    }
                )
                nlp_engine = provider.create_engine()
                registry = RecognizerRegistry(supported_languages=["en"])
                registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=["en"])
                by_entity: dict[str, list[PatternSpec]] = {}
                for spec in PATTERNS:
                    if spec.group == 0 and not spec.name_like:
                        by_entity.setdefault(spec.entity, []).append(spec)
                for entity, specs in by_entity.items():
                    # Presidio patterns are case-sensitive; inline the IGNORECASE flag where needed.
                    patterns = [
                        Pattern(
                            name=f"{entity.lower()}_{i}",
                            regex=("(?i)" if s.flags & re.IGNORECASE else "") + s.regex,
                            score=s.score,
                        )
                        for i, s in enumerate(specs)
                    ]
                    registry.add_recognizer(
                        PatternRecognizer(
                            supported_entity=entity,
                            patterns=patterns,
                            name=f"protocite_{entity.lower()}",
                            supported_language="en",
                            # Presidio defaults to IGNORECASE, which breaks capitalised-name patterns.
                            global_regex_flags=re.DOTALL | re.MULTILINE,
                        )
                    )
                self._analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["en"])
                self._anonymizer = AnonymizerEngine()  # type: ignore[no-untyped-call]
                self.engine = "presidio"
            except Exception as exc:  # pragma: no cover - depends on optional runtime deps
                log.warning("presidio_unavailable_falling_back_to_regex", error_type=type(exc).__name__)
                self._analyzer = None

    def warmup(self) -> None:
        self._init_presidio()
        self.redact("warmup")

    def redact(self, text: str) -> RedactionResult:
        self._init_presidio()
        spans = _regex_spans(text)  # always on, including the group-capture patterns
        if self._analyzer is not None:
            for result in self._analyzer.analyze(
                text=text, language="en", entities=REQUESTED_ENTITIES, score_threshold=0.5
            ):
                metadata = result.recognition_metadata or {}
                from_ner = "Spacy" in str(metadata.get("recognizer_name", ""))
                start, end = result.start, result.end
                if result.entity_type == "PERSON" and from_ner:
                    sub = _person_subspan(text, start, end)
                    if sub is None:
                        continue
                    start, end = sub
                if result.entity_type == "PHONE_NUMBER" and len(re.sub(r"\D", "", text[start:end])) < 10:
                    continue
                spans.append(_Span(result.entity_type, start, end, result.score, from_ner))
        resolved = _resolve_overlaps(spans)
        if not resolved:
            return RedactionResult(text=text, engine=self.engine)
        if self._anonymizer is not None:
            from presidio_anonymizer.entities import OperatorConfig, RecognizerResult

            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=[RecognizerResult(s.entity, s.start, s.end, s.score) for s in resolved],
                operators={
                    entity: OperatorConfig("replace", {"new_value": placeholder})
                    for entity, placeholder in PLACEHOLDERS.items()
                }
                | {"DEFAULT": OperatorConfig("replace", {"new_value": "<PII>"})},
            )
            redacted = anonymized.text
        else:
            redacted = _apply(text, resolved)
        entities = [RedactedEntity(s.entity, s.start, s.end) for s in resolved]
        return RedactionResult(text=redacted, entities=entities, engine=self.engine)


_default: PIIRedactor | None = None


def get_redactor(engine: str = "presidio") -> PIIRedactor:
    global _default
    if _default is None:
        _default = PIIRedactor(engine)
    return _default


def redact(text: str) -> RedactionResult:
    return get_redactor().redact(text)
