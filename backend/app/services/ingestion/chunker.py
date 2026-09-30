"""Clause-level chunking with section paths.

Rules (ADR 0002):
* Numbered headings (4, 4.2, 4.2.1, A., A.1, Appendix B) open a clause; the number is its
  `section_path`. Content before the first numbered heading is the preamble, path "0".
* One chunk per clause that has body content (parent headings with no own text emit nothing).
* (a)/(b)/(i) sub-clauses stay in their parent chunk and are recorded in `covered_paths`.
* Tiny clauses (< min_tokens) merge with the next sibling (else the previous one); the merged
  chunk's path is "4.1-4.2" and `covered_paths` lists every clause it contains.
* Long clauses (> max_tokens) split at block, then sentence, boundaries: "4.2#1", "4.2#2".
* Tables: one chunk per table (`is_table`), plus one chunk per row (with the header) for tables
  longer than `table_row_split` rows. A tiny intro paragraph is kept as the table's caption.
* `context_header` "[{doc_code} v{version} §{path}] {heading}" is used for embedding / keyword
  search only; `text` is the verbatim clause body.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.ingestion.parser import Block, ParsedDocument, rows_to_markdown, split_table_row

# Approximates sub-word model tokens: words plus punctuation marks (one word is ~1.3 tokens).
_TOKEN = re.compile(r"\w+|[^\w\s]")
_NUM_HEADING = re.compile(r"^(?:section|clause|§)?\s*(\d{1,2}(?:\.\d{1,2}){0,4})\.?(?:\s+|$)(.*)$", re.IGNORECASE)
_APPENDIX = re.compile(r"^(?:appendix|annex(?:ure)?|schedule)\s+([A-Z])\b[\s.:—–-]*(.*)$", re.IGNORECASE)
_LETTER_NUM = re.compile(r"^([A-Z]\.\d{1,2}(?:\.\d{1,2}){0,3})\.?\s+(.+)$")
_LETTER = re.compile(r"^([A-Z])\.\s+(.+)$")
_SUBCLAUSE = re.compile(r"^\s*(?:[-*+]\s+)?\(([a-z]{1,2}|[ivx]{1,5})\)\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9(])")


def count_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


def parse_heading_number(text: str) -> tuple[str | None, str]:
    """Return (section number, heading title) for a heading line; number is None if unnumbered."""
    stripped = text.strip().lstrip("#").strip()
    for pattern in (_APPENDIX, _LETTER_NUM, _NUM_HEADING, _LETTER):
        match = pattern.match(stripped)
        if match:
            number = match.group(1).rstrip(".")
            title = match.group(2).strip(" .:—–-") or stripped
            return number, title
    return None, stripped


def parent_path(path: str) -> str:
    base = path.split("#", 1)[0].split("-", 1)[0]
    return base.rsplit(".", 1)[0] if "." in base else ""


@dataclass
class ChunkDraft:
    ordinal: int
    section_path: str
    covered_paths: list[str]
    heading: str
    text: str
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    is_table: bool = False
    bbox: dict[str, Any] | None = None
    token_count: int = 0
    context_header: str = ""

    @property
    def embedding_text(self) -> str:
        return f"{self.context_header}\n{self.text}"


@dataclass
class _Clause:
    path: str
    heading: str
    blocks: list[Block] = field(default_factory=list)
    sub_paths: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkerConfig:
    min_tokens: int = 40
    max_tokens: int = 400
    table_row_split: int = 15


def _clauses(doc: ParsedDocument) -> list[_Clause]:
    clauses: list[_Clause] = []
    current = _Clause(path="0", heading="Document information")
    seen_numbered = False
    for block in doc.blocks:
        if block.type == "heading":
            number, title = parse_heading_number(block.text)
            if number is None:
                if not seen_numbered and not current.blocks and block.level <= 1:
                    current.heading = title  # document title names the preamble
                else:
                    current.blocks.append(block)  # un-numbered sub-heading stays inside the clause
                continue
            seen_numbered = True
            clauses.append(current)
            current = _Clause(path=number, heading=title)
            continue
        sub = _SUBCLAUSE.match(block.text)
        if sub:
            current.sub_paths.append(f"{current.path}({sub.group(1)})")
        current.blocks.append(block)
    clauses.append(current)
    return clauses


def _span(blocks: list[Block]) -> tuple[int, int, int, int, dict[str, Any] | None]:
    pages = [b.page for b in blocks]
    boxes = [b.bbox for b in blocks if b.bbox]
    bbox: dict[str, Any] | None = None
    if boxes:
        by_page: dict[int, dict[str, float]] = {}
        for box in boxes:
            page = int(box["page"])
            agg = by_page.setdefault(page, {"x0": 1.0, "y0": 1.0, "x1": 0.0, "y1": 0.0})
            agg["x0"], agg["y0"] = min(agg["x0"], box["x0"]), min(agg["y0"], box["y0"])
            agg["x1"], agg["y1"] = max(agg["x1"], box["x1"]), max(agg["y1"], box["y1"])
        bbox = {"boxes": [{"page": p, **coords} for p, coords in sorted(by_page.items())]}
    return (
        min(pages),
        max(pages),
        min(b.char_start for b in blocks),
        max(b.char_end for b in blocks),
        bbox,
    )


def _split_long(blocks: list[Block], max_tokens: int) -> list[list[Block]]:
    """Group blocks into parts of <= max_tokens, splitting oversized blocks at sentence boundaries."""
    units: list[Block] = []
    for block in blocks:
        if count_tokens(block.text) <= max_tokens:
            units.append(block)
            continue
        cursor = 0
        for sentence in _SENTENCE_END.split(block.text):
            local = block.text.find(sentence, cursor)
            local = cursor if local < 0 else local
            cursor = local + len(sentence)
            units.append(
                Block(
                    block.type,
                    sentence,
                    page=block.page,
                    char_start=block.char_start + local,
                    char_end=block.char_start + local + len(sentence),
                    bbox=block.bbox,
                )
            )
    parts: list[list[Block]] = []
    current: list[Block] = []
    tokens = 0
    for unit in units:
        n = count_tokens(unit.text)
        if current and tokens + n > max_tokens:
            parts.append(current)
            current, tokens = [], 0
        current.append(unit)
        tokens += n
    if current:
        parts.append(current)
    return parts


def _table_rows(block: Block) -> list[list[str]]:
    if block.rows:
        return block.rows
    return [
        split_table_row(line)
        for line in block.text.splitlines()
        if line.strip().startswith("|") and not re.match(r"^\s*\|?\s*:?-{3,}", line)
    ]


def chunk_document(
    doc: ParsedDocument,
    *,
    doc_code: str,
    version_label: str,
    config: ChunkerConfig | None = None,
) -> list[ChunkDraft]:
    cfg = config or ChunkerConfig()
    drafts: list[ChunkDraft] = []

    def emit(path: str, covered: list[str], heading: str, blocks: list[Block], text: str, is_table: bool) -> None:
        page_start, page_end, c0, c1, bbox = _span(blocks)
        drafts.append(
            ChunkDraft(
                ordinal=len(drafts),
                section_path=path,
                covered_paths=covered,
                heading=heading,
                text=text.strip(),
                page_start=page_start,
                page_end=page_end,
                char_start=c0,
                char_end=c1,
                is_table=is_table,
                bbox=bbox,
                token_count=count_tokens(text),
            )
        )

    for clause in _clauses(doc):
        covered = [clause.path, *clause.sub_paths]
        text_blocks = [b for b in clause.blocks if b.type != "table"]
        tables = [b for b in clause.blocks if b.type == "table"]
        text = "\n\n".join(b.text for b in text_blocks)
        caption = ""
        if tables and len(tables) == 1 and count_tokens(text) < cfg.min_tokens:
            caption, text_blocks = text, []  # tiny intro becomes the table caption
        if text_blocks:
            if count_tokens(text) > cfg.max_tokens:
                parts = _split_long(text_blocks, cfg.max_tokens)
                for n, part in enumerate(parts, start=1):
                    emit(
                        f"{clause.path}#{n}",
                        covered,
                        clause.heading,
                        part,
                        "\n\n".join(b.text for b in part),
                        False,
                    )
            else:
                emit(clause.path, covered, clause.heading, text_blocks, text, False)
        for table in tables:
            rows = _table_rows(table)
            table_md = table.text if table.text.lstrip().startswith("|") else rows_to_markdown(rows)
            body = f"{caption}\n\n{table_md}" if caption else table_md
            emit(clause.path, covered, clause.heading, [table], body, True)
            if len(rows) - 1 > cfg.table_row_split:
                header = rows[0]
                for r, row in enumerate(rows[1:], start=1):
                    emit(
                        clause.path,
                        covered,
                        f"{clause.heading} — row {r}",
                        [table],
                        rows_to_markdown([header, row]),
                        True,
                    )

    drafts = _merge_tiny(drafts, cfg.min_tokens)
    for index, draft in enumerate(drafts):
        draft.ordinal = index
        draft.context_header = f"[{doc_code} v{version_label} §{draft.section_path}] {draft.heading}"
    return drafts


def _merge_pair(a: ChunkDraft, b: ChunkDraft) -> ChunkDraft:
    first, last = a.section_path.split("-")[0], b.section_path.split("-")[-1]
    boxes = [*(a.bbox or {}).get("boxes", []), *(b.bbox or {}).get("boxes", [])]
    text = f"{a.text}\n\n{b.heading}\n{b.text}"
    return ChunkDraft(
        ordinal=a.ordinal,
        section_path=f"{first}-{last}",
        covered_paths=[*a.covered_paths, *[p for p in b.covered_paths if p not in a.covered_paths]],
        heading=f"{a.heading}; {b.heading}",
        text=text,
        page_start=min(a.page_start, b.page_start),
        page_end=max(a.page_end, b.page_end),
        char_start=min(a.char_start, b.char_start),
        char_end=max(a.char_end, b.char_end),
        is_table=False,
        bbox={"boxes": boxes} if boxes else None,
        token_count=count_tokens(text),
    )


def _mergeable(draft: ChunkDraft) -> bool:
    return not draft.is_table and draft.section_path != "0" and "#" not in draft.section_path


def _merge_tiny(drafts: list[ChunkDraft], min_tokens: int) -> list[ChunkDraft]:
    result = list(drafts)
    i = 0
    while i < len(result):
        draft = result[i]
        if not _mergeable(draft) or draft.token_count >= min_tokens:
            i += 1
            continue
        nxt = result[i + 1] if i + 1 < len(result) else None
        prev = result[i - 1] if i > 0 else None
        if nxt and _mergeable(nxt) and parent_path(nxt.section_path) == parent_path(draft.section_path):
            result[i : i + 2] = [_merge_pair(draft, nxt)]
            continue  # re-check the merged chunk
        if prev and _mergeable(prev) and parent_path(prev.section_path) == parent_path(draft.section_path):
            result[i - 1 : i + 1] = [_merge_pair(prev, draft)]
            i = max(i - 1, 0)
            continue
        i += 1
    return result
