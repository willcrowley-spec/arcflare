"""Discovery run tracking and process handoff models."""
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.process import BusinessProcess


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="running")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pass_results: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_by: Mapped[str] = mapped_column(String(100), nullable=False, server_default="system")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_scores: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    stage_results: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    organization: Mapped["Organization"] = relationship("Organization")


class ProcessHandoff(Base):
    __tablename__ = "process_handoffs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    handoff_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="unknown")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, server_default="0.0")
    is_gap: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    needs_review: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    discovery_run_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("discovery_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    gap_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="open")
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    evidence_sources: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    source_process: Mapped["BusinessProcess"] = relationship(
        "BusinessProcess", foreign_keys=[source_process_id]
    )
    target_process: Mapped["BusinessProcess"] = relationship(
        "BusinessProcess", foreign_keys=[target_process_id]
    )
