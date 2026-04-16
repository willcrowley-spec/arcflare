from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.connection import PlatformConnection
    from app.models.organization import Organization


class MetadataObject(Base):
    __tablename__ = "metadata_objects"
    __table_args__ = (
        UniqueConstraint("connection_id", "api_name", name="uq_metadata_objects_connection_api_name"),
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
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    field_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    managed_package_namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    has_triggers: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_flows: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    has_validation_rules: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    connection: Mapped["PlatformConnection"] = relationship(
        "PlatformConnection", back_populates="metadata_objects"
    )
    fields: Mapped[list["MetadataField"]] = relationship(
        "MetadataField", back_populates="metadata_object", cascade="all, delete-orphan"
    )
    telemetry: Mapped[list["RecordTelemetry"]] = relationship(
        "RecordTelemetry", back_populates="metadata_object", cascade="all, delete-orphan"
    )


class MetadataField(Base):
    __tablename__ = "metadata_fields"
    __table_args__ = (UniqueConstraint("object_id", "api_name", name="uq_metadata_fields_object_api_name"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("metadata_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_indexed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    relationship_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relationship_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    metadata_object: Mapped["MetadataObject"] = relationship("MetadataObject", back_populates="fields")


class MetadataAutomation(Base):
    __tablename__ = "metadata_automation"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "automation_type",
            "api_name",
            name="uq_metadata_automation_conn_type_api",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    automation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_object: Mapped[str | None] = mapped_column(String(255), nullable=True)
    complexity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    connection: Mapped["PlatformConnection"] = relationship(
        "PlatformConnection", back_populates="automations"
    )
    organization: Mapped["Organization"] = relationship("Organization")


class RecordTelemetry(Base):
    __tablename__ = "record_telemetry"
    __table_args__ = (Index("ix_record_telemetry_object_snapshot", "object_id", "snapshot_at"),)

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    object_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("metadata_objects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_count_delta: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    modified_count_delta: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    metadata_object: Mapped["MetadataObject"] = relationship("MetadataObject", back_populates="telemetry")


class MetadataComponent(Base):
    __tablename__ = "metadata_components"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "component_category",
            "api_name",
            name="uq_metadata_components_conn_cat_api",
        ),
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
    connection_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    component_category: Mapped[str] = mapped_column(String(50), nullable=False)
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    related_object: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    organization: Mapped["Organization"] = relationship("Organization")
    connection: Mapped["PlatformConnection"] = relationship("PlatformConnection")
