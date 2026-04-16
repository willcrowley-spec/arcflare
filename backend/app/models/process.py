from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.organization import Organization


class BusinessProcess(Base):
    __tablename__ = "business_processes"

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
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    efficiency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    automation_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="draft")
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    sub_process_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    managed_asset_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship("Organization")
    nodes: Mapped[list["ProcessNode"]] = relationship(
        "ProcessNode", back_populates="process", cascade="all, delete-orphan"
    )
    edges: Mapped[list["ProcessEdge"]] = relationship(
        "ProcessEdge", back_populates="process", cascade="all, delete-orphan"
    )


class ProcessNode(Base):
    __tablename__ = "process_nodes"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_type: Mapped[str] = mapped_column(String(50), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(100), nullable=True)
    position_x: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    position_y: Mapped[float] = mapped_column(Float, nullable=False, server_default="0")
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    process: Mapped["BusinessProcess"] = relationship("BusinessProcess", back_populates="nodes")


class ProcessEdge(Base):
    __tablename__ = "process_edges"
    __table_args__ = (
        UniqueConstraint(
            "process_id",
            "source_node_id",
            "target_node_id",
            name="uq_process_edges_process_src_tgt",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    process_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("business_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("process_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_node_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("process_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    relationship_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    process: Mapped["BusinessProcess"] = relationship("BusinessProcess", back_populates="edges")
    source_node: Mapped["ProcessNode"] = relationship("ProcessNode", foreign_keys=[source_node_id])
    target_node: Mapped["ProcessNode"] = relationship("ProcessNode", foreign_keys=[target_node_id])
