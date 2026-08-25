"""ORM models — PVReport, CallLog.

Phase 1: Defined but migrations not run yet.
Use `python scripts/migrate.py` to create tables once PostgreSQL is up.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[str] = mapped_column(String(255), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    left_participant: Mapped[dict | None] = mapped_column(JSONB)
    right_participant: Mapped[dict | None] = mapped_column(JSONB)
    call_type: Mapped[str | None] = mapped_column(String(50))

    pv_report: Mapped["PVReport | None"] = relationship(
        back_populates="call_log", uselist=False
    )


class PVReport(Base):
    __tablename__ = "pv_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("call_logs.id")
    )
    subject: Mapped[str | None] = mapped_column(Text)
    compte_rendu: Mapped[str | None] = mapped_column(Text)
    actions: Mapped[dict | None] = mapped_column(JSONB)
    raw_transcript: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    routed_to: Mapped[str | None] = mapped_column(String(50))

    call_log: Mapped["CallLog | None"] = relationship(back_populates="pv_report")
