from __future__ import annotations

from app.services.ingestion.chunker import (
    ChunkerConfig,
    chunk_document,
    count_tokens,
    parent_path,
    parse_heading_number,
)
from app.services.ingestion.parser import parse_markdown

LONG = " ".join(f"Sentence number {i} explains one more detail of the clause in plain words." for i in range(60))
PAD = "This padding sentence adds enough ordinary words to keep the clause well above the merge threshold."

DOC = f"""# P-TEST-01 Test Protocol

> SYNTHETIC — FOR DEMO ONLY.

## 1 Purpose

This protocol exists to test the clause chunker with enough words in this clause so that it stays a
single chunk and is not merged with any sibling clause at all. {PAD}

## 4 Dosing

All doses in this section are weight based and the prescriber documents the weight used on the chart
before the first dose is given to the patient. {PAD}

### 4.1 Initial dose

Give the loading dose as described here, with enough words in the clause to stay above the merge
threshold of forty tokens that the chunker applies to tiny clauses. {PAD}

### 4.2 Nomogram

Adjust the infusion according to the table.

| aPTT | Action |
|---|---|
| Below 40 | Increase |
| Above 100 | Hold |

### 4.3 Monitoring

- (a) Repeat the aPTT 6 hours after every rate change and record it on the chart with the time.
- (b) Check the platelet count daily and escalate a fall of more than half from the baseline value.

## 5 Tiny one

Short.

## 6 Tiny two

Also short.

## 7 Long clause

{LONG}

## Appendix A Forms

The appendix lists the forms used with this protocol, including the infusion chart and the escalation
record, with enough words to stand on its own as one chunk. {PAD}
"""


def _chunks(text: str = DOC, **cfg: int):
    return chunk_document(
        parse_markdown(text),
        doc_code="P-TEST-01",
        version_label="1",
        config=ChunkerConfig(**cfg) if cfg else None,
    )


def test_heading_number_parsing() -> None:
    assert parse_heading_number("4.2.1 Rate change") == ("4.2.1", "Rate change")
    assert parse_heading_number("Section 5 Scope") == ("5", "Scope")
    assert parse_heading_number("Appendix B — Forms") == ("B", "Forms")
    assert parse_heading_number("A.1 Checklist") == ("A.1", "Checklist")
    assert parse_heading_number("C. Contacts") == ("C", "Contacts")
    assert parse_heading_number("Background") == (None, "Background")


def test_parent_path() -> None:
    assert parent_path("4.2.1") == "4.2"
    assert parent_path("4") == ""
    assert parent_path("4.1-4.2") == "4"
    assert parent_path("7#2") == ""


def test_one_chunk_per_leaf_clause_with_section_paths() -> None:
    paths = [c.section_path for c in _chunks()]
    assert "1" in paths and "4" in paths and "4.1" in paths and "4.3" in paths
    assert "A" in paths
    assert paths[0] == "0"  # preamble keeps its own path


def test_parent_intro_text_becomes_its_own_chunk() -> None:
    chunk = next(c for c in _chunks() if c.section_path == "4")
    assert "weight based" in chunk.text


def test_subclauses_are_recorded_in_covered_paths() -> None:
    chunk = next(c for c in _chunks() if c.section_path == "4.3")
    assert chunk.covered_paths == ["4.3", "4.3(a)", "4.3(b)"]


def test_tiny_siblings_merge_and_record_every_clause() -> None:
    merged = next(c for c in _chunks() if c.section_path == "5-6")
    assert merged.covered_paths == ["5", "6"]
    assert "Short." in merged.text and "Also short." in merged.text


def test_long_clause_splits_at_sentence_boundaries() -> None:
    parts = [c for c in _chunks() if c.section_path.startswith("7#")]
    assert [p.section_path for p in parts] == [f"7#{i}" for i in range(1, len(parts) + 1)]
    assert len(parts) >= 2
    assert all(p.token_count <= 400 for p in parts)
    assert all(p.text.rstrip().endswith(".") for p in parts)  # split between sentences
    assert all("7" in p.covered_paths for p in parts)


def test_table_is_its_own_chunk_with_tiny_intro_as_caption() -> None:
    chunks = [c for c in _chunks() if c.section_path == "4.2"]
    assert len(chunks) == 1
    table = chunks[0]
    assert table.is_table
    assert table.text.startswith("Adjust the infusion according to the table.")
    assert "| Above 100 | Hold |" in table.text


def test_big_tables_also_get_one_chunk_per_row_with_header() -> None:
    rows = "\n".join(f"| Row {i} | Value {i} |" for i in range(20))
    doc = f"## 3 Big table\n\nIntro text.\n\n| Key | Value |\n|---|---|\n{rows}\n"
    chunks = _chunks(doc)
    row_chunks = [c for c in chunks if " — row " in c.heading]
    assert len(row_chunks) == 20
    assert all(c.text.startswith("| Key | Value |") for c in row_chunks)
    assert all(c.is_table and c.section_path == "3" for c in row_chunks)


def test_small_tables_do_not_get_row_chunks() -> None:
    assert not [c for c in _chunks() if " — row " in c.heading]


def test_context_header_and_ordinals() -> None:
    chunks = _chunks()
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))
    first = next(c for c in chunks if c.section_path == "4.1")
    assert first.context_header == "[P-TEST-01 v1 §4.1] Initial dose"
    assert first.embedding_text.startswith(first.context_header)


def test_char_offsets_point_back_to_the_source() -> None:
    parsed = parse_markdown(DOC)
    chunk = next(c for c in chunk_document(parsed, doc_code="P", version_label="1") if c.section_path == "4.1")
    assert "Give the loading dose" in parsed.full_text[chunk.char_start : chunk.char_end]


def test_token_count_counts_words_and_punctuation() -> None:
    assert count_tokens("Give 80 units/kg IV.") == 7  # Give, 80, units, /, kg, IV, .
