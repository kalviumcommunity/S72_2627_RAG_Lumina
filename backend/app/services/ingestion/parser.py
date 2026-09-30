"""Parse source files into structured blocks with page and character offsets.

Markdown / text: own line-based parser (exact character offsets into the source file).
PDF: docling when DOCLING_ENABLED=true, otherwise pypdf text per page; pages with no text layer
are rasterised and OCR'd (see ocr.py). DOCX: python-docx. HTML: BeautifulSoup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.core.logging import get_logger

log = get_logger(__name__)

BlockType = Literal["heading", "paragraph", "table", "list_item"]

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf", ".docx", ".html", ".htm"}

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d{1,3}[.)]|\([a-z]{1,3}\)|\([ivx]{1,5}\)|[a-z][.)])\s+")
# Numbered heading line in plain text (PDF/OCR): "4.2 Antibiotic timing", "SECTION 3 — SCOPE".
_TEXT_HEADING = re.compile(
    r"^(?:(?:[Ss]ection|SECTION|[Cc]lause|CLAUSE)\s+)?(\d{1,2}(?:\.\d{1,2}){0,3}|[A-Z])[.)]?\s+([A-Z][^\n]{1,90})$"
)


@dataclass
class Block:
    type: BlockType
    text: str
    page: int = 1
    char_start: int = 0
    char_end: int = 0
    level: int = 0
    rows: list[list[str]] | None = None
    bbox: dict[str, Any] | None = None  # {"page", "x0", "y0", "x1", "y1"} normalised to 0..1


@dataclass
class ParsedDocument:
    blocks: list[Block]
    full_text: str
    page_count: int
    parser: str
    warnings: list[dict[str, Any]] = field(default_factory=list)
    ocr_page_confidence: dict[int, float] = field(default_factory=dict)

    @property
    def ocr_min_confidence(self) -> float | None:
        return min(self.ocr_page_confidence.values()) if self.ocr_page_confidence else None


class ParseError(Exception):
    pass


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(norm[0]) + " |", "|" + "|".join(["---"] * width) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------------------
# Markdown / plain text
# --------------------------------------------------------------------------------------------------


def parse_markdown(text: str) -> ParsedDocument:
    """Line-based Markdown parser that keeps exact source offsets for every block."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    offsets: list[int] = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1

    blocks: list[Block] = []
    i = 0
    n = len(lines)

    def end_of(idx: int) -> int:
        return offsets[idx] + len(lines[idx])

    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped or stripped in ("---", "***", "___"):
            i += 1
            continue
        heading = _MD_HEADING.match(line)
        if heading:
            blocks.append(
                Block(
                    "heading",
                    heading.group(2).strip(),
                    char_start=offsets[i],
                    char_end=end_of(i),
                    level=len(heading.group(1)),
                )
            )
            i += 1
            continue
        if stripped.startswith("|"):
            start = i
            rows: list[list[str]] = []
            while i < n and lines[i].strip().startswith("|"):
                if not _MD_TABLE_SEP.match(lines[i]):
                    rows.append(split_table_row(lines[i]))
                i += 1
            raw = "\n".join(lines[start:i])
            blocks.append(Block("table", raw, char_start=offsets[start], char_end=end_of(i - 1), rows=rows))
            continue
        if _LIST_ITEM.match(line):
            start = i
            i += 1
            # continuation lines: indented, non-empty, not a new item / heading / table
            while i < n and lines[i].strip() and lines[i].startswith(("  ", "\t")) and not _LIST_ITEM.match(lines[i]):
                i += 1
            raw = "\n".join(lines[start:i])
            blocks.append(Block("list_item", raw, char_start=offsets[start], char_end=end_of(i - 1)))
            continue
        start = i
        i += 1
        while (
            i < n
            and lines[i].strip()
            and not _MD_HEADING.match(lines[i])
            and not lines[i].strip().startswith("|")
            and not _LIST_ITEM.match(lines[i])
        ):
            i += 1
        raw = "\n".join(lines[start:i])
        blocks.append(Block("paragraph", raw, char_start=offsets[start], char_end=end_of(i - 1)))
    return ParsedDocument(blocks=blocks, full_text=text, page_count=1, parser="markdown")


def _flush_paragraph(paragraph: list[str], page_no: int, start: int, blocks: list[Block]) -> None:
    """Emit the pending paragraph (or list item) lines as one block and clear the buffer."""
    if not paragraph:
        return
    raw = "\n".join(paragraph)
    kind: BlockType = "list_item" if _LIST_ITEM.match(paragraph[0]) else "paragraph"
    blocks.append(Block(kind, raw, page=page_no, char_start=start, char_end=start + len(raw)))
    paragraph.clear()


