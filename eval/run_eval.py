"""Run the ProtoCite evaluation set through the real pipeline and gate on thresholds.

Usage (from the repository root, with the backend virtualenv):
    backend\\.venv\\Scripts\\python -m eval.run_eval                  # LLM mode (LLM_PROVIDER from .env)
    backend\\.venv\\Scripts\\python -m eval.run_eval --mode extractive  # no LLM: deterministic, free
    backend\\.venv\\Scripts\\python -m eval.run_eval --only hep-06,mtp-02 --no-gate

It uses a separate database (protocite_eval) and storage folder, loads the synthetic sample corpus
into it when it is empty (or with --fresh), pins "today" (--today) so effective dates are
reproducible, and writes a Markdown + JSON report to eval/reports/. Exit code 1 if a threshold
fails (unless --no-gate).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
DATASET = ROOT / "eval" / "datasets" / "sample_questions.jsonl"
REPORTS = ROOT / "eval" / "reports"

from eval.metrics import ChunkRef, ItemResult, aggregate, gate, score_item  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", choices=["llm", "extractive"], default="llm")
    p.add_argument("--dataset", type=Path, default=DATASET)
    p.add_argument("--only", default="", help="comma-separated item ids or categories")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--database", default="protocite_eval", help="database name for the evaluation copy")
    p.add_argument("--fresh", action="store_true", help="rebuild the evaluation database from the sample corpus")
    p.add_argument("--today", default="2026-09-30", help="pinned 'today' for effective-date logic")
    p.add_argument("--delay", type=float, default=None, help="seconds between questions (default: 3 in llm mode)")
    p.add_argument("--no-gate", action="store_true", help="always exit 0")
    return p.parse_args()


def load_items(args: argparse.Namespace) -> list[dict[str, Any]]:
    items = [json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.only:
        wanted = {w.strip() for w in args.only.split(",") if w.strip()}
        items = [i for i in items if i["id"] in wanted or i["category"] in wanted]
    return items[: args.limit] if args.limit else items


def configure_environment(args: argparse.Namespace) -> str:
    """Point the backend at the evaluation database before any app module reads its settings."""
    os.chdir(BACKEND)  # Settings reads .env / ../.env relative to the working directory
    sys.path.insert(0, str(BACKEND))
    from app.core.config import Settings

    base = Settings().database_url
    parts = urlsplit(base)
    eval_url = urlunsplit(parts._replace(path=f"/{args.database}"))
    os.environ.update(
        {
            "DATABASE_URL": eval_url,
            "TODAY_OVERRIDE": args.today,
            "STORAGE_DIR": str(ROOT / ".runtime" / "eval-storage"),
            "INGEST_INLINE": "true",
            "LOG_LEVEL": "WARNING",
            "LOG_JSON": "false",
        }
    )
    if args.mode == "extractive":
        os.environ["LLM_PROVIDER"] = "none"
    return eval_url


async def ensure_database(url: str) -> bool:
    """Create the evaluation database (with pgvector) if it does not exist. Returns True if created."""
    import asyncpg

    plain = url.replace("postgresql+asyncpg://", "postgresql://")
    parts = urlsplit(plain)
    name = parts.path.lstrip("/")
    admin = await asyncpg.connect(urlunsplit(parts._replace(path="/postgres")))
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if not exists:
            await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()
    conn = await asyncpg.connect(plain)
    try:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    finally:
        await conn.close()
    return not exists


async def prepare_corpus(url: str, fresh: bool) -> None:
    from sqlalchemy import func, select

    from app.db.session import dispose_engine, get_sessionmaker, init_engine
    from app.models import Document
    from scripts.ingest_sample import DEFAULT_CORPUS, load_corpus
    from scripts.reset_db import reset
    from scripts.seed import seed

    documents = 0
    if not fresh:
        try:
            init_engine(url)
            async with get_sessionmaker()() as session:
                documents = (await session.execute(select(func.count()).select_from(Document))).scalar_one()
        except Exception:
            documents = 0
        finally:
            await dispose_engine()
    if documents and not fresh:
        print(f"Evaluation corpus ready ({documents} documents)")
        return
    print("Building the evaluation database from the SYNTHETIC sample corpus...")
    await asyncio.to_thread(reset, url, wipe_storage=False)
    init_engine(url)
    try:
        await seed()
        summary = await load_corpus(DEFAULT_CORPUS, detect_conflicts=True, verbose=False)
        print("Corpus:", {k: v for k, v in summary.items() if v})
    finally:
        await dispose_engine()


async def run(args: argparse.Namespace, items: list[dict[str, Any]], url: str) -> tuple[list[ItemResult], str]:
    from sqlalchemy import select, text

    from app.db.session import dispose_engine, get_sessionmaker, init_engine
    from app.models import AnswerLog, Chunk, Document, DocumentVersion, QueryLog, User
    from app.services.orchestrator import Orchestrator
    from app.services.registry import get_services, load_corpus_vocabulary
    from app.services.retrieval.eligibility import ELIGIBLE_CTE

    init_engine(url)
    services = get_services()
    await asyncio.to_thread(services.warmup)
    delay = args.delay if args.delay is not None else (3.0 if args.mode == "llm" and services.llm else 0.0)
    results: list[ItemResult] = []
    try:
        async with get_sessionmaker()() as session:
            await load_corpus_vocabulary(session)
            users = {u.email: u for u in (await session.execute(select(User))).scalars()}
            rows = await session.execute(
                select(Chunk.id, Document.doc_code, DocumentVersion.version_label, Chunk.section_path, Chunk.covered_paths)
                .join(DocumentVersion, DocumentVersion.id == Chunk.version_id)
                .join(Document, Document.id == DocumentVersion.document_id)
            )
            chunks = {
                str(r.id): ChunkRef(r.doc_code, r.version_label, r.section_path, tuple(r.covered_paths or ()))
                for r in rows
            }
            eligible: dict[Any, set[str]] = {}
            as_of = services.settings.today()
            for user in users.values():
                if user.branch_id not in eligible:
                    ids = await session.execute(
                        text(f"{ELIGIBLE_CTE} SELECT id FROM eligible"),  # noqa: S608  static CTE
                        {"as_of": as_of, "branch_id": user.branch_id},
                    )
                    eligible[user.branch_id] = {str(i) for (i,) in ids}

        for n, item in enumerate(items, 1):
            user = users[item["user"]]
            async with get_sessionmaker()() as session:
                response = await Orchestrator(services).answer(session, item["question"], user, None)
            stored = ""
            if item.get("pii"):
                async with get_sessionmaker()() as session:
                    log = await session.get(QueryLog, response.query_id)
                    answer_log = (
                        await session.execute(select(AnswerLog).where(AnswerLog.query_id == response.query_id))
                    ).scalar_one_or_none()
                    stored = " ".join(
                        [log.redacted_question if log else "", (answer_log.answer_text or "") if answer_log else ""]
                    )
            result = score_item(item, response, chunks, eligible[user.branch_id], stored)
            results.append(result)
            status = "PASS" if result.passed else "FAIL"
            print(
                f"[{n:>3}/{len(items)}] {status} {item['id']:<8} {result.route}/{result.outcome:<9} "
                f"{result.latency_ms:>6} ms {result.generation_mode or '-':<10} {'; '.join(result.notes)[:90]}",
                flush=True,
            )
            if delay and n < len(items):
                await asyncio.sleep(delay)
    finally:
        await dispose_engine()
    return results, services.model_id


def write_report(
    args: argparse.Namespace, results: list[ItemResult], summary: dict[str, Any], model_id: str, elapsed: float
) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    base = REPORTS / f"eval-{stamp}-{args.mode}"
    rows = gate(summary)
    passed = all(ok for *_, ok in rows)

    def fmt(value: Any) -> str:
        if value is None:
            return "n/a"
        if isinstance(value, float) and value <= 1 and not float(value).is_integer():
            return f"{value:.1%}"
        return str(value)

    lines = [
        f"# ProtoCite evaluation — {args.mode} mode",
        "",
        f"- Run: {datetime.now(UTC).isoformat(timespec='seconds')} · {elapsed:.0f} s · pinned today {args.today}",
        f"- Models: `{model_id}`",
        f"- Dataset: `{args.dataset.name}` · {summary['questions']} questions · {summary['passed']} fully passed",
        f"- Generation modes: {summary['generation_modes']}",
        f"- **Gate: {'PASS' if passed else 'FAIL'}**",
        "",
        "SYNTHETIC corpus — for demonstrating the method, not clinical validation.",
        "",
        "## Thresholds",
        "",
        "| Metric | Value | Threshold | Result |",
        "|---|---|---|---|",
    ]
    lines += [f"| {m} | {fmt(v)} | {op} {fmt(t)} | {'pass' if ok else '**FAIL**'} |" for m, v, op, t, ok in rows]
    lines += [
        "",
        "## Other measurements",
        "",
        f"- Mean reciprocal rank of the first gold clause: {fmt(summary['mrr'])}",
        f"- Verified claims / generated claims: {fmt(summary['claims_supported_ratio'])}",
        f"- Latency p50 / p95 (all): {summary['latency_p50_ms']} / {summary['latency_p95_ms']} ms",
        f"- Latency p50 / p95 (answered): {summary['answer_latency_p50_ms']} / {summary['answer_latency_p95_ms']} ms",
        "",
        "## By category",
        "",
        "| Category | Passed | Total |",
        "|---|---|---|",
    ]
    lines += [f"| {c} | {v['passed']} | {v['total']} |" for c, v in sorted(summary["by_category"].items())]
    failures = [r for r in results if not r.passed]
    lines += ["", f"## Items that did not pass every check ({len(failures)})", ""]
    for r in failures:
        failed = [k for k, ok in r.checks.items() if not ok]
        lines += [
            f"### {r.id} — {r.question}",
            f"- Expected **{r.expect}**, got route `{r.route}`, outcome `{r.outcome}`"
            + (f", reason `{r.reason}`" if r.reason else ""),
            f"- Failed checks: {', '.join(failed)}",
            f"- Cited: {', '.join(r.cited) or '—'} · Retrieved: {', '.join(r.sources[:6]) or '—'}",
        ]
        if r.notes:
            lines.append(f"- Notes: {'; '.join(r.notes)}")
        if r.answer:
            lines.append(f"- Answer: {' '.join(r.answer.split())[:400]}")
        lines.append("")
    base.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")
    payload = {
        "mode": args.mode,
        "model_id": model_id,
        "today": args.today,
        "summary": summary,
        "gate": [{"metric": m, "value": v, "op": op, "threshold": t, "pass": ok} for m, v, op, t, ok in rows],
        "items": [r.__dict__ | {"passed": r.passed} for r in results],
    }
    base.with_suffix(".json").write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    (REPORTS / f"latest-{args.mode}.md").write_text("\n".join(lines), encoding="utf-8")
    return base.with_suffix(".md")


def main() -> int:
    args = parse_args()
    items = load_items(args)
    if not items:
        sys.exit("No evaluation items selected")
    url = configure_environment(args)
    from app.core.logging import configure_logging

    configure_logging("WARNING", json_logs=False)
    started = time.perf_counter()

    async def pipeline() -> tuple[list[ItemResult], str]:
        # One event loop for everything: the LLM client must not outlive the loop it was made in.
        created = await ensure_database(url)
        await prepare_corpus(url, fresh=args.fresh or created)
        return await run(args, items, url)

    results, model_id = asyncio.run(pipeline())
    summary = aggregate(results)
    report = write_report(args, results, summary, model_id, time.perf_counter() - started)
    rows = gate(summary)
    print()
    for metric, value, op, threshold, ok in rows:
        print(f"  {'ok  ' if ok else 'FAIL'} {metric:<30} {value!s:<8} {op} {threshold}")
    passed = all(ok for *_, ok in rows)
    print(f"\n{summary['passed']}/{summary['questions']} items passed every check · gate {'PASS' if passed else 'FAIL'}")
    print(f"Report: {report}")
    return 0 if passed or args.no_gate else 1


if __name__ == "__main__":
    sys.exit(main())
