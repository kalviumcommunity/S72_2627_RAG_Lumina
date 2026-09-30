"""First-run setup, safe to repeat: migrate, seed reference data, load the sample corpus if empty.

Usage (from backend/):  python -m scripts.bootstrap [--skip-corpus]
Used by protocite.ps1 start and the Docker api entrypoint.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select

from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.models import Document
from scripts.ingest_sample import DEFAULT_CORPUS, load_corpus
from scripts.seed import seed


def migrate() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


async def run(skip_corpus: bool) -> None:
    init_engine()
    try:
        counts = await seed()
        print("Reference data:", ", ".join(f"{k}+{v}" for k, v in counts.items()))
        async with get_sessionmaker()() as session:
            documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        if documents or skip_corpus:
            print(f"Corpus: {documents} document(s) already loaded")
            return
        print("Corpus: empty, loading the SYNTHETIC sample corpus (first run takes a minute)...")
        summary = await load_corpus(DEFAULT_CORPUS, detect_conflicts=True)
        print("Corpus:", {k: v for k, v in summary.items() if v})
    finally:
        await dispose_engine()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-corpus", action="store_true", help="do not load the sample corpus")
    args = parser.parse_args()
    configure_logging("WARNING", json_logs=False)
    migrate()
    print("Database: schema up to date")
    asyncio.run(run(args.skip_corpus))


if __name__ == "__main__":
    main()
