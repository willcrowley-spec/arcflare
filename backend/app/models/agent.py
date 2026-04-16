from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.recommendation import Recommendation


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    monthly_cap: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    total_spend: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, server_default="0")
    total_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="idle")
    accuracy: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    capability_tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    linked_recommendation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recommendations.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship("Organization")
    linked_recommendation: Mapped["Recommendation | None"] = relationship(
        "Recommendation", back_populates="agents"
    )
    usage_logs: Mapped[list["AgentUsageLog"]] = relationship(
        "AgentUsageLog", back_populates="agent", cascade="all, delete-orphan"
    )


class AgentUsageLog(Base):
    __tablename__ = "agent_usage_logs"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    agent_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Numeric(8, 4), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    agent: Mapped["Agent"] = relationship("Agent", back_populates="usage_logs")
