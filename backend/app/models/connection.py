from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.metadata import MetadataAutomation, MetadataObject
    from app.models.organization import Organization


class PlatformConnection(Base):
    __tablename__ = "platform_connections"
    __table_args__ = (
        UniqueConstraint("org_id", "platform_type", "platform_org_id", name="uq_connection_platform_org"),
    )

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
    platform_type: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_org_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    instance_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    oauth_tokens_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="pending")
    entity_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_config_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship("Organization", back_populates="connections")
    metadata_objects: Mapped[list["MetadataObject"]] = relationship(
        "MetadataObject", back_populates="connection"
    )
    automations: Mapped[list["MetadataAutomation"]] = relationship(
        "MetadataAutomation", back_populates="connection"
    )
