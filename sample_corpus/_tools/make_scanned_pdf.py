"""Generate the scanned-style sample circular (image-only PDF, no text layer).

SYNTHETIC — FOR DEMO ONLY. Run from the repo root:
    python sample_corpus/_tools/make_scanned_pdf.py
The output is committed, so this only needs re-running if the text below changes.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parents[1] / "circulars" / "C-2026-11_sepsis_timing_update_scan.pdf"
DPI = 200
WIDTH, HEIGHT = int(8.27 * DPI), int(11.69 * DPI)  # A4
MARGIN = int(0.9 * DPI)

LINES: list[tuple[str, str]] = [
    ("title", "DEMO HEALTH NETWORK"),
    ("title", "CIRCULAR C-2026-11"),
    ("small", "SYNTHETIC - FOR DEMO ONLY. Fictional circular for the ProtoCite demo corpus."),
    ("small", "Not clinical guidance. Do not use for patient care."),
    ("gap", ""),
    ("body", "Subject: Sepsis antibiotic timing - risk-stratified targets"),
    ("body", "Circular number: C-2026-11      Version: 1"),
    ("body", "Date of issue: 2026-09-08      Effective from: 2026-09-15"),
    ("body", "Amends: P-ED-01 section 5.3"),
    ("gap", ""),
    ("heading", "1 BACKGROUND"),
    ("body", "A network audit of 1,240 adult sepsis presentations found that giving antibiotics"),
    ("body", "within one hour to every patient with possible sepsis led to unnecessary broad-"),
    ("body", "spectrum antibiotic use in patients later found not to have an infection. The"),
    ("body", "Sepsis Working Group has approved risk-stratified antibiotic timing targets."),
    ("gap", ""),
    ("heading", "2 AMENDMENT"),
    ("body", "Section 5.3 of P-ED-01 (Sepsis Recognition and One-Hour Bundle, version 2) is"),
    ("body", "replaced with effect from 15 September 2026 by the following:"),
    ("body", "(a) Probable sepsis or septic shock: give broad-spectrum intravenous antibiotics"),
    ("body", "within 1 hour of recognition."),
    ("body", "(b) Possible sepsis without shock: complete a senior clinical assessment and give"),
    ("body", "antibiotics within 3 hours of recognition if infection remains the likely cause."),
    ("body", "(c) Record the time of the first antibiotic dose on the sepsis screening form."),
    ("gap", ""),
    ("heading", "3 CONTACT"),
    ("body", "Emergency Department clinical lead, extension 3105."),
    ("gap", ""),
    ("body", "Signed: Chair, Sepsis Working Group (synthetic)"),
]

FONT_CANDIDATES = [
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
BOLD_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]


def _font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    sys.exit("No TrueType font found; install DejaVu or Liberation fonts")


def render() -> Image.Image:
    rng = random.Random(2026_11)
    page = Image.new("L", (WIDTH, HEIGHT), color=246)
    draw = ImageDraw.Draw(page)
    fonts = {
        "title": _font(BOLD_CANDIDATES, 44),
        "heading": _font(BOLD_CANDIDATES, 34),
        "body": _font(FONT_CANDIDATES, 31),
        "small": _font(FONT_CANDIDATES, 25),
    }
    y = MARGIN
    for kind, text in LINES:
        if kind == "gap":
            y += 22
            continue
        font = fonts[kind]
        x = MARGIN if kind != "title" else (WIDTH - draw.textlength(text, font=font)) // 2
        draw.text((x, y), text, fill=28, font=font)
        y += int(font.size * 1.55)
    # Scanner artefacts: faint speckle, slight skew and blur.
    pixels = page.load()
    for _ in range(9000):
        px, py = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        pixels[px, py] = rng.choice((180, 200, 215))
    page = page.rotate(0.35, resample=Image.BICUBIC, fillcolor=246, expand=False)
    return page.filter(ImageFilter.GaussianBlur(radius=0.6))


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    render().save(OUT, "PDF", resolution=float(DPI))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
