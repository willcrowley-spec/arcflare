from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConnectionCreate(BaseModel):
    platform_type: str = Field(default="salesforce", max_length=50)
    instance_url: str | None = Field(default=None, max_length=512)


class ConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    platform_type: str
    platform_org_id: str | None = None
    instance_url: str | None
    status: str
    entity_count: int
    last_sync_at: datetime | None
    sync_config_json: dict
    created_at: datetime


class ConnectionList(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    connections: list[ConnectionResponse]
    total: int
