"""Audit chain verification CLI script.

Usage:
    python -m scripts.verify_audit
"""

from __future__ import annotations

import asyncio
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, init_engine, session_scope
from app.services.audit import verify_chain


async def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    init_engine()
    try:
        async with session_scope() as session:
            result = await verify_chain(session)
            if result.ok:
                print(f"[OK] Audit chain valid. {result.events_checked} events verified with cryptographic hash-chaining.")
                return 0
            else:
                print(f"[FAIL] Audit chain compromised at sequence {result.first_bad_seq}! Reason: {result.reason}")
                return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
