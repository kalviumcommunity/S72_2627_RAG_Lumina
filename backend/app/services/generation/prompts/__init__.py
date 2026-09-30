"""Prompt loading. Each prompt's version is the first 8 hex chars of its SHA-256 (logged per query)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str

    @property
    def version(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class PromptSet:
    classifier: Prompt
    generator: Prompt
    verifier: Prompt

    @property
    def version(self) -> str:
        return ",".join(f"{p.name}@{p.version}" for p in (self.classifier, self.generator, self.verifier))


@lru_cache
def load_prompts() -> PromptSet:
    def read(name: str) -> Prompt:
        return Prompt(name, (_DIR / f"{name}.md").read_text(encoding="utf-8").strip())

    return PromptSet(classifier=read("classifier"), generator=read("generator"), verifier=read("verifier"))
