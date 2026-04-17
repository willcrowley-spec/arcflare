from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MetadataObjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    connection_id: UUID
    api_name: str
    label: str | None
    object_type: str | None
    field_count: int
    record_count: int
    is_custom: bool
    managed_package_namespace: str | None
    classification: str | None
    classification_source: str
    velocity_score: float
    automation_count: int = 0
    metadata_json: dict


class MetadataFieldResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    api_name: str
    label: str | None
    field_type: str | None
    is_custom: bool
    is_required: bool
    is_indexed: bool
    is_unique: bool
    relationship_to: str | None
    relationship_type: str | None
    metadata_json: dict


class TelemetryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    object_id: UUID
    record_count: int
    created_count_delta: int
    modified_count_delta: int
    snapshot_at: datetime


class AutomationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    connection_id: UUID
    org_id: UUID
    automation_type: str
    api_name: str
    label: str | None
    status: str | None
    related_object: str | None
    complexity_score: int | None
    metadata_json: dict


class VelocityPoint(BaseModel):
    object_id: UUID
    api_name: str
    velocity_score: float
    window_days: int


class MetadataComponentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    connection_id: UUID
    component_category: str
    api_name: str
    label: str | None
    status: str | None
    related_object: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class MetadataSummary(BaseModel):
    objects: dict = Field(default_factory=dict)
    fields: dict = Field(default_factory=dict)
    automations: dict = Field(default_factory=dict)
    components: dict = Field(default_factory=dict)
    licensing: dict = Field(default_factory=dict)
    last_sync_at: datetime | None = None