def blocks_from_plain_pages(pages: list[str], page_offsets: dict[int, int] | None = None) -> tuple[list[Block], str]:
    """Heuristic structure for extracted PDF/OCR text: numbered heading lines + paragraphs.

    `page_offsets`, if given, is filled with {page_number: offset of that page in the full text}.
    """
    blocks: list[Block] = []
    full: list[str] = []
    offset = 0
    for idx, page_text in enumerate(pages):
        page_no = idx + 1
        if page_offsets is not None:
            page_offsets[page_no] = offset
        text = page_text.replace("\r\n", "\n")
        paragraph: list[str] = []
        para_start = offset

        cursor = offset
        for line in text.split("\n"):
            stripped = line.strip()
            line_start = cursor
            cursor += len(line) + 1
            if not stripped:
                _flush_paragraph(paragraph, page_no, para_start, blocks)
                continue
            words = stripped.split()
            looks_heading = _TEXT_HEADING.match(stripped) and len(words) <= 9 and not stripped.endswith((".", ",", ";"))
            if looks_heading:
                _flush_paragraph(paragraph, page_no, para_start, blocks)
                blocks.append(
                    Block(
                        "heading",
                        stripped,
                        page=page_no,
                        char_start=line_start,
                        char_end=line_start + len(line),
                        level=2,
                    )
                )
                continue
            if _LIST_ITEM.match(stripped):
                _flush_paragraph(paragraph, page_no, para_start, blocks)
            if not paragraph:
                para_start = line_start
            paragraph.append(line.rstrip())
        _flush_paragraph(paragraph, page_no, para_start, blocks)
        full.append(text)
        offset += len(text) + 2  # pages are joined with a blank line
    return blocks, "\n\n".join(full)


# --------------------------------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------------------------------


def parse_pdf(path: Path, *, ocr_languages: str, ocr_dpi: int, docling_enabled: bool) -> ParsedDocument:
    if docling_enabled:
        try:
            return _parse_with_docling(path)
        except Exception as exc:  # fall back, but record why
            warning = {
                "code": "docling_failed",
                "message": f"docling failed ({type(exc).__name__}); used pypdf",
            }
            doc = _parse_pdf_basic(path, ocr_languages=ocr_languages, ocr_dpi=ocr_dpi)
            doc.warnings.insert(0, warning)
            return doc
    return _parse_pdf_basic(path, ocr_languages=ocr_languages, ocr_dpi=ocr_dpi)


def _parse_pdf_basic(path: Path, *, ocr_languages: str, ocr_dpi: int) -> ParsedDocument:
    from pypdf import PdfReader

    from app.services.ingestion import ocr

    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ParseError(f"Unreadable PDF: {type(exc).__name__}") from exc
    warnings: list[dict[str, Any]] = []
    page_texts: list[str] = []
    ocr_conf: dict[int, float] = {}
    ocr_blocks: dict[int, list[Block]] = {}
    for index, page in enumerate(reader.pages):
        try:
            extracted = page.extract_text() or ""
        except Exception:
            extracted = ""
        if len(extracted.strip()) >= 20:
            page_texts.append(extracted)
            continue
        if not ocr.tesseract_available():
            warnings.append(
                {
                    "code": "ocr_unavailable",
                    "page": index + 1,
                    "message": "Page has no text layer and OCR is unavailable",
                }
            )
            page_texts.append("")
            continue
        result = ocr.ocr_pdf_page(path, index, languages=ocr_languages, dpi=ocr_dpi)
        ocr_conf[index + 1] = result.mean_confidence
        page_texts.append(result.text)
        ocr_blocks[index + 1] = result.blocks
    page_offsets: dict[int, int] = {}
    blocks, full_text = blocks_from_plain_pages(page_texts, page_offsets)
    _attach_ocr_bboxes(blocks, ocr_blocks, page_offsets)
    if not full_text.strip():
        raise ParseError("No text could be extracted from the PDF")
    parser = "pypdf+tesseract" if ocr_conf else "pypdf"
    return ParsedDocument(
        blocks=blocks,
        full_text=full_text,
        page_count=len(reader.pages),
        parser=parser,
        warnings=warnings,
        ocr_page_confidence=ocr_conf,
    )


def _attach_ocr_bboxes(blocks: list[Block], ocr_blocks: dict[int, list[Block]], page_offsets: dict[int, int]) -> None:
    """Give blocks on OCR'd pages the bbox of the OCR paragraphs whose characters they contain."""
    for block in blocks:
        candidates = ocr_blocks.get(block.page)
        if not candidates:
            continue
        base = page_offsets.get(block.page, 0)
        start, end = block.char_start - base, block.char_end - base
        boxes = [cand.bbox for cand in candidates if cand.bbox and cand.char_start < end and cand.char_end > start]
        if boxes:
            block.bbox = {
                "page": block.page,
                "x0": min(b["x0"] for b in boxes),
                "y0": min(b["y0"] for b in boxes),
                "x1": max(b["x1"] for b in boxes),
                "y1": max(b["y1"] for b in boxes),
            }


