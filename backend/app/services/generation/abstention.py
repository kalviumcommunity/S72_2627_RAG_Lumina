"""Abstention responses (not found / high risk / out of scope / clarify) with escalation contacts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact

AbstainReason = Literal["not_found", "high_risk", "out_of_scope", "clarify", "unavailable"]

MESSAGES: dict[str, str] = {
    "not_found": (
        "No approved, current hospital document answers this question. Do not rely on memory for this — "
        "escalate to the contacts below."
    ),
    "high_risk": (
        "This asks for a patient-specific decision (diagnosis, individual dosing or whether to give or "
        "withhold treatment). ProtoCite only shows what approved documents say and cannot make this decision. "
        "Please discuss with a senior clinician or pharmacist."
    ),
    "out_of_scope": (
        "ProtoCite only answers questions about the network's approved protocols, drug guidelines and circulars."
    ),
    "clarify": "A little more detail is needed to find the right document.",
    "unavailable": (
        "The answer service could not complete safely. No unverified text has been shown. "
        "Please retry or escalate to the contacts below."
    ),
}


@dataclass
class Escalation:
    reason: AbstainReason
    message: str
    contacts: list[dict[str, Any]] = field(default_factory=list)
    clarifying_question: str | None = None


def contact_to_dict(contact: Contact) -> dict[str, Any]:
    return {
        "id": str(contact.id),
        "role_label": contact.role_label,
        "phone_ext": contact.phone_ext,
        "phone": contact.phone,
        "pager": contact.pager,
        "notes": contact.notes,
        "branch_id": str(contact.branch_id) if contact.branch_id else None,
    }


async def contacts_for(
    session: AsyncSession,
    branch_id: uuid.UUID | None,
    reason: str,
    department_ids: list[uuid.UUID] | None = None,
    limit: int = 4,
) -> list[dict[str, Any]]:
    stmt = select(Contact).where(or_(Contact.branch_id.is_(None), Contact.branch_id == branch_id))
    contacts = list((await session.execute(stmt)).scalars())
    dept = set(department_ids or [])

    def rank(c: Contact) -> tuple[int, int, int, int]:
        relevant = 0 if (not c.escalation_for or reason in c.escalation_for) else 1
        local = 0 if c.branch_id is not None else 1
        in_dept = 0 if c.department_id in dept else 1
        return (relevant, in_dept, local, c.priority)

    def offered(c: Contact) -> bool:
        if c.escalation_for and reason not in c.escalation_for:
            return False
        # Service-specific contacts (e.g. the blood bank) only when the question touched that service.
        return c.department_id is None or c.department_id in dept or reason == "high_risk"

    chosen = [c for c in sorted(contacts, key=rank) if offered(c)]
    return [contact_to_dict(c) for c in chosen[:limit]]


async def build(
    session: AsyncSession,
    reason: AbstainReason,
    branch_id: uuid.UUID | None,
    *,
    clarifying_question: str | None = None,
    department_ids: list[uuid.UUID] | None = None,
) -> Escalation:
    contacts = (
        [] if reason in ("out_of_scope", "clarify") else await contacts_for(session, branch_id, reason, department_ids)
    )
    return Escalation(reason, MESSAGES[reason], contacts, clarifying_question)
