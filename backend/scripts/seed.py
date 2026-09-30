"""Seed branches, departments, demo users and the escalation directory (idempotent).

Usage (from backend/):  python -m scripts.seed
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, init_engine, session_scope
from app.models import Branch, Contact, Department, User
from app.models.enums import Role
from app.services import audit

DATA = Path(__file__).with_name("seed_data.yaml")


async def seed(data: dict[str, Any] | None = None) -> dict[str, int]:
    data = data or yaml.safe_load(DATA.read_text(encoding="utf-8"))
    counts = {"branches": 0, "departments": 0, "users": 0, "contacts": 0}
    async with session_scope() as session:
        branches: dict[str, Branch] = {b.code: b for b in (await session.execute(select(Branch))).scalars()}
        for item in data["branches"]:
            if item["code"] not in branches:
                branches[item["code"]] = Branch(code=item["code"], name=item["name"])
                session.add(branches[item["code"]])
                counts["branches"] += 1
        departments: dict[str, Department] = {d.code: d for d in (await session.execute(select(Department))).scalars()}
        for item in data["departments"]:
            if item["code"] not in departments:
                departments[item["code"]] = Department(code=item["code"], name=item["name"])
                session.add(departments[item["code"]])
                counts["departments"] += 1
        await session.flush()

        existing_users = {u.email for u in (await session.execute(select(User))).scalars()}
        for item in data["users"]:
            if item["email"] in existing_users:
                continue
            session.add(
                User(
                    email=item["email"],
                    display_name=item["name"],
                    role=Role(item["role"]),
                    branch_id=branches[item["branch"]].id if item.get("branch") else None,
                    department_id=departments[item["department"]].id if item.get("department") else None,
                    is_active=True,
                )
            )
            counts["users"] += 1

        existing_contacts = {(c.role_label, c.branch_id) for c in (await session.execute(select(Contact))).scalars()}
        for item in data["contacts"]:
            branch_id = branches[item["branch"]].id if item.get("branch") else None
            if (item["role_label"], branch_id) in existing_contacts:
                continue
            session.add(
                Contact(
                    role_label=item["role_label"],
                    branch_id=branch_id,
                    department_id=departments[item["department"]].id if item.get("department") else None,
                    phone_ext=item.get("phone_ext"),
                    phone=item.get("phone"),
                    pager=item.get("pager"),
                    notes=item.get("notes"),
                    escalation_for=list(item.get("escalation_for") or []),
                    priority=int(item.get("priority", 100)),
                )
            )
            counts["contacts"] += 1
        if any(counts.values()):
            await audit.record(session, action="seed.loaded", entity_type="system", payload=counts)
    return counts


async def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=False)
    init_engine()
    try:
        counts = await seed()
        print("Seeded:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
