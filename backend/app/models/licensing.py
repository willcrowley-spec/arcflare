from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.connection import PlatformConnection
    from app.models.organization import Organization


class OrgLicenseSnapshot(Base):
    __tablename__ = "org_license_snapshots"

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
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    edition: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    licenses_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    package_licenses_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    psl_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    limits_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    estimated_annual_spend: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    organization: Mapped["Organization"] = relationship("Organization")
    connection: Mapped["PlatformConnection"] = relationship("PlatformConnection")


class UserVelocitySnapshot(Base):
    __tablename__ = "user_velocity_snapshots"

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
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    active_user_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    internal_active_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    external_active_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    new_users_this_month: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    deactivated_this_month: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    by_role_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    by_profile_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    organization: Mapped["Organization"] = relationship("Organization")
    connection: Mapped["PlatformConnection"] = relationship("PlatformConnection")
