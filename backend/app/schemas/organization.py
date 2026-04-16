from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrgProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    clerk_org_id: str
    plan_tier: str
    settings_json: dict
    created_at: datetime
    updated_at: datetime


class EntityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: UUID
    name: str
    entity_type: str | None
    parent_id: UUID | None
    department: str | None
    title: str | None
    role: str | None
    headcount: int
    is_active: bool
    salesforce_user_id: str | None
    cost_data_json: dict
    metadata_json: dict
    created_at: datetime


class EntityCreate(BaseModel):
    name: str = Field(..., max_length=255)
    entity_type: str | None = Field(default=None, max_length=50)
    parent_id: UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    headcount: int = Field(default=1, ge=0)
    is_active: bool = True
    salesforce_user_id: str | None = Field(default=None, max_length=18)


class EntityUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    entity_type: str | None = Field(default=None, max_length=50)
    parent_id: UUID | None = None
    department: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    headcount: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    salesforce_user_id: str | None = Field(default=None, max_length=18)
    cost_data_json: dict | None = None
    metadata_json: dict | None = None


class CostModelResponse(BaseModel):
    org_id: UUID
    annual_cost_deflection: float | None = None
    hires_deflected: float | None = None
    assumptions: dict = Field(default_factory=dict)


class HierarchyNode(BaseModel):
    id: UUID
    name: str
    entity_type: str | None
    children: list["HierarchyNode"] = Field(default_factory=list)


class HierarchyResponse(BaseModel):
    roots: list[HierarchyNode]
