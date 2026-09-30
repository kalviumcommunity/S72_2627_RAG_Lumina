from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, Timestamps, UUIDPrimaryKey
from app.models.branch import Branch
from app.models.department import Department
from app.models.enums import Role


class User(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=20, name="role"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    department_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("departments.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    branch: Mapped[Branch | None] = relationship(lazy="joined")
    department: Mapped[Department | None] = relationship(lazy="joined")
