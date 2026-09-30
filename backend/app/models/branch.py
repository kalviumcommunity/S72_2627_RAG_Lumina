from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class Branch(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "branches"

    name: Mapped[str] = mapped_column(String(200))
    code: Mapped[str] = mapped_column(String(20), unique=True)
