"""Tesseract OCR for pages without a text layer; records mean word confidence per page."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.services.ingestion.parser import Block

log = get_logger(__name__)


@dataclass
class OcrPage:
    text: str
    mean_confidence: float  # 0..1
    blocks: list[Block] = field(default_factory=list)  # one per OCR paragraph, with normalised bbox
    language: str = "eng"


def _configure_binary() -> str | None:
    import pytesseract

    from app.core.config import get_settings

    settings = get_settings()
    if settings.tessdata_prefix:
        os.environ["TESSDATA_PREFIX"] = settings.tessdata_prefix  # inherited by the tesseract subprocess
    configured = settings.tesseract_cmd or os.environ.get("TESSERACT_CMD") or shutil.which("tesseract")
    if configured:
        pytesseract.pytesseract.tesseract_cmd = configured
    return configured


@lru_cache
def tesseract_available() -> bool:
    try:
        import pytesseract

        if not _configure_binary():
            return False
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


@lru_cache
def resolve_languages(requested: str) -> str:
    """Keep only installed language packs (e.g. 'eng+hin' -> 'eng' when Hindi data is missing)."""
    import pytesseract

    try:
        installed = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    wanted = [lang for lang in requested.split("+") if lang in installed]
    if len(wanted) < len(requested.split("+")):
        log.warning("ocr_language_pack_missing", requested=requested, using="+".join(wanted) or "eng")
    return "+".join(wanted) or "eng"


def ocr_image(image: Any, *, languages: str = "eng", page_number: int = 1) -> OcrPage:
    import pytesseract
    from pytesseract import Output

    lang = resolve_languages(languages)
    width, height = image.size
    data = pytesseract.image_to_data(image, lang=lang, output_type=Output.DICT, config="--psm 3")
    confidences: list[float] = []
    paragraphs: dict[tuple[int, int], dict[str, Any]] = {}
    lines: dict[tuple[int, int, int], list[str]] = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        confidences.append(conf / 100.0)
        para_key = (data["block_num"][i], data["par_num"][i])
        line_key = (*para_key, data["line_num"][i])
        lines.setdefault(line_key, []).append(word)
        x0, y0 = data["left"][i], data["top"][i]
        x1, y1 = x0 + data["width"][i], y0 + data["height"][i]
        para = paragraphs.setdefault(para_key, {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "lines": []})
        para["x0"], para["y0"] = min(para["x0"], x0), min(para["y0"], y0)
        para["x1"], para["y1"] = max(para["x1"], x1), max(para["y1"], y1)
        if line_key not in para["lines"]:
            para["lines"].append(line_key)

    text_parts: list[str] = []
    blocks: list[Block] = []
    offset = 0
    for para in paragraphs.values():
        para_text = "\n".join(" ".join(lines[key]) for key in para["lines"])
        text_parts.append(para_text)
        start = offset
        offset += len(para_text) + 2  # paragraphs are joined with a blank line below
        blocks.append(
            Block(
                "paragraph",
                para_text,
                page=page_number,
                char_start=start,  # offsets within this page's OCR text
                char_end=start + len(para_text),
                bbox={
                    "page": page_number,
                    "x0": round(para["x0"] / width, 4),
                    "y0": round(para["y0"] / height, 4),
                    "x1": round(para["x1"] / width, 4),
                    "y1": round(para["y1"] / height, 4),
                },
            )
        )
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrPage(text="\n\n".join(text_parts), mean_confidence=round(mean, 4), blocks=blocks, language=lang)


def render_pdf_page(path: Path, page_index: int, dpi: int = 300) -> Any:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[page_index]
        bitmap = page.render(scale=dpi / 72)
        image = bitmap.to_pil().convert("L")
    finally:
        pdf.close()
    return image


def ocr_pdf_page(path: Path, page_index: int, *, languages: str, dpi: int) -> OcrPage:
    image = render_pdf_page(path, page_index, dpi)
    return ocr_image(image, languages=languages, page_number=page_index + 1)
