"""Process-wide service container (models are loaded once). Tests swap in fakes via set_services()."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.embeddings import EmbeddingProvider, build_embedder
from app.services.generation.prompts import PromptSet, load_prompts
from app.services.generation.verifier import CrossEncoderNLI, NLIChecker
from app.services.llm import LLMProvider, build_llm
from app.services.retrieval.authority import BoostConfig
from app.services.retrieval.reranker import CrossEncoderReranker, LexicalReranker, Reranker
from app.services.retrieval.search import SearchConfig
from app.services.safety import pii_redaction
from app.services.safety.pii_redaction import PIIRedactor

log = get_logger(__name__)


@dataclass
class Services:
    settings: Settings
    llm: LLMProvider | None
    embedder: EmbeddingProvider
    reranker: Reranker
    redactor: PIIRedactor
    prompts: PromptSet
    nli: NLIChecker | None = None

    @property
    def search_config(self) -> SearchConfig:
        s = self.settings
        return SearchConfig(
            top_k=s.retrieval_top_k,
            rrf_k=s.rrf_k,
            rerank_candidates=s.rerank_candidates,
            rerank_top_n=s.rerank_top_n,
            k_context=s.k_context,
            boosts=BoostConfig(
                branch=s.authority_branch_boost,
                circular=s.authority_circular_boost,
                recency=s.authority_recency_boost,
            ),
        )

    @property
    def model_id(self) -> str:
        llm = f"{self.llm.name}:{self.llm.model_id}" if self.llm else "none"
        return f"{llm}|emb:{self.embedder.model_id}|rr:{self.reranker.model_id}"

    def warmup(self) -> None:
        start = time.perf_counter()
        for component in (self.embedder, self.reranker, self.redactor):
            fn = getattr(component, "warmup", None)
            if callable(fn):
                fn()
        log.info("models_warmed", seconds=round(time.perf_counter() - start, 1))


def configure_model_runtime(settings: Settings) -> None:
    """Environment for transformers / huggingface_hub; must run before either is imported."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    if settings.hf_hub_offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"


def build_services(settings: Settings | None = None) -> Services:
    s = settings or get_settings()
    configure_model_runtime(s)
    reranker: Reranker = (
        LexicalReranker()
        if s.reranker_provider == "lexical"
        else CrossEncoderReranker(s.reranker_model, s.reranker_max_length, s.model_device)
    )
    return Services(
        settings=s,
        llm=build_llm(s),
        embedder=build_embedder(s),
        reranker=reranker,
        redactor=PIIRedactor(s.pii_redaction_engine),
        prompts=load_prompts(),
        nli=CrossEncoderNLI(s.nli_model) if s.nli_enabled else None,
    )


_services: Services | None = None


def get_services() -> Services:
    global _services
    if _services is None:
        _services = build_services()
    return _services


def set_services(services: Services | None) -> None:
    global _services
    _services = services


async def load_corpus_vocabulary(session: AsyncSession) -> int:
    """Teach the redactor every word used in documents, branches and departments (never a name),
    and refresh the corpus term statistics used for key-term matching."""
    from app.models import Branch, Chunk, Department, Document
    from app.services.retrieval.terms import term_stats

    words: set[str] = set()
    for column in (Document.title, Branch.name, Department.name):
        for (value,) in await session.execute(select(column)):
            words.update(re.findall(r"[A-Za-z][A-Za-z-]{1,}", value or ""))
    passages: list[str] = []
    for heading, text in await session.execute(select(Chunk.heading, Chunk.text)):
        passages.append(f"{heading}\n{text}")
        words.update(re.findall(r"[A-Za-z][A-Za-z-]{1,}", f"{heading} {text}"))
    pii_redaction.add_vocabulary(words)
    term_stats.fit(passages)
    return len(words)
