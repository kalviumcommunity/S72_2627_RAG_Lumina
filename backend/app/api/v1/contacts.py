from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.models.contact import Contact
from app.schemas.admin import ContactAdminOut

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactAdminOut])
async def list_contacts(user: CurrentUser, session: DbSession, branch_id: uuid.UUID | None = None) -> list[Contact]:
    branch = branch_id or user.branch_id
    stmt = select(Contact).order_by(Contact.priority, Contact.role_label)
    if branch is not None:
        stmt = stmt.where(or_(Contact.branch_id.is_(None), Contact.branch_id == branch))
    return list((await session.execute(stmt)).scalars())
