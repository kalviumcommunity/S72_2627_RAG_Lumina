"""Re-compute the audit hash chain and report the first broken link (exit code 1 if broken).

Usage (from backend/):  python -m scripts.audit_verify
"""

from __future__ import annotations

import asyncio
import sys

from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.services import audit


async def main() -> int:
    configure_logging("WARNING", json_logs=False)
    init_engine()
    try:
        async with get_sessionmaker()() as session:
            result = await audit.verify_chain(session)
    finally:
        await dispose_engine()
    if result.ok:
        print(f"Audit chain intact: {result.events_checked} events verified.")
        return 0
    print(f"Audit chain BROKEN at seq {result.first_bad_seq}: {result.reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
