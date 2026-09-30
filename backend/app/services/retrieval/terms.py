"""Corpus term statistics: which query words are *specific* (rare in the corpus, e.g. a drug name).

Specific ("key") terms drive two safeguards:
* retrieval: passages containing a key term are guaranteed a place in the re-ranking pool and get a
  small boost, so "Does Tazocin need approval?" reaches the table that actually lists the drug;
* extractive answers: a quoted sentence must contain a key term, otherwise the system abstains
  rather than quoting a generic sentence that merely sounds relevant.
"""

from __future__ import annotations

import math
import threading
from collections import Counter
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from app.services.textutil import stemmed_words

_LEXICON = Path(__file__).with_name("entity_lexicon.txt")


@lru_cache
def entity_lexicon() -> frozenset[str]:
    terms: set[str] = set()
    for line in _LEXICON.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            terms |= stemmed_words(line)
    return frozenset(terms)


class TermStats:
    def __init__(self) -> None:
        self._df: Counter[str] = Counter()
        self._n = 0
        self._lock = threading.Lock()

    @property
    def documents(self) -> int:
        return self._n

    def fit(self, texts: Iterable[str]) -> None:
        df: Counter[str] = Counter()
        n = 0
        for text in texts:
            df.update(stemmed_words(text))
            n += 1
        with self._lock:
            self._df, self._n = df, n

    def add(self, texts: Iterable[str]) -> None:
        with self._lock:
            for text in texts:
                self._df.update(stemmed_words(text))
                self._n += 1

    def df(self, term: str) -> int:
        return self._df.get(term, 0)

    def idf(self, term: str) -> float:
        return math.log((self._n + 1) / (self.df(term) + 1)) + 1.0

    def key_terms(self, query: str, *, max_ratio: float = 0.12, min_df_cap: int = 3) -> set[str]:
        """The specific things a question is about.

        Named entities (medicines, components, tests) found in the corpus take priority; without
        one, fall back to query words that are rare in the corpus.
        """
        if self._n == 0:
            return set()
        words = stemmed_words(query)
        entities = {w for w in words & entity_lexicon() if self.df(w) > 0}
        if entities:
            return entities
        cap = max(min_df_cap, int(self._n * max_ratio))
        return {w for w in words if 0 < self.df(w) <= cap and not w.isdigit()}

    def uncovered_entities(self, question: str, expansions: Iterable[tuple[str, str]] = ()) -> set[str]:
        """Named entities in the question that no indexed document mentions (e.g. "dengue").

        An entity is covered when an approved abbreviation/brand expansion of it appears in the
        corpus ("Tazocin" → piperacillin-tazobactam). Uncovered entities mean the documents cannot
        answer the question, however similar the retrieved text sounds.
        """
        if self._n == 0:
            return set()
        missing = {w for w in stemmed_words(question) & entity_lexicon() if self.df(w) == 0}
        for term, meaning in expansions:
            if missing & stemmed_words(term) and any(self.df(m) > 0 for m in stemmed_words(meaning)):
                missing -= stemmed_words(term)
        return missing


term_stats = TermStats()
