"""Write-only, hash-chained audit log.

hash_n = sha256(hash_{n-1} + canonical_json(record_n)), where record_n covers every stored column
except seq/hash. Writers serialise on a transaction-scoped advisory lock so the chain never forks.
UPDATE/DELETE/TRUNCATE on audit_events are rejected by database triggers.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditEvent

GENESIS_HASH = "0" * 64
_AUDIT_LOCK_KEY = 7_345_001


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def event_record(
    *,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload,
        "created_at": created_at.astimezone(UTC).isoformat(timespec="microseconds"),
    }


def compute_hash(prev_hash: str, record: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(record)).encode("utf-8")).hexdigest()


async def record(
    session: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an event in the caller's transaction (committed together with the change it records)."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _AUDIT_LOCK_KEY})
    last = (
        await session.execute(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1))
    ).scalar_one_or_none()
    prev_hash = last or GENESIS_HASH
    created_at = datetime.now(UTC)  # timestamptz keeps microseconds, so the hash round-trips
    clean_payload = json.loads(canonical_json(payload or {}))
    entity = str(entity_id) if entity_id is not None else None
    rec = event_record(
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity,
        payload=clean_payload,
        created_at=created_at,
    )
    event = AuditEvent(
        created_at=created_at,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity,
        payload=clean_payload,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, rec),
    )
    session.add(event)
    await session.flush()
    return event


@dataclass
class ChainVerification:
    ok: bool
    events_checked: int
    first_bad_seq: int | None = None
    reason: str | None = None


def verify_events(events: list[AuditEvent]) -> ChainVerification:
    prev = GENESIS_HASH
    for index, event in enumerate(events):
        rec = event_record(
            actor_user_id=event.actor_user_id,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            payload=event.payload,
            created_at=event.created_at,
        )
        if event.prev_hash != prev:
            return ChainVerification(False, index, event.seq, "prev_hash does not match the previous event")
        if compute_hash(prev, rec) != event.hash:
            return ChainVerification(False, index, event.seq, "hash does not match the event contents")
        prev = event.hash
    return ChainVerification(True, len(events))


async def verify_chain(session: AsyncSession) -> ChainVerification:
    events = list((await session.execute(select(AuditEvent).order_by(AuditEvent.seq))).scalars())
    return verify_events(events)
