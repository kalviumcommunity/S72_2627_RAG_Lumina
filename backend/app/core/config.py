"""Application settings. Every tunable comes from the environment (see .env.example)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["gemini", "anthropic", "ollama", "none"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App -----------------------------------------------------------------------------------
    app_env: Literal["dev", "test", "prod"] = "dev"
    api_base_url: str = "http://localhost:8000"
    web_base_url: str = "http://localhost:5173"
    extra_cors_origins: str = ""  # comma separated
    secret_key: str = "change-me"  # noqa: S105  (rejected at startup when APP_ENV=prod)
    dev_auth: bool = True
    session_idle_minutes: int = Field(default=15, ge=1, le=24 * 60)

    # --- Database / cache ----------------------------------------------------------------------
    database_url: str = "postgresql+asyncpg://protocite:protocite@localhost:5432/protocite"
    redis_url: str = "redis://localhost:6379/0"
    storage_dir: Path = Path("./data/storage")
    ingest_inline: bool = False  # run ingestion in-process instead of via the arq worker
    # Built web app (frontend/dist). When the folder exists the API also serves the UI on the same
    # origin, so one process is enough for a demo; in development Vite serves it instead.
    web_dist_dir: Path = Path(__file__).resolve().parents[3] / "frontend" / "dist"

    # --- OIDC (production) ---------------------------------------------------------------------
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""

    # --- Models --------------------------------------------------------------------------------
    llm_provider: LLMProviderName = "gemini"
    gemini_api_key: str = ""
    # Comma-separated fallback chains: if a model is rate-limited the next one is used.
    gemini_model: str = "gemini-3.6-flash,gemini-3.5-flash"  # writes the answers
    gemini_fast_model: str = "gemini-3.5-flash-lite,gemini-3.1-flash-lite"  # routing + verification
    gemini_thinking_level: Literal["", "minimal", "low", "medium", "high"] = "minimal"
    # Vertex AI mode (data residency): pins inference to a Google Cloud region, e.g. asia-south1.
    gemini_use_vertex: bool = False
    google_cloud_project: str = ""
    google_cloud_location: str = "asia-south1"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: Literal["low", "medium", "high"] = "low"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_num_ctx: int = 8192
    llm_timeout_seconds: float = 90.0
    llm_max_concurrency: int = 4
    # Per-stage budgets (seconds); past them the stage uses its deterministic fallback. 0 = no limit.
    llm_budget_classify_s: float = 6.0
    llm_budget_generate_s: float = 15.0
    llm_budget_verify_s: float = 10.0
    llm_budget_conflict_s: float = 10.0

    embedding_provider: Literal["sentence-transformers", "hash"] = "sentence-transformers"
    embedding_model: str = "intfloat/multilingual-e5-base"
    embedding_dim: int = 768
    embedding_batch_size: int = 16
    reranker_provider: Literal["cross-encoder", "lexical"] = "cross-encoder"
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_max_length: int = 256
    rerank_candidates: int = 8
    model_device: Literal["auto", "cpu", "cuda"] = "auto"  # auto = CUDA when available
    nli_enabled: bool = False
    nli_model: str = "cross-encoder/nli-deberta-v3-base"
    warmup_models: bool = True
    # Use only locally cached Hugging Face models (no network at startup — safer for demos).
    hf_hub_offline: bool = False
    docling_enabled: bool = False

    # --- Retrieval / safety thresholds ---------------------------------------------------------
    k_context: int = 6
    retrieval_top_k: int = 40
    rerank_top_n: int = 12
    rrf_k: int = 60
    min_relevance: float = 0.35
    verifier_threshold: float = 0.8
    # batch: one LLM call judges every claim (same per-claim rubric); per_claim: one call per claim/passage.
    verifier_mode: Literal["batch", "per_claim"] = "batch"
    ocr_min_confidence: float = 0.80
    ocr_languages: str = "eng+hin"
    ocr_dpi: int = 300
    tesseract_cmd: str = ""  # path to the tesseract binary if it is not on PATH
    tessdata_prefix: str = ""  # directory holding *.traineddata if tesseract cannot find it
    authority_branch_boost: float = 0.10
    authority_circular_boost: float = 0.05
    authority_recency_boost: float = 0.02
    conflict_min_confidence: float = 0.7
    pii_redaction_engine: Literal["presidio", "regex"] = "presidio"

    # --- Limits / retention --------------------------------------------------------------------
    query_rate_limit_per_minute: int = 30
    max_question_chars: int = 1000
    max_upload_mb: int = 25
    log_retention_days: int = 180

    # --- Observability -------------------------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True
    otel_exporter_otlp_endpoint: str = ""

    # Pin "today" for demos and tests; effective-version logic always goes through settings.today().
    today_override: date | None = None

    @field_validator("today_override", mode="before")
    @classmethod
    def _empty_date_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @model_validator(mode="after")
    def _refuse_unsafe_production(self) -> Settings:
        """APP_ENV=prod must not start with the demo secret or the password-less demo sign-in."""
        if self.app_env != "prod":
            return self
        problems = []
        if self.secret_key == "change-me" or len(self.secret_key) < 32:  # noqa: S105
            problems.append("SECRET_KEY must be a random string of at least 32 characters")
        if self.dev_auth:
            problems.append("DEV_AUTH must be false (demo sign-in lets anyone act as any user)")
        if problems:
            raise ValueError("Unsafe production settings: " + "; ".join(problems))
        return self

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def cors_origins(self) -> list[str]:
        origins = [self.web_base_url]
        origins += [o.strip() for o in self.extra_cors_origins.split(",") if o.strip()]
        return origins

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id)

    def today(self) -> date:
        return self.today_override or datetime.now(UTC).date()


@lru_cache
def get_settings() -> Settings:
    return Settings()
