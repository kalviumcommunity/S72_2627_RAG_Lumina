"""PII redaction (safety-critical). All identifiers below are synthetic."""

from __future__ import annotations

import pytest

from app.services.safety.pii_redaction import PIIRedactor

CASES = [
    ("Patient Ramesh Kumar needs heparin", ["Ramesh", "Kumar"], "<PERSON>"),
    ("Mrs. Sunita Sharma is on meropenem", ["Sunita", "Sharma"], "<PERSON>"),
    ("Can I give Clexane to Anil in ICU?", ["Anil"], "<PERSON>"),
    ("pt called Arjun Mehta, bed 4", ["Arjun", "Mehta"], "<PERSON>"),
    ("Call her son on 9876543210", ["9876543210"], "<PHONE>"),
    ("Family number +91 98765 43210", ["98765 43210"], "<PHONE>"),
    ("Landline 022-24567890 for the ward", ["24567890"], "<PHONE>"),
    ("UHID 20231145 heparin rate?", ["20231145"], "<MRN>"),
    ("MRN: DHN00123456 needs review", ["DHN00123456"], "<MRN>"),
    ("IP No. 2026/0456 admitted today", ["2026/0456"], "<MRN>"),
    ("ABHA 91-2345-6789-0123 on file", ["2345-6789-0123"], "<ABHA>"),
    ("ABHA address ravi.k@abdm", ["ravi.k@abdm"], "<ABHA>"),
    ("Aadhaar 2345 6789 0123 given", ["2345 6789 0123"], "<ID_NUMBER>"),
    ("email ravi.k@example.com", ["ravi.k@example.com"], "<EMAIL>"),
    ("DOB 12/03/1980, on warfarin", ["12/03/1980"], "<DOB>"),
]

CLINICAL = [
    "What is the heparin infusion nomogram rate change for aPTT above 100?",
    "Does Tazocin need AMS approval? Is Meropenem restricted?",
    "Heparin bolus 80 units/kg and repeat aPTT at 6 hours; call ext 2210",
    "Massive transfusion protocol: what is in pack 1 at Riverside?",
    "What changed in the circular of September for Hillview?",
    "Give 30 mL/kg crystalloid within 3 hours for lactate of 4 mmol/L",
    "Protocol P-ICU-07 section 4.2 and circular C-2026-09",
]


@pytest.fixture(scope="module", params=["presidio", "regex"])
def redactor(request: pytest.FixtureRequest) -> PIIRedactor:
    r = PIIRedactor(request.param)
    r.warmup()
    if request.param == "presidio":
        assert r.engine == "presidio", "Presidio + en_core_web_sm should be installed"
    return r


@pytest.mark.parametrize(("text", "secrets", "placeholder"), CASES)
def test_identifiers_are_removed(redactor: PIIRedactor, text: str, secrets: list[str], placeholder: str) -> None:
    result = redactor.redact(text)
    for secret in secrets:
        assert secret not in result.text, f"{secret!r} leaked: {result.text!r}"
    assert placeholder in result.text
    assert result.changed


@pytest.mark.parametrize("text", CLINICAL)
def test_clinical_questions_are_untouched(redactor: PIIRedactor, text: str) -> None:
    result = redactor.redact(text)
    assert result.text == text
    assert not result.changed


def test_result_does_not_retain_the_original_values(redactor: PIIRedactor) -> None:
    result = redactor.redact("Mr Ramesh Kumar UHID 20231145")
    stored = repr(result.entities)
    assert "Ramesh" not in stored and "20231145" not in stored


def test_overlapping_detections_produce_one_placeholder(redactor: PIIRedactor) -> None:
    result = redactor.redact("ABHA 91-2345-6789-0123")
    assert result.text.count("<") == 1