def _parse_with_docling(path: Path) -> ParsedDocument:  # pragma: no cover - optional dependency
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(do_ocr=False, do_table_structure=True)
    converter = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})
    doc = converter.convert(str(path)).document
    blocks: list[Block] = []
    parts: list[str] = []
    offset = 0
    for item, level in doc.iterate_items():
        label = str(getattr(item, "label", "")).lower()
        page = item.prov[0].page_no if getattr(item, "prov", None) else 1
        if "table" in label:
            df = item.export_to_dataframe(doc=doc)
            rows = [list(map(str, df.columns))] + [list(map(str, r)) for r in df.values.tolist()]
            text = rows_to_markdown(rows)
            kind: BlockType = "table"
        else:
            text = getattr(item, "text", "") or ""
            kind = (
                "heading"
                if ("header" in label or "title" in label)
                else ("list_item" if "list" in label else "paragraph")
            )
            rows = None
        if not text.strip():
            continue
        blocks.append(
            Block(kind, text, page=page, char_start=offset, char_end=offset + len(text), level=level, rows=rows)
        )
        parts.append(text)
        offset += len(text) + 2
    if not blocks:
        raise ParseError("docling produced no content")
    return ParsedDocument(blocks=blocks, full_text="\n\n".join(parts), page_count=len(doc.pages), parser="docling")


# --------------------------------------------------------------------------------------------------
# DOCX / HTML
# --------------------------------------------------------------------------------------------------


def parse_docx(path: Path) -> ParsedDocument:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(str(path))
    except Exception as exc:
        raise ParseError(f"Unreadable DOCX: {type(exc).__name__}") from exc
    blocks: list[Block] = []
    parts: list[str] = []
    offset = 0

    def add(block: Block) -> None:
        nonlocal offset
        block.char_start, block.char_end = offset, offset + len(block.text)
        blocks.append(block)
        parts.append(block.text)
        offset += len(block.text) + 2

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name if para.style is not None else "") or ""
            if style.lower().startswith("heading") or style.lower() == "title":
                digits = re.findall(r"\d+", style)
                add(Block("heading", text, level=int(digits[0]) if digits else 1))
            elif "list" in style.lower():
                add(Block("list_item", text))
            else:
                add(Block("paragraph", text))
        elif tag == "tbl":
            table = Table(child, document)
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            if rows:
                add(Block("table", rows_to_markdown(rows), rows=rows))
    if not blocks:
        raise ParseError("DOCX contains no text")
    return ParsedDocument(blocks=blocks, full_text="\n\n".join(parts), page_count=1, parser="python-docx")


def parse_html(raw: str) -> ParsedDocument:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    blocks: list[Block] = []
    parts: list[str] = []
    offset = 0

    def add(block: Block) -> None:
        nonlocal offset
        block.char_start, block.char_end = offset, offset + len(block.text)
        blocks.append(block)
        parts.append(block.text)
        offset += len(block.text) + 2

    root = soup.body or soup
    for element in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "table"]):
        if element.name == "table":
            rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])] for tr in element.find_all("tr")]
            rows = [r for r in rows if any(r)]
            if rows:
                add(Block("table", rows_to_markdown(rows), rows=rows))
            continue
        if element.find_parent("table") is not None:
            continue
        text = element.get_text(" ", strip=True)
        if not text:
            continue
        if element.name.startswith("h"):
            add(Block("heading", text, level=int(element.name[1])))
        elif element.name == "li":
            add(Block("list_item", text))
        else:
            add(Block("paragraph", text))
    if not blocks:
        raise ParseError("HTML contains no text")
    return ParsedDocument(blocks=blocks, full_text="\n\n".join(parts), page_count=1, parser="beautifulsoup")


# --------------------------------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------------------------------


def parse_file(
    path: Path,
    *,
    ocr_languages: str = "eng",
    ocr_dpi: int = 300,
    docling_enabled: bool = False,
) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ParseError(f"Unsupported file type: {suffix or 'none'}")
    if suffix in (".md", ".markdown", ".txt"):
        return parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".pdf":
        return parse_pdf(path, ocr_languages=ocr_languages, ocr_dpi=ocr_dpi, docling_enabled=docling_enabled)
    if suffix == ".docx":
        return parse_docx(path)
    return parse_html(path.read_text(encoding="utf-8", errors="replace"))
