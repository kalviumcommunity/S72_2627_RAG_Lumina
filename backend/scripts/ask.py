"""Ask ProtoCite from the command line (same pipeline as the API; answers are logged and audited).

Usage (from backend/):
    python -m scripts.ask "What is the heparin nomogram step for aPTT above 100?"
    python -m scripts.ask --user arjun.iyer@dhn.example "Who do I call to activate the MTP?"
    python -m scripts.ask --file questions.txt --debug
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy import select

from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_sessionmaker, init_engine
from app.models import User
from app.schemas.query import QueryResponse
from app.services.orchestrator import Orchestrator
from app.services.registry import get_services, load_corpus_vocabulary


def render(q: str, r: QueryResponse, branch: str, debug: bool) -> str:
    out = [
        f"\n### [{branch}] {q}",
        f"  route={r.route.value} outcome={r.outcome.value} mode={r.generation_mode} latency={r.latency_ms}ms",
    ]
    if r.pii_redacted:
        out.append(f"  redacted: {r.redacted_question}")
    if r.answer:
        out += ["  " + line for line in r.answer.splitlines()]
    for c in r.citations:
        amends = (
            f" (amends {', '.join(a.doc_code + (' §' + a.section_path if a.section_path else '') for a in c.amends)})"
            if c.amends
            else ""
        )
        out.append(
            f"   [{c.marker}] {c.doc_code} v{c.version} §{c.section_path} — {c.heading} · effective {c.effective_from}{amends}"
        )
    for qv in r.quick_values:
        out.append(f"   • {qv.label}: {qv.value} [{qv.source}]")
    for cf in r.conflicts:
        out.append(
            f"   ⚠ conflict: {cf.a.doc_code} §{cf.a.section_path} vs {cf.b.doc_code} §{cf.b.section_path} (newer: {cf.newer})"
        )
    if r.escalation:
        out.append(f"  ESCALATE ({r.escalation.reason}): {r.escalation.message}")
        out += [f"   ☎ {c.role_label} ext {c.phone_ext or '-'}" for c in r.escalation.contacts]
        if r.escalation.clarifying_question:
            out.append(f"  ? {r.escalation.clarifying_question}")
    if debug:
        out.append("  sources: " + ", ".join(f"{s.doc_code} §{s.section_path} ({s.relevance:.2f})" for s in r.sources))
        if r.verification:
            out.append(
                f"  verification: {r.verification.supported}/{r.verification.claims} claims supported ({r.verification.judge})"
            )
    return "\n".join(out)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question", nargs="*")
    parser.add_argument("--user", default="kavya.rao@dhn.example")
    parser.add_argument("--file", type=Path, help="one question per line")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    questions = [" ".join(args.question)] if args.question else []
    if args.file:
        questions += [line.strip() for line in args.file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not questions:
        parser.error("give a question or --file")
    configure_logging("WARNING", json_logs=False)
    init_engine()
    services = get_services()
    try:
        async with get_sessionmaker()() as session:
            await load_corpus_vocabulary(session)
            user = (await session.execute(select(User).where(User.email == args.user))).scalar_one_or_none()
            if user is None:
                sys.exit(f"Unknown user {args.user}")
        services.warmup()
        for question in questions:
            async with get_sessionmaker()() as session:
                result = await Orchestrator(services).answer(session, question, user, None)
            print(render(question, result, user.branch.code if user.branch else "-", args.debug), flush=True)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
